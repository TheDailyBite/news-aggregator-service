from typing import Any, Dict, List, Optional, Set, Tuple

import json
import uuid
from collections.abc import Mapping
from datetime import datetime
from itertools import zip_longest

import boto3
import numpy as np
import tiktoken
from langchain import PromptTemplate
from langchain.callbacks import get_openai_callback
from langchain.chains import LLMChain
from langchain.chains.summarize import load_summarize_chain
from langchain.chat_models import ChatOpenAI
from langchain.docstore.document import Document
from langchain.embeddings import HuggingFaceHubEmbeddings, OpenAIEmbeddings
from langchain.embeddings.base import Embeddings
from langchain.text_splitter import TokenTextSplitter
from news_aggregator_data_access_layer.assets.news_assets import RawArticle, RawArticleEmbedding
from news_aggregator_data_access_layer.config import (
    REGION_NAME,
    S3_ENDPOINT_URL,
    SOURCED_ARTICLES_S3_BUCKET,
)
from news_aggregator_data_access_layer.constants import (
    ArticleApprovalStatus,
    EmbeddingType,
    SummarizationLength,
)
from news_aggregator_data_access_layer.models.dynamodb import (
    SourcedArticles,
    get_current_dt_utc_attribute,
)
from news_aggregator_data_access_layer.utils.s3 import (
    dt_to_lexicographic_dash_s3_prefix,
    dt_to_lexicographic_date_s3_prefix,
    dt_to_lexicographic_s3_prefix,
    get_success_file,
    read_objects_from_prefix_with_extension,
    store_object_in_s3,
    store_success_file,
    success_file_exists_at_prefix,
)
from pydantic import BaseModel
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.metrics import silhouette_score
from tenacity import retry, stop_after_attempt, wait_random_exponential

from news_aggregator_service.config import (
    FAKE_HUGGINGFACE_API_KEY,
    FAKE_OPENAI_API_KEY,
    HUGGINGFACE_API_KEY,
    HUGGINGFACE_API_KEY_SECRET_NAME,
    LONG_SUMMARIZATION_MODEL_NAME,
    OPENAI_API_KEY,
    OPENAI_API_KEY_SECRET_NAME,
    SUMMARIZATION_MODEL_NAME,
    SUMMARIZATION_TEMPERATURE,
)
from news_aggregator_service.constants import (
    ARTICLE_SEPARATOR,
    MEDIUM_SUMMARY_DEFINITION,
    REFINE_REWRITE_PROMPT_TEMPLATE,
    REFINE_REWRITE_REFINE_STEP_TEMPLATE,
    SHORT_SUMMARY_DEFINITION,
    SUMMARIZATION_FAILURE_MESSAGE,
    SUMMARIZATION_TEMPLATE,
    TITLE_REWRITE_TEMPLATE,
)
from news_aggregator_service.exceptions import ArticleSummarizationFailure
from news_aggregator_service.utils.secrets import get_secret
from news_aggregator_service.utils.telemetry import setup_logger

logger = setup_logger(__name__)

# Set up Open AI API credentials
# NOTE - this is just used for testing locally
# in production, we use the secrets manager
if OPENAI_API_KEY:
    openai_api_key = OPENAI_API_KEY
else:
    try:
        openai_api_key = get_secret(OPENAI_API_KEY_SECRET_NAME)
    except Exception as e:
        logger.info("Using fake open ai api key for testing")
        openai_api_key = FAKE_OPENAI_API_KEY

# Set up Hugging Face API credentials
# NOTE - this is just used for testing locally
# in production, we use the secrets manager
if HUGGINGFACE_API_KEY:
    huggingface_api_key = HUGGINGFACE_API_KEY
else:
    try:
        huggingface_api_key = get_secret(HUGGINGFACE_API_KEY_SECRET_NAME)
    except Exception as e:
        logger.info("Using fake hugging face api key for testing")
        huggingface_api_key = FAKE_HUGGINGFACE_API_KEY


class SourcedArticleRef(BaseModel):
    article_id: str
    article_title: str
    article_dt_published: str
    article_topic_id: str
    article_topic: str
    source_article_categories: list[str]
    source_article_ids: list[str]
    source_article_urls: list[str]
    source_article_provider_domains: list[str]
    source_article_titles: list[str]


class SourcedArticle:
    def __init__(
        self,
        article_cluster: list[RawArticle],
        publishing_date_str: str,
        topic_id: str,
        topic: str,
        sourcing_run_id: str,
        s3_client: boto3.client = boto3.client(
            service_name="s3", region_name=REGION_NAME, endpoint_url=S3_ENDPOINT_URL
        ),
    ):
        if (
            not all(isinstance(article, RawArticle) for article in article_cluster)
            or not article_cluster
        ):
            raise ValueError(
                f"article_cluster must be of type List[RawArticle]; actual type {type(article_cluster)}"
            )
        self.article_cluster = article_cluster
        self.article_cluster_dts_published = [
            datetime.fromisoformat(article.dt_published) for article in self.article_cluster
        ]
        self.sourced_article_published_dt = min(self.article_cluster_dts_published)
        logger.info(
            f"Computed Sourced article published dt will be {self.sourced_article_published_dt} as the min of {self.article_cluster_dts_published}"
        )
        self.source_article_categories = [article.category for article in self.article_cluster]
        self.source_article_ids = [article.article_id for article in self.article_cluster]
        self.source_article_urls = [article.url for article in self.article_cluster]
        self.source_article_provider_domains = [
            article.provider_domain for article in self.article_cluster
        ]
        self.source_article_titles = [article.title for article in self.article_cluster]
        self.sourced_article_id = f"{dt_to_lexicographic_dash_s3_prefix(self.sourced_article_published_dt)}#{str(uuid.uuid4())}"
        self.publishing_date_str = publishing_date_str
        self.topic_id = topic_id
        self.topic = topic
        self.sourcing_run_id = sourcing_run_id
        self.s3_client = s3_client
        self.sourced_candidate_articles_s3_extension = ".json"
        self.summary_s3_extension = ".txt"
        self.summarization_suffix = "_summary"
        self.success_marker_fn = "__SUCCESS__"
        self.is_processed = False
        self.text_chunk_token_length = 250
        self.text_chunk_token_overlap = 0
        self.title: str = ""
        self.full_article_summary: Optional[str] = None
        self.medium_article_summary: Optional[str] = None
        self.short_article_summary: Optional[str] = None
        self.article_processing_cost = 0.0
        summarization_open_ai = ChatOpenAI(
            model_name=SUMMARIZATION_MODEL_NAME,
            openai_api_key=openai_api_key,
            temperature=SUMMARIZATION_TEMPERATURE,
        )  # type: ignore
        self.summarization_open_ai = summarization_open_ai
        long_summarization_open_ai = ChatOpenAI(
            model_name=LONG_SUMMARIZATION_MODEL_NAME,
            openai_api_key=openai_api_key,
            temperature=SUMMARIZATION_TEMPERATURE,
        )  # type: ignore
        self.long_summarization_open_ai = long_summarization_open_ai
        # summarization stuff
        summarization_prompt_template = SUMMARIZATION_TEMPLATE.replace("####topic####", self.topic)
        self._medium_summarization_prompt_template = PromptTemplate(
            template=summarization_prompt_template.replace(
                "####summary_definition####", MEDIUM_SUMMARY_DEFINITION
            ),
            input_variables=["text"],
        )
        self._medium_summarization_stuff_llm_chain = load_summarize_chain(
            long_summarization_open_ai,
            chain_type="stuff",
            prompt=self._medium_summarization_prompt_template,
        )
        self._short_summarization_prompt_template = PromptTemplate(
            template=summarization_prompt_template.replace(
                "####summary_definition####", SHORT_SUMMARY_DEFINITION
            ),
            input_variables=["text"],
        )
        self._short_summarization_stuff_llm_chain = load_summarize_chain(
            long_summarization_open_ai,
            chain_type="stuff",
            prompt=self._short_summarization_prompt_template,
        )
        # refine rewrite chains
        refine_rewrite_prompt_template = REFINE_REWRITE_PROMPT_TEMPLATE.replace(
            "####topic####", self.topic
        )
        refine_rewrite_refine_step_prompt_template = REFINE_REWRITE_REFINE_STEP_TEMPLATE.replace(
            "####topic####", self.topic
        )
        self._refine_rewrite_prompt_template = PromptTemplate(
            template=refine_rewrite_prompt_template,
            input_variables=["text"],
        )
        self._refine_rewrite_refine_step_prompt_template = PromptTemplate(
            template=refine_rewrite_refine_step_prompt_template,
            input_variables=["existing_answer", "text"],
        )
        self._rewrite_refine_llm_chain = load_summarize_chain(
            self.summarization_open_ai,
            chain_type="refine",
            question_prompt=self._refine_rewrite_prompt_template,
            refine_prompt=self._refine_rewrite_refine_step_prompt_template,
        )
        self._rewrite_long_refine_llm_chain = load_summarize_chain(
            self.long_summarization_open_ai,
            chain_type="refine",
            question_prompt=self._refine_rewrite_prompt_template,
            refine_prompt=self._refine_rewrite_refine_step_prompt_template,
        )
        # TODO - add others
        # title
        title_rewrite_template = TITLE_REWRITE_TEMPLATE.replace("####topic####", self.topic)
        self._title_rewrite_prompt_template = PromptTemplate(
            template=title_rewrite_template,
            input_variables=["text"],
        )
        self._title_generation_stuff_chain = load_summarize_chain(
            summarization_open_ai,
            chain_type="stuff",
            prompt=self._title_rewrite_prompt_template,
        )

    def _get_sourced_candidates_s3_object_prefix(self) -> str:
        return f"sourced_candidate_articles/{self.topic_id}/{self.publishing_date_str}/{self.sourced_article_id}"

    def _get_sourced_candidate_article_s3_object_key(self) -> str:
        return f"{self._get_sourced_candidates_s3_object_prefix()}/{self.sourced_article_id}{self.sourced_candidate_articles_s3_extension}"

    def _get_sourced_candidate_article_summary_s3_object_key(
        self, summarization_length: SummarizationLength
    ) -> str:
        return f"{self._get_sourced_candidates_s3_object_prefix()}/{summarization_length.value}{self.summarization_suffix}{self.summary_s3_extension}"

    def process_article(self) -> float:
        try:
            logger.info(f"Processing article with sourced article id {self.sourced_article_id}")
            article_processing_cost = 0.0
            self.title, cost = self._generate_article_title()
            article_processing_cost += cost
            # create article summaries
            self.full_article_summary, cost = self._summarize_article(
                summarization_length=SummarizationLength.FULL
            )
            article_processing_cost += cost
            self.medium_article_summary, cost = self._summarize_article(
                summarization_length=SummarizationLength.MEDIUM
            )
            article_processing_cost += cost
            self.short_article_summary, cost = self._summarize_article(
                summarization_length=SummarizationLength.SHORT
            )
            article_processing_cost += cost
            # TODO -
            # create embedding?
            # find out clustered topic using BertTopic?
            # find out sentiment?
            # More?
            self.is_processed = True
            self.article_processing_cost = article_processing_cost
            return article_processing_cost
        except Exception as e:
            logger.error(
                f"Error processing article {self.sourced_article_id}: {e}. Source article ids: {self.source_article_ids}"
            )
            raise

    def store_article(self):
        logger.info(f"Storing article {self.sourced_article_id}")
        if not self.is_processed:
            logger.info(
                f"Article {self.sourced_article_id} has not been processed yet. Processing now..."
            )
            self.process_article()
        # store sourced article in json
        # store summarizations in txt with "text/plain" content type
        # store article in dynamodb with an approval status of "pending"
        article_dir_prefix = self._get_sourced_candidates_s3_object_prefix()
        article_key = self._get_sourced_candidate_article_s3_object_key()
        short_summary_key = self._get_sourced_candidate_article_summary_s3_object_key(
            SummarizationLength.SHORT
        )
        medium_summary_key = self._get_sourced_candidate_article_summary_s3_object_key(
            SummarizationLength.MEDIUM
        )
        full_summary_key = self._get_sourced_candidate_article_summary_s3_object_key(
            SummarizationLength.FULL
        )
        source_article_ref = SourcedArticleRef(
            article_id=self.sourced_article_id,
            article_title=self.title,
            article_dt_published=self.sourced_article_published_dt.isoformat(),
            article_topic_id=self.topic_id,
            article_topic=self.topic,
            source_article_categories=self.source_article_categories,
            source_article_ids=self.source_article_ids,
            source_article_urls=self.source_article_urls,
            source_article_provider_domains=self.source_article_provider_domains,
            source_article_titles=self.source_article_titles,
        )
        store_object_in_s3(
            SOURCED_ARTICLES_S3_BUCKET,
            article_key,
            source_article_ref.json(),
            s3_client=self.s3_client,
        )
        # TODO - might need to add content-type
        store_object_in_s3(
            SOURCED_ARTICLES_S3_BUCKET,
            short_summary_key,
            self.short_article_summary,
            s3_client=self.s3_client,
        )
        store_object_in_s3(
            SOURCED_ARTICLES_S3_BUCKET,
            medium_summary_key,
            self.medium_article_summary,
            s3_client=self.s3_client,
        )
        store_object_in_s3(
            SOURCED_ARTICLES_S3_BUCKET,
            full_summary_key,
            self.full_article_summary,
            s3_client=self.s3_client,
        )
        store_success_file(
            SOURCED_ARTICLES_S3_BUCKET,
            article_dir_prefix,
            self.success_marker_fn,
            s3_client=self.s3_client,
        )
        db_sourced_article = SourcedArticles(
            topic_id=self.topic_id,
            sourced_article_id=self.sourced_article_id,
            dt_sourced=get_current_dt_utc_attribute(),
            dt_published=self.sourced_article_published_dt,
            date_published=self.publishing_date_str,
            title=self.title,
            topic=self.topic,
            source_article_categories=self.source_article_categories,
            source_article_ids=self.source_article_ids,
            source_article_urls=self.source_article_urls,
            providers=self.source_article_provider_domains,
            short_summary_ref=short_summary_key,
            medium_summary_ref=medium_summary_key,
            full_summary_ref=full_summary_key,
            sourcing_run_id=self.sourcing_run_id,
            article_processing_cost=self.article_processing_cost,
            article_approval_status=ArticleApprovalStatus.APPROVED,  # TODO - NOTE - this is temporary to assess the quality of articles
        )
        logger.info(
            f"Saving sourced article for partition key {self.topic_id} and range key {self.sourced_article_id} to dynamodb..."
        )
        db_sourced_article.save(condition=SourcedArticles.sourced_article_id.does_not_exist())

    def _chunk_text_in_docs(self, article_cluster_texts: list[str]) -> list[Document]:
        docs: list[Document] = []
        # the chunk_size and overlap is in tokens
        text_splitter = TokenTextSplitter.from_tiktoken_encoder(
            model_name="gpt-3.5-turbo",
            chunk_size=self.text_chunk_token_length,
            chunk_overlap=self.text_chunk_token_overlap,
        )
        # will look like = [[chunk_article_1_0, chunk_article_1_1, ....], [chunk_article_2_0, chunk_article_2_1, ...], ....]
        chunked_text_per_article_in_cluster: list[list[str]] = []
        num_articles_in_cluster = len(article_cluster_texts)
        for article_text in article_cluster_texts:
            chunked_article_text = text_splitter.split_text(article_text)
            chunked_text_per_article_in_cluster.append(chunked_article_text)
        for chunked_articles in zip_longest(*chunked_text_per_article_in_cluster, fillvalue=None):
            text_list = []
            for article_chunk in chunked_articles:
                if article_chunk is not None:
                    text_list.append(article_chunk)
            text = ARTICLE_SEPARATOR.join(text_list)
            doc = Document(page_content=text)
            docs.append(doc)
        return docs

    def _generate_article_title(self) -> tuple[str, float]:
        docs: list[Document] = [
            Document(page_content=title) for title in self.source_article_titles
        ]
        chain = self._title_generation_stuff_chain
        logger.info(
            f"Generating article title for {self.sourced_article_id} using chain {type(chain)}..."
        )
        with get_openai_callback() as cb:
            response = chain.run(docs)
            title = response
            # NOTE - the title is wrapped in quotes for some reason so we remove them
            if title.startswith('"') and title.endswith('"'):
                title = title[1:-1]
            # TODO - emit metrics
            logger.info(
                f"Title generation chain has total cost {cb.total_cost}. Total tokens: {cb.total_tokens}; prompt tokens {cb.prompt_tokens}; completion tokens {cb.completion_tokens}; title character length {len(title)}."
            )
            return title, float(cb.total_cost)

    def _summarize_article(self, summarization_length: SummarizationLength) -> tuple[str, float]:
        article_cluster_texts = [article.get_article_text() for article in self.article_cluster]
        if summarization_length == SummarizationLength.FULL:
            token_counts = []
            for article_text in article_cluster_texts:
                tokens = self.long_summarization_open_ai.get_token_ids(article_text)
                token_counts.append(len(tokens))
            logger.info(
                f"Total tokens in article cluster: {sum(token_counts)}. Total articles in cluster: {len(article_cluster_texts)}. Average tokens per article: {float(sum(token_counts)) / len(article_cluster_texts)}. Max tokens per article: {max(token_counts)}."
            )
            # TODO - might still need to chunk the text
            # will try with each doc being an article initially
            # I probably need to chunk it as I did before and maybe add the separator
            docs: list[Document] = [
                Document(page_content=article_text) for article_text in article_cluster_texts
            ]
            # simply rewrite the article instead of summarizing
            # TODO - NOTE - we are using the long chain by default. In the future we could definetely use long chain
            # only for documents with large number of tokens, else the normal context length one
            chain = self._rewrite_long_refine_llm_chain
        elif summarization_length == SummarizationLength.MEDIUM:
            chain = self._medium_summarization_stuff_llm_chain
            if not self.full_article_summary:
                raise ArticleSummarizationFailure(
                    self.sourced_article_id,
                    "Full article summary is empty. Cannot produce medium summary.",
                )
            docs = [Document(page_content=self.full_article_summary)]
        elif summarization_length == SummarizationLength.SHORT:
            chain = self._short_summarization_stuff_llm_chain
            if not self.full_article_summary:
                raise ArticleSummarizationFailure(
                    self.sourced_article_id,
                    "Full article summary is empty. Cannot produce short summary.",
                )
            docs = [Document(page_content=self.full_article_summary)]
        else:
            raise ValueError(f"Invalid summarization length {summarization_length.value}")
        logger.info(
            f"Summarizing article {self.sourced_article_id} with summarization length {summarization_length.value} using chain {type(chain)}..."
        )
        with get_openai_callback() as cb:
            response = chain.run(docs)
            summary = response
            # TODO - emit metrics
            logger.info(
                f"Summary chain for summarization length {summarization_length.value} has total cost {cb.total_cost}. Total tokens: {cb.total_tokens}; prompt tokens {cb.prompt_tokens}; completion tokens {cb.completion_tokens}; summary character length {len(summary)}."
            )
            return summary, float(cb.total_cost)


class ArticleClusterGenerator:
    def __init__(self, raw_articles: list[RawArticle]):
        self.raw_articles = raw_articles
        self.clustered_articles: list[list[RawArticle]] = []
        self.embedding_model_name = "text-embedding-ada-002"
        self._openai_ada2_text_embedding_model = OpenAIEmbeddings(  # type: ignore
            chunk_size=2048, model=self.embedding_model_name, openai_api_key=openai_api_key
        )
        # change if needed. Currently ada2 text is set as default
        self.embeddings_model = self._openai_ada2_text_embedding_model
        self.embeddings_model_cost_per_token = 0.0001 / 1000
        self.embedding_type = EmbeddingType.TITLE_AND_DESCRIPTION_AND_CONTENT_CONCAT

    def _generate_docs(self) -> list[str]:
        logger.info(
            f"Generating docs for {len(self.raw_articles)} articles for embedding type {self.embedding_type.value}..."
        )
        if self.embedding_type == EmbeddingType.TITLE:
            docs = [article.title for article in self.raw_articles]
        elif self.embedding_type == EmbeddingType.DESCRIPTION:
            docs = [article.get_article_text_description() for article in self.raw_articles]
        elif self.embedding_type == EmbeddingType.CONTENT:
            docs = [article.get_article_text() for article in self.raw_articles]
        elif self.embedding_type == EmbeddingType.TITLE_AND_DESCRIPTION_CONCAT:
            docs = [
                f"{article.title} {article.get_article_text_description()}"
                for article in self.raw_articles
            ]
        elif self.embedding_type == EmbeddingType.TITLE_AND_CONTENT_CONCAT:
            docs = [
                f"{article.title} {article.get_article_text()}" for article in self.raw_articles
            ]
        elif self.embedding_type == EmbeddingType.DESCRIPTION_AND_CONTENT_CONCAT:
            docs = [
                f"{article.get_article_text_description()} {article.get_article_text()}"
                for article in self.raw_articles
            ]
        elif self.embedding_type == EmbeddingType.TITLE_AND_DESCRIPTION_AND_CONTENT_CONCAT:
            docs = [
                f"{article.title} {article.get_article_text_description()} {article.get_article_text()}"
                for article in self.raw_articles
            ]
        elif self.embedding_type == EmbeddingType.TITLE_AND_DESCRIPTION_AVG:
            docs = [
                item
                for article in self.raw_articles
                for item in [article.title, article.get_article_text_description()]
            ]
        elif self.embedding_type == EmbeddingType.TITLE_AND_CONTENT_AVG:
            docs = [
                item
                for article in self.raw_articles
                for item in [article.title, article.get_article_text()]
            ]
        elif self.embedding_type == EmbeddingType.DESCRIPTION_AND_CONTENT_AVG:
            docs = [
                item
                for article in self.raw_articles
                for item in [article.get_article_text_description(), article.get_article_text()]
            ]
        elif self.embedding_type == EmbeddingType.TITLE_AND_DESCRIPTION_AND_CONTENT_AVG:
            docs = [
                item
                for article in self.raw_articles
                for item in [
                    article.title,
                    article.get_article_text_description(),
                    article.get_article_text(),
                ]
            ]
        else:
            raise NotImplementedError(
                f"Embedding type {self.embedding_type.value} not implemented."
            )
        docs = [doc.replace("\n", " ") for doc in docs]
        return docs

    def _combine_embeddings(self, embeddings: list[list[float]]) -> list[list[float]]:
        if len(embeddings) % len(self.raw_articles) != 0:
            raise ValueError(
                f"Embeddings length {len(embeddings)} is not a multiple of raw articles length {len(self.raw_articles)}"
            )
        attributes_per_article = len(embeddings) // len(self.raw_articles)
        combined_embeddings = []
        for i in range(0, len(embeddings), attributes_per_article):
            attr_embeddings = []
            for j in range(attributes_per_article):
                attr_embeddings.append(embeddings[i + j])
            avg_attr_embeddings = [np.mean(values) for values in zip(*attr_embeddings)]
            combined_embeddings.append(avg_attr_embeddings)
        if len(combined_embeddings) != len(self.raw_articles):
            raise ValueError(
                f"Combined embeddings length {len(combined_embeddings)} is not equal to raw articles length {len(self.raw_articles)}"
            )
        return combined_embeddings

    def generate_clusters(self) -> tuple[list[list[RawArticle]], list[RawArticleEmbedding], float]:
        logger.info(f"Generating clusters for {len(self.raw_articles)} articles...")
        docs: list[str] = self._generate_docs()
        embeddings = self._generate_embeddings(
            docs, self.embeddings_model, self.embeddings_model_cost_per_token
        )
        if len(embeddings) != len(self.raw_articles):
            embeddings = self._combine_embeddings(embeddings)
        article_embeddings: list[RawArticleEmbedding] = self._generate_article_embeddings(
            embeddings
        )
        # with <= 2 articles the clustering algorithm fails. In any case it wouldn't work well.
        if len(self.raw_articles) <= 2:
            return [[article] for article in self.raw_articles], article_embeddings, float("inf")
        cluster_labels, n_clusters, clustering_score = self._cluster_embeddings(embeddings)
        logger.info(
            f"Generated {n_clusters} clusters with clustering score {clustering_score} for embedding type {self.embedding_type.value}..."
        )
        self.clustered_articles = self._group_articles_by_cluster(
            self.raw_articles, cluster_labels, n_clusters
        )
        self.__log_cluster_stats(self.clustered_articles)
        return self.clustered_articles, article_embeddings, clustering_score

    def _generate_article_embeddings(
        self, embeddings: list[list[float]]
    ) -> list[RawArticleEmbedding]:
        return [
            RawArticleEmbedding(
                article_id=self.raw_articles[i].article_id,
                embedding_type=self.embedding_type.value,
                embedding_model_name=self.embedding_model_name,
                embedding=embeddings[i],
            )
            for i in range(len(self.raw_articles))
        ]

    def __log_cluster_stats(self, clustered_articles: list[list[RawArticle]]) -> None:
        logger.info(f"Generated {len(clustered_articles)} clusters.")
        for cluster in clustered_articles:
            logger.info("==============Cluster==============\n")
            for cluster_article in cluster:
                logger.info(f"Title: {cluster_article.title}; Url: {cluster_article.url}")
            logger.info("\n")

    def _group_articles_by_cluster(
        self, articles: list[RawArticle], labels: list[int], n_clusters: int
    ) -> list[list[RawArticle]]:
        result: list[list[RawArticle]] = []
        for i in range(n_clusters):
            result.append([])
        for cluster_idx, article in zip(labels, articles):
            result[cluster_idx].append(article)
        return result

    @retry(wait=wait_random_exponential(multiplier=1, max=60), stop=stop_after_attempt(5))
    def _generate_embeddings(
        self, docs: list[str], embedding_model: Embeddings, cost_per_token: float
    ) -> list[list[float]]:
        encoding = tiktoken.model.encoding_for_model(embedding_model.model)  # type: ignore
        total_tokens = 0
        for doc in docs:
            tokens = encoding.encode(
                doc,
                allowed_special=embedding_model.allowed_special,  # type: ignore
                disallowed_special=embedding_model.disallowed_special,  # type: ignore
            )
            total_tokens += len(tokens)
        # TODO - add timing
        embeddings = embedding_model.embed_documents(docs)
        if (
            not embeddings
            or not isinstance(embeddings, list)
            or not isinstance(embeddings[0], list)
            or not isinstance(embeddings[0][0], float)
        ):
            raise ValueError(
                f"Embeddings are not in the expected format. Expected list[list[float]]; got {type(embeddings)}. {embeddings}"
            )
        logger.info(
            f"Total tokens in documents: {total_tokens}. Approx Cost USD to generate embeddings with model {embedding_model}: {total_tokens * cost_per_token}"
        )
        return embeddings

    def _cluster_embeddings(self, embeddings: list[list[float]]) -> tuple[list[int], int, float]:
        return self._hac_cluster_embeddings(embeddings)

    def _hac_cluster_embeddings(
        self, embeddings: list[list[float]]
    ) -> tuple[list[int], int, float]:
        logger.info("Clustering embeddings using HAC...")
        range_n_clusters = range(2, len(embeddings))
        embeddings_np = np.array(embeddings, dtype=np.float32)
        silhouette_avg_scores = []
        iter_labels = []
        for n_clusters in range_n_clusters:
            # The silhouette coefficient can range from -1, 1
            clusterer = AgglomerativeClustering(n_clusters=n_clusters, linkage="ward")
            # Fit the model
            clusterer = clusterer.fit(embeddings_np)
            cluster_labels = clusterer.labels_
            # The silhouette_score gives the average value for all the samples.
            # This gives a perspective into the density and separation of the formed
            # clusters
            silhouette_avg = silhouette_score(embeddings_np, cluster_labels)
            silhouette_avg_scores.append(silhouette_avg)
            iter_labels.append(cluster_labels.tolist())
        max_silhouette_avg_idx = silhouette_avg_scores.index(max(silhouette_avg_scores))
        max_silhouette_avg = silhouette_avg_scores[max_silhouette_avg_idx]
        max_silhouette_avg_labels = iter_labels[max_silhouette_avg_idx]
        n_clusters = range_n_clusters[max_silhouette_avg_idx]
        logger.info(
            f"Optimal number of clusters: {n_clusters}. Max silhouette score: {max_silhouette_avg}. Max silhouette score labels: {max_silhouette_avg_labels}. Max iter index: {max_silhouette_avg_idx}. All silhouette scores: {silhouette_avg_scores}"
        )
        return max_silhouette_avg_labels, n_clusters, max_silhouette_avg

    def _kmeans_cluster_embeddings(
        self, embeddings: list[list[float]]
    ) -> tuple[list[int], int, float]:
        logger.info("Clustering embeddings using KMeans...")
        range_n_clusters = range(2, len(embeddings))
        embeddings_np = np.array(embeddings, dtype=np.float32)
        silhouette_avg_scores = []
        iter_labels = []
        for n_clusters in range_n_clusters:
            # The silhouette coefficient can range from -1, 1
            # Initialize the clusterer with n_clusters value and a random generator
            # seed of 10 for reproducibility.
            clusterer = KMeans(
                n_clusters=n_clusters, init="k-means++", n_init="auto", random_state=10
            )
            cluster_labels = clusterer.fit_predict(embeddings_np)
            # The silhouette_score gives the average value for all the samples.
            # This gives a perspective into the density and separation of the formed
            # clusters
            silhouette_avg = silhouette_score(embeddings_np, cluster_labels)
            silhouette_avg_scores.append(silhouette_avg)
            iter_labels.append(cluster_labels.tolist())
            # Labeling the clusters
            centers = clusterer.cluster_centers_
        max_silhouette_avg_idx = silhouette_avg_scores.index(max(silhouette_avg_scores))
        max_silhouette_avg = silhouette_avg_scores[max_silhouette_avg_idx]
        max_silhouette_avg_labels = iter_labels[max_silhouette_avg_idx]
        n_clusters = range_n_clusters[max_silhouette_avg_idx]
        logger.info(
            f"Optimal number of clusters: {n_clusters}. Max silhouette score: {max_silhouette_avg}. Max silhouette score labels: {max_silhouette_avg_labels}. Max iter index: {max_silhouette_avg_idx}"
        )
        return max_silhouette_avg_labels, n_clusters, max_silhouette_avg
