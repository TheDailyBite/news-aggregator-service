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
    DATE_SORTING_STR,
    RELEVANCE_SORTING_STR,
    ResultRefTypes,
)
from news_aggregator_data_access_layer.utils.s3 import dt_to_lexicographic_date_s3_prefix

from news_aggregator_service.config import SOURCING_DEFAULT_TOP_K
from news_aggregator_service.sourcers.models.sourced_articles import SourcedArticle
from news_aggregator_service.utils.telemetry import setup_logger

logger = setup_logger(__name__)


class NaiveSourcer:
    def __init__(
        self,
        aggregation_dt: datetime,
        topics: list[str],
        s3_client: boto3.client = boto3.client(
            service_name="s3", region_name=REGION_NAME, endpoint_url=S3_ENDPOINT_URL
        ),
    ):
        self.aggregation_dt = aggregation_dt
        self.aggregation_date_str = dt_to_lexicographic_date_s3_prefix(aggregation_dt)
        self.s3_client = s3_client
        self.candidate_articles = CandidateArticles(ResultRefTypes.S3, self.aggregation_dt)
        self.topics = topics
        self.sorting = None
        self.aggregators: set[str] = set()
        self.article_inventory: dict[str, Any] = dict()
        self.sourced_articles: list[SourcedArticle] = []

    def _get_sorting_lambda(self, sorting: str) -> Any:
        if sorting == RELEVANCE_SORTING_STR:
            return lambda x: x.aggregation_index
        elif sorting == DATE_SORTING_STR:
            return lambda x: x.date_published
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
        """This populates the article inventory with the raw articles from the candidate articles bucket (raw candidate articles prefix)
        The goal of the article inventory is to provide an easy interfact to fetch articles for a given topic and category on a given day (e.g. top k).
        We know that for a particular aggregation day, there could be multiple aggregations for a particular topic and for a particular aggregator.
        The article inventory will be a dictionary of dictionaries.
        At a high-level data will be organized as follows:
        article_inventory = {
            topic_1: {
                category_1: {
                    aggregator_1: [article_1, article_2, ...], # the articles are sorted by aggregation_index and  for Relevance sorting; unsorted for date sorting
                    aggregator_2: [article_1, article_2, ...],
                    ...
                },
            },
            ...
        }
        """
        self.article_inventory = dict()
        self.aggregators = set()
        self.sorting = None
        for topic in self.topics:
            kwargs = {"s3_client": self.s3_client, "topic": topic}
            raw_articles = self.candidate_articles.load_articles(**kwargs)
            categories_for_topic = set()
            aggregators_for_topic = set()
            self.article_inventory[topic] = dict()
            # create inventory of categories and aggregators for topic
            for raw_article in raw_articles:
                categories_for_topic.add(raw_article.requested_category)
                aggregators_for_topic.add(raw_article.aggregator_id)
            self.aggregators = self.aggregators.union(aggregators_for_topic)
            for category in categories_for_topic:
                self.article_inventory[topic][category] = dict()
                for aggregator in aggregators_for_topic:
                    self.article_inventory[topic][category][aggregator] = []
            for raw_article in raw_articles:
                self.article_inventory[topic][raw_article.requested_category][
                    raw_article.aggregator_id
                ].append(raw_article)
            # theoretically different aggregation runs could have different sorting methods
            # we simplify this by assuming for a given day the sorting method is the same for all aggregations
            # sort the articles by aggregation_index for relevance sorting
            if raw_articles and not self.sorting:
                self.sorting = raw_articles[0].sorting
            for category in categories_for_topic:
                for aggregator in aggregators_for_topic:
                    self.article_inventory[topic][category][aggregator].sort(
                        key=self._get_sorting_lambda(self.sorting)  # type: ignore
                    )

    def source_articles(self, top_k: int = SOURCING_DEFAULT_TOP_K) -> list[SourcedArticle]:
        """This sources the articles from the article inventory.
        The goal of this method is to source the top k articles for each topic and category.
        Currently, the articles from different aggregators are treated equally and are sourced in a round-robin fashion,
        until we reach the top k articles for the topic and category.
        The articles are sourced from the article inventory.
        """
        logger.info(
            f"Sourcing top_k {top_k} articles for topics {self.topics} and respective categories..."
        )
        if not self.article_inventory:
            logger.info("Populating article inventory first since it is empty")
            self.populate_article_inventory()
        self.sourced_articles = []
        for topic in self.topics:
            for category in self.article_inventory[topic].keys():
                articles_for_topic = [
                    value
                    for values in self.article_inventory[topic][category].values()
                    for value in values
                ]
                sourcing_func, sorting_lambda = self._get_sourcing_func(self.sorting)  # type: ignore
                top_k_articles = sourcing_func(top_k, articles_for_topic, key=sorting_lambda)
                self.sourced_articles.extend(
                    [
                        SourcedArticle(
                            article, self.aggregation_date_str, topic, category, self.s3_client
                        )
                        for article in top_k_articles
                    ]
                )
        return self.sourced_articles

    def store_articles(self) -> None:
        for sourced_article in self.sourced_articles:
            sourced_article.store_article()
