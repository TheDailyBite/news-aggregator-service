from typing import Any, List

from collections.abc import Mapping
from datetime import datetime
from unittest import mock

import pytest
from news_aggregator_data_access_layer.assets.news_assets import RawArticle
from news_aggregator_data_access_layer.constants import (
    ALL_CATEGORIES_STR,
    DATE_SORTING_STR,
    RELEVANCE_SORTING_STR,
)
from news_aggregator_data_access_layer.utils.s3 import (
    dt_to_lexicographic_date_s3_prefix,
    dt_to_lexicographic_s3_prefix,
)

from news_aggregator_service.sourcers.models.sourced_articles import SourcedArticle

TEST_DT_1 = datetime(2023, 4, 11, 21, 2, 39, 4166)
TEST_DT_2 = datetime(2023, 4, 11, 22, 2, 39, 4166)
TEST_DT_3 = datetime(2023, 4, 11, 22, 2, 45, 4166)
TEST_DT_4 = datetime(2023, 4, 11, 23, 2, 45, 4166)
TEST_DT_1_STR = dt_to_lexicographic_s3_prefix(TEST_DT_1)
TEST_DT_2_STR = dt_to_lexicographic_s3_prefix(TEST_DT_2)
TEST_DT_3_STR = dt_to_lexicographic_s3_prefix(TEST_DT_3)
TEST_DT_4_STR = dt_to_lexicographic_s3_prefix(TEST_DT_4)

TEST_TOPICS = ["topic_1", "topic_2", "topic_3"]
TEST_AGGREGATOR_ID_1 = "aggregator_id_1"
TEST_AGGREGATOR_ID_2 = "aggregator_id_2"
TEST_CATEGORY_1 = "category_1"
TEST_CATEGORY_2 = "category_2"


def test_sourced_article_init():
    test_s3_client = "s3_client"
    raw_article_0 = RawArticle(
        article_id="article_id_1",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_DT_1_STR,
        aggregation_index=0,
        topic=TEST_TOPICS[0],
        title="the article title",
        url="url",
        article_data="article_data",
        sorting=DATE_SORTING_STR,
        category=TEST_CATEGORY_1,
    )
    sourced_article = SourcedArticle(
        raw_article_0, TEST_DT_1_STR, TEST_TOPICS[0], ALL_CATEGORIES_STR, s3_client=test_s3_client
    )
    assert sourced_article.raw_article == raw_article_0
    assert sourced_article.article_id == raw_article_0.article_id
    assert sourced_article.article_url == raw_article_0.url
    assert sourced_article.topic == raw_article_0.topic
    assert sourced_article.requested_category == ALL_CATEGORIES_STR
    assert sourced_article.category == TEST_CATEGORY_1
    assert sourced_article.aggregation_date_str == TEST_DT_1_STR
    assert sourced_article.long_article_summary is None
    assert sourced_article.long_article_summary is None
    assert sourced_article.long_article_summary is None
    assert sourced_article._summarization_prompt_template is not None
    assert sourced_article._summarization_llm_chain is not None
