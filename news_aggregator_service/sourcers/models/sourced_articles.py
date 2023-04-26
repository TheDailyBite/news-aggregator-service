from typing import Any, Dict, List, Mapping, Set, Tuple

from datetime import datetime

import boto3
from news_aggregator_data_access_layer.assets.news_assets import RawArticle
from news_aggregator_data_access_layer.config import (
    REGION_NAME,
    S3_ENDPOINT_URL,
    SOURCED_ARTICLES_S3_BUCKET,
)
from news_aggregator_data_access_layer.utils.s3 import (
    dt_to_lexicographic_date_s3_prefix,
    dt_to_lexicographic_s3_prefix,
    get_success_file,
    read_objects_from_prefix_with_extension,
    store_object_in_s3,
    store_success_file,
    success_file_exists_at_prefix,
)

from news_aggregator_service.utils.telemetry import setup_logger

logger = setup_logger(__name__)


class SourcedArticle:
    def __init__(
        self,
        raw_article: RawArticle,
        aggregation_date_str: str,
        topic: str,
        requested_category: str,
        s3_client: boto3.client = boto3.client(
            service_name="s3", region_name=REGION_NAME, endpoint_url=S3_ENDPOINT_URL
        ),
    ):
        if not isinstance(raw_article, RawArticle) or not raw_article:
            raise ValueError("raw_article must be of type RawArticle")
        self.raw_article = raw_article
        self.article_id = raw_article.article_id
        self.article_url = raw_article.url
        self.topic = topic
        self.requested_category = requested_category
        self.aggregation_date_str = aggregation_date_str
        self.sourced_candidate_articles_s3_extension = ".json"
        self.success_marker_fn = "__SUCCESS__"
        self.long_article_summary = None
        self.medium_article_summary = None
        self.short_article_summary = None

    def _get_sourced_candidates_s3_object_prefix(self) -> str:
        prefix = f"sourced_candidate_articles/{self.aggregation_date_str}/{self.topic}"
        if self.requested_category:
            prefix += f"/{self.requested_category}"
        return prefix

    def _get_sourced_candidate_article_s3_object_key(self) -> str:
        return f"{self._get_sourced_candidates_s3_object_prefix()}/{self.article_id}{self.sourced_candidate_articles_s3_extension}"

    def _process_article(self):
        pass

    def store_article(self):
        pass
