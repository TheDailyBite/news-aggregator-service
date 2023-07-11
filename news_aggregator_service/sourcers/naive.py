from typing import Any, Dict, List, Set, Tuple

import heapq
from collections.abc import Mapping
from datetime import datetime

import boto3
from news_aggregator_data_access_layer.assets.news_assets import CandidateArticles, RawArticle
from news_aggregator_data_access_layer.config import (
    REGION_NAME,
    S3_ENDPOINT_URL,
    SOURCED_ARTICLES_S3_BUCKET,
)
from news_aggregator_data_access_layer.constants import (
    ARTICLE_NOT_SOURCED_TAGS_FLAG,
    ARTICLE_SOURCED_TAGS_FLAG,
    DATE_SORTING_STR,
    RELEVANCE_SORTING_STR,
    ArticleApprovalStatus,
    ResultRefTypes,
)
from news_aggregator_data_access_layer.models.dynamodb import SourcedArticles, get_uuid4_attribute
from news_aggregator_data_access_layer.utils.s3 import dt_to_lexicographic_date_s3_prefix

from news_aggregator_service.sourcers.models.sourced_articles import (
    ArticleClusterGenerator,
    SourcedArticle,
)
from news_aggregator_service.utils.telemetry import setup_logger

logger = setup_logger(__name__)


class NaiveSourcer:
    def __init__(
        self,
        topic_id: str,
        topic: str,
        top_k: int,
        sourcing_date: datetime,
        daily_publishing_limit: int,
        s3_client: boto3.client = boto3.client(
            service_name="s3", region_name=REGION_NAME, endpoint_url=S3_ENDPOINT_URL
        ),
    ):
        self.topic_id = topic_id
        self.topic = topic
        self.top_k = top_k
        self.sourcing_date = sourcing_date
        self.sourcing_date_str = dt_to_lexicographic_date_s3_prefix(sourcing_date)
        self.daily_publishing_limit = daily_publishing_limit
        self.s3_client = s3_client
        # NOTE - we are using relevance sorting by default as date would bias towards latest articles (or oldest)
        self.sorting = RELEVANCE_SORTING_STR
        self.candidate_articles = CandidateArticles(ResultRefTypes.S3, topic_id)
        self.article_inventory: list[RawArticle] = []
        self.sourced_articles: list[SourcedArticle] = []

    def is_daily_publishing_limit_for_topic_reached(self) -> bool:
        """This checks if the daily publishing limit for the topic is reached"""
        published_articles_on_date_count = 0
        published_articles = SourcedArticles.lsi_1.query(
            self.topic_id, SourcedArticles.date_published == self.sourcing_date_str
        )
        for article in published_articles:
            if article.article_approval_status == ArticleApprovalStatus.APPROVED:
                published_articles_on_date_count += 1
        if published_articles_on_date_count >= self.daily_publishing_limit:
            return True
        return False

    def cluster_articles(self) -> list[list[RawArticle]]:
        """This clusters the articles in the article inventory into clusters of similar articles."""
        article_cluster_gen = ArticleClusterGenerator(self.article_inventory)
        return article_cluster_gen.generate_clusters()

    def _sort_clustered_articles(
        self, clustered_articles: list[list[RawArticle]]
    ) -> list[list[RawArticle]]:
        """This sorts the clustered articles based on the sorting criteria."""
        # currently clusters are sorted by size. A larger cluster is more likely to have more relevant articles.
        logger.info(
            f"Sorting {len(clustered_articles)} clusters of articles based on cluster size (largest first) prior to generating sourced articles."
        )
        sorted_clustered_articles = sorted(
            clustered_articles, key=len, reverse=True
        )  # largest cluster first
        return sorted_clustered_articles

    def generate_sourced_articles(
        self, clustered_articles: list[list[RawArticle]], sourcing_run_id: str
    ) -> None:
        """This generates the sourced articles from the clusters of articles."""
        self.sourced_articles = []
        sorted_clustered_articles = self._sort_clustered_articles(clustered_articles)
        for article_cluster in sorted_clustered_articles:
            if len(self.sourced_articles) >= self.top_k:
                logger.info(
                    f"Reached top_k limit of {self.top_k} sourced articles. Breaking out of sourcing loop."
                )
                break
            sourced_article = SourcedArticle(
                article_cluster,
                self.sourcing_date_str,
                self.topic_id,
                self.topic,
                sourcing_run_id,
                self.s3_client,
            )
            article_processing_cost = sourced_article.process_article()
            logger.info(
                f"Sourced article with id {sourced_article.sourced_article_id} had total processing cost: {article_processing_cost}"
            )
            # TODO - do rest of ops like uniqueness etc.
            self.sourced_articles.append(sourced_article)
        logger.info(
            f"Generated {len(self.sourced_articles)} sourced articles. Requested top_k: {self.top_k}"
        )

    def _get_sorting_lambda(self, sorting: str) -> Any:
        if sorting == RELEVANCE_SORTING_STR:
            return lambda x: x.aggregation_index
        elif sorting == DATE_SORTING_STR:
            return lambda x: datetime.fromisoformat(x.dt_published)
        else:
            raise ValueError(f"Invalid sorting {sorting}")

    def _get_sourcing_func(self, sorting: str) -> tuple[Any, Any]:
        if sorting == RELEVANCE_SORTING_STR:
            return (heapq.nsmallest, self._get_sorting_lambda(sorting))
        elif sorting == DATE_SORTING_STR:
            # for date we source latest articles preferrably
            return (heapq.nlargest, self._get_sorting_lambda(sorting))
        else:
            raise ValueError(f"Invalid sorting {sorting}")

    def populate_article_inventory(self) -> None:
        """This populates the article inventory with all the raw articles for a given topic_id on a certain publishing date that have yet to be considered for sourcing.
        (TODO - should we only mark as sourced those which we took? or even those we considered?)
        The articles will be sorted by the sorting criteria defined in the sourcer (self.sourcing).
        """
        self.article_inventory = []
        kwargs = {"s3_client": self.s3_client, "publishing_date": self.sourcing_date}
        # take only articles that have not been sourced yet
        articles = self.candidate_articles.load_articles(
            tag_filter_key=self.candidate_articles.is_sourced_article_tag_key,
            tag_filter_value=ARTICLE_NOT_SOURCED_TAGS_FLAG,
            **kwargs,
        )
        if not articles:
            logger.info(
                f"No articles found for topic {self.topic_id} on date {self.sourcing_date_str}"
            )
            return
        raw_articles, raw_articles_metadata, raw_articles_tags = (
            [a[i] for a in articles] for i in range(3)
        )
        logger.info(
            f"Loaded {len(raw_articles)} raw articles for topic {self.topic_id} on date {self.sourcing_date_str}"
        )
        for raw_article in raw_articles:
            self.article_inventory.append(raw_article)
        logger.info(
            f"Sorting {len(self.article_inventory)} articles in inventory by {self.sorting}"
        )
        sourcing_func, sorting_lambda = self._get_sourcing_func(self.sorting)
        self.article_inventory = sourcing_func(
            len(self.article_inventory), self.article_inventory, key=sorting_lambda
        )

    def source_articles(self) -> list[SourcedArticle]:
        """This sources the articles from the article inventory.
        TODO -
        The articles are sourced from the article inventory.
        """
        sourcing_run_id = get_uuid4_attribute()
        logger.info(
            f"Sourcing Run Id: {sourcing_run_id}. Sourcing top_k {self.top_k} articles for topic {self.topic_id} on date {self.sourcing_date_str}"
        )
        if self.is_daily_publishing_limit_for_topic_reached() is True:
            logger.info(f"Daily publishing limit reached for topic {self.topic_id}.")
            # TODO - emit metric
        if not self.article_inventory:
            logger.info("Populating article inventory first since it is empty")
            self.populate_article_inventory()
        # TODO - do we want a minumum?
        # if len(self.article_inventory) < MINIMUM_ARTICLE_INVENTORY_SIZE_TO_SOURCE:
        #     logger.info(
        #         f"Article inventory size {len(self.article_inventory)} is less than minimum article inventory size {MINIMUM_ARTICLE_INVENTORY_SIZE_TO_SOURCE}. Sourcing will occur at a later date when more candidates are available."
        #     )
        #     # TODO - pubish metric
        #     return self.sourced_articles
        clustered_articles: list[list[RawArticle]] = self.cluster_articles()
        self.generate_sourced_articles(clustered_articles, sourcing_run_id)
        return self.sourced_articles

    def store_articles(self) -> None:
        if not self.sourced_articles:
            return
        for sourced_article in self.sourced_articles:
            sourced_article.store_article()
        logger.info(
            f"Sourced articles stored for topic {self.topic_id}. Will mark articles considered as sourced in candidate articles."
        )
        kwargs = {
            "s3_client": self.s3_client,
            "articles": self.article_inventory,
            "updated_tag_value": ARTICLE_SOURCED_TAGS_FLAG,
        }
        self.candidate_articles.update_articles_is_sourced_tag(**kwargs)
