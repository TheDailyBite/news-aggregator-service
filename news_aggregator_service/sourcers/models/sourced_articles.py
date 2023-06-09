from typing import Any, Dict, List, Optional, Set, Tuple

import uuid
from collections.abc import Mapping
from datetime import datetime

import boto3
import numpy as np
from langchain import PromptTemplate
from langchain.callbacks import get_openai_callback
from langchain.chains import LLMChain
from langchain.chat_models import ChatOpenAI
from langchain.embeddings import HuggingFaceHubEmbeddings
from news_aggregator_data_access_layer.assets.news_assets import RawArticle
from news_aggregator_data_access_layer.config import (
    REGION_NAME,
    S3_ENDPOINT_URL,
    SOURCED_ARTICLES_S3_BUCKET,
)
from news_aggregator_data_access_layer.constants import SummarizationLength
from news_aggregator_data_access_layer.models.dynamodb import SourcedArticles
from news_aggregator_data_access_layer.utils.s3 import (
    dt_to_lexicographic_date_s3_prefix,
    dt_to_lexicographic_s3_prefix,
    get_success_file,
    read_objects_from_prefix_with_extension,
    store_object_in_s3,
    store_success_file,
    success_file_exists_at_prefix,
)
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from tenacity import retry, stop_after_attempt, wait_random_exponential

from news_aggregator_service.config import (
    FAKE_HUGGINGFACE_API_KEY,
    FAKE_OPENAI_API_KEY,
    HUGGINGFACE_API_KEY,
    HUGGINGFACE_API_KEY_SECRET_NAME,
    OPENAI_API_KEY,
    OPENAI_API_KEY_SECRET_NAME,
    SUMMARIZATION_MODEL_NAME,
    SUMMARIZATION_TEMPERATURE,
)
from news_aggregator_service.constants import SUMMARIZATION_FAILURE_MESSAGE, SUMMARIZATION_TEMPLATE
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


class SourcedArticle:
    def __init__(
        self,
        clustered_articles: list[RawArticle],
        publishing_date_str: str,
        topic_id: str,
        topic: str,
        requested_category: str,
        s3_client: boto3.client = boto3.client(
            service_name="s3", region_name=REGION_NAME, endpoint_url=S3_ENDPOINT_URL
        ),
    ):
        if (
            not all(isinstance(article, RawArticle) for article in clustered_articles)
            or not clustered_articles
        ):
            raise ValueError("clustered_articles must be of type List[RawArticle]")
        self.clustered_articles = clustered_articles
        self.source_article_ids = [article.article_id for article in clustered_articles]
        self.publishing_date_str = publishing_date_str
        self.topic_id = topic_id
        self.topic = topic
        self.requested_category = requested_category
        self.s3_client = s3_client
        self.sourced_candidate_articles_s3_extension = ".json"
        self.summary_s3_extension = ".txt"
        self.summarization_suffix = "_summary"
        self.success_marker_fn = "__SUCCESS__"
        self.is_processed = False
        self.full_article_summary: Optional[str] = None
        self.medium_article_summary: Optional[str] = None
        self.short_article_summary: Optional[str] = None
        summarization_open_ai = ChatOpenAI(
            model_name=SUMMARIZATION_MODEL_NAME,
            openai_api_key=openai_api_key,
            temperature=SUMMARIZATION_TEMPERATURE,
        )  # type: ignore
        self._summarization_prompt_template = PromptTemplate(
            template=SUMMARIZATION_TEMPLATE,
            input_variables=["url", "length", "query", "failure_message"],
        )
        self._summarization_llm_chain = LLMChain(
            llm=summarization_open_ai,
            prompt=self._summarization_prompt_template,
        )

    def _get_sourced_candidates_s3_object_prefix(self) -> str:
        prefix = f"sourced_candidate_articles/{self.publishing_date_str}/{self.topic}"
        if self.requested_category:
            prefix += f"/{self.requested_category}"
        prefix += f"/{self.sourced_article_id}"
        return prefix

    def _get_sourced_candidate_article_s3_object_key(self) -> str:
        return f"{self._get_sourced_candidates_s3_object_prefix()}/{self.original_article_id}{self.sourced_candidate_articles_s3_extension}"

    def _get_sourced_candidate_article_summary_s3_object_key(
        self, summarization_length: SummarizationLength
    ) -> str:
        return f"{self._get_sourced_candidates_s3_object_prefix()}/{summarization_length.value}{self.summarization_suffix}{self.summary_s3_extension}"

    def process_article(self) -> None:
        logger.info(
            f"Processing article with original {self.original_article_id} and sourced article id {self.sourced_article_id}"
        )
        # Use a template to structure the prompt
        # create article summaries
        self.short_article_summary = self._summarize_article(
            summarization_length=SummarizationLength.SHORT
        )
        self.medium_article_summary = self._summarize_article(
            summarization_length=SummarizationLength.MEDIUM
        )
        self.full_article_summary = self._summarize_article(
            summarization_length=SummarizationLength.FULL
        )
        # create embedding?
        # find out clustered topic?
        # find out sentiment?
        # More?
        self.is_processed = True

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
        # TODO - might want to create a model for sourced articles to add additional context
        store_object_in_s3(
            SOURCED_ARTICLES_S3_BUCKET,
            article_key,
            self.raw_article.json(),
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
        # TODO - store in dynamodb - this might need to be revisited
        # TODO - should the title be retwritten? probably
        db_sourced_article = SourcedArticles(
            self.topic_requested_category,
            self.sourced_article_id,
            dt_published=datetime.fromisoformat(self.raw_article.dt_published),
            title=self.raw_article.title,
            topic=self.raw_article.topic,
            category=self.raw_article.category,
            original_article_id=self.original_article_id,
            short_summary_ref=short_summary_key,
            medium_summary_ref=medium_summary_key,
            full_summary_ref=full_summary_key,
        )
        logger.info(
            f"Saving sourced article for partition key {self.topic_requested_category} and range key {self.sourced_article_id} to dynamodb..."
        )
        db_sourced_article.save(condition=SourcedArticles.article_id.does_not_exist())

    def _summarize_article(self, summarization_length: SummarizationLength) -> str:
        inputs = {
            "url": self.article_url,
            "length": summarization_length.value,
            "failure_message": SUMMARIZATION_FAILURE_MESSAGE,
            "query": self.topic,
        }
        with get_openai_callback() as cb:
            response = self._summarization_llm_chain(inputs=inputs, return_only_outputs=True)
            summary = str(response["text"])
            if summary == SUMMARIZATION_FAILURE_MESSAGE:
                raise ArticleSummarizationFailure(self.original_article_id)
            # TODO - emit metrics
            logger.info(
                f"Summary chain for summarization length {summarization_length.value} has total cost {cb.total_cost}. Total tokens: {cb.total_tokens}; prompt tokens {cb.prompt_tokens}; completion tokens {cb.completion_tokens}; summary character length {len(summary)}."
            )
            return summary


class ArticleClusterGenerator:
    def __init__(self, raw_articles: list[RawArticle]):
        self.raw_articles = raw_articles
        self.clustered_articles: list[list[RawArticle]] = []
        self._embedding_model_name = "sentence-transformers/all-mpnet-base-v2"  # TODO - best one?

    def generate_clusters(self) -> list[list[RawArticle]]:
        if self.clustered_articles:
            return self.clustered_articles
        if not self.raw_articles:
            return []
        if len(self.raw_articles) == 1:
            return [[self.raw_articles]]
        logger.info(f"Generating clusters for {len(self.raw_articles)} articles...")
        # NOTE - given the weakness of news text generation via url it seems to be unrealiable to
        # generate embeddings with the raw article text. Instead we will use the article title which seems to perform well.
        # we will probably need to revisit this in the future. Possibly adding a portion of the article text to the title
        # could give the embedding even more context to cluster on.
        titles = [article.title for article in self.raw_articles]
        title_embeddings = self._generate_embeddings(titles)
        cluster_labels, n_clusters = self._cluster_embeddings(title_embeddings)
        self.clustered_articles = self._group_articles_by_cluster(
            self.raw_articles, cluster_labels, n_clusters
        )
        self.__log_cluster_stats(self.clustered_articles)
        return self.clustered_articles

    def __log_cluster_stats(self, clustered_articles: list[list[RawArticle]]):
        logger.info(f"Generated {len(clustered_articles)} clusters.")
        for cluster in clustered_articles:
            logger.info("==============Cluster==============\n")
            for cluster_article in cluster:
                logger.info(f"Title: {cluster_article.title}; Url: {cluster_article.url}")
            logger.info("\n")

    def _group_articles_by_cluster(
        self, articles: list[RawArticle], labels: list[int], n_clusters: int
    ) -> list[list[RawArticle]]:
        result = []
        for i in range(n_clusters):
            result.append([])
        for cluster_idx, article in zip(labels, articles):
            result[cluster_idx].append(article)
        return result

    @retry(wait=wait_random_exponential(multiplier=1, max=60), stop=stop_after_attempt(5))
    def _generate_embeddings(self, docs: list[str]) -> list[float]:
        embedding_model = HuggingFaceHubEmbeddings(
            repo_id=self._embedding_model_name,
            task="feature-extraction",
            huggingfacehub_api_token=huggingface_api_key,
        )
        # TODO - add timing metrics
        return embedding_model.embed_documents(docs)

    def _cluster_embeddings(self, embeddings: list[list[float]]) -> tuple[list[int], int]:
        range_n_clusters = range(2, len(embeddings))
        embeddings_np = np.array(embeddings, dtype=np.float32)
        silhouette_avg_scores = []
        iter_labels = []
        for n_clusters in range_n_clusters:
            # The silhouette coefficient can range from -1, 1
            # Initialize the clusterer with n_clusters value and a random generator
            # seed of 10 for reproducibility.
            clusterer = KMeans(n_clusters=n_clusters, n_init="auto", random_state=10)
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
        return max_silhouette_avg_labels, n_clusters
