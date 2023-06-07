from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from news_aggregator_data_access_layer.assets.news_assets import CandidateArticles, RawArticle

from news_aggregator_service.aggregators.news_aggregators import BingAggregator
from news_aggregator_service.config import BING_AGGREGATOR_ID

TEST_STORE_BUCKET = "test-store-bucket"
TEST_STORE_PATHS = "path1,path2"
TEST_PUBLISHED_DATE_STR = "2023-04-11T21:02:39+00:00"
TEST_DT = datetime(2023, 4, 11, 21, 2, 39, 4166)
TEST_AGGREGATION_RUN_ID = "test-aggregation-run-id"
TEST_RAW_ARTICLE_1 = RawArticle(
    article_id="1#test-article-id",
    aggregator_id=BING_AGGREGATOR_ID,
    dt_published=TEST_PUBLISHED_DATE_STR,
    aggregation_index=0,
    topic_id="topic_id",
    topic="topic",
    title="the article title",
    url="url",
    article_data="article_data",
    sorting="relevance",
)
TEST_AGGREGATED_CANDIDATES = [TEST_RAW_ARTICLE_1]


@pytest.fixture
def patched_bing_aggregator():
    with patch.object(BingAggregator, "get_api_key") as mocked_get_api_key:
        mocked_get_api_key.return_value = "test-api-key"
        return BingAggregator()


def test_bing_generate_article_id(patched_bing_aggregator):
    aggregator = patched_bing_aggregator
    article_idx = 1

    article_id = aggregator.generate_article_id(article_idx)

    assert isinstance(article_id, str)
    assert len(article_id) == 43
    assert article_id[:7] == f"00000{article_idx}#"


def test_bing_store_candidates(patched_bing_aggregator):
    aggregator = patched_bing_aggregator
    with patch.object(CandidateArticles, "store_articles") as mocked_store_articles:
        mocked_store_articles.return_value = (TEST_STORE_BUCKET, TEST_STORE_PATHS)
        actual_store_bucket, actual_store_paths = aggregator.store_candidates(
            TEST_AGGREGATED_CANDIDATES, TEST_DT, TEST_AGGREGATION_RUN_ID
        )
        assert actual_store_bucket == TEST_STORE_BUCKET
        assert actual_store_paths == TEST_STORE_PATHS


def test_bing_preprocess_articles_is_unique_article_check(patched_bing_aggregator):
    aggregator = patched_bing_aggregator
    articles = [
        MagicMock(date_published="dp1"),
        MagicMock(date_published="dp2"),
        MagicMock(date_published="dp3"),
    ]
    is_unique_article_se = [True, False, True]
    expected_preprocessed_articles = [articles[0], articles[2]]
    with patch.object(aggregator, "is_unique_article") as mocked_aggregator:
        mocked_aggregator.side_effect = is_unique_article_se
        actual_preprocessed_candidates = aggregator.preprocess_articles(articles, set())
        assert actual_preprocessed_candidates == expected_preprocessed_articles


def test_bing_preprocess_articles_is_unique_article_check_and_date_published(
    patched_bing_aggregator,
):
    aggregator = patched_bing_aggregator
    articles = [
        MagicMock(date_published="dp1"),
        MagicMock(date_published="dp2"),
        MagicMock(date_published=""),
    ]
    is_unique_article_se = [True, False, True]
    expected_preprocessed_articles = [articles[0]]
    with patch.object(aggregator, "is_unique_article") as mocked_aggregator:
        mocked_aggregator.side_effect = is_unique_article_se
        actual_preprocessed_candidates = aggregator.preprocess_articles(articles, set())
        assert actual_preprocessed_candidates == expected_preprocessed_articles
