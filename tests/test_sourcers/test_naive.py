from typing import Any, List

from collections.abc import Mapping
from datetime import datetime
from unittest import mock

import pytest
from news_aggregator_data_access_layer.assets.news_assets import CandidateArticles, RawArticle
from news_aggregator_data_access_layer.config import CANDIDATE_ARTICLES_S3_BUCKET
from news_aggregator_data_access_layer.constants import (
    ALL_CATEGORIES_STR,
    DATE_SORTING_STR,
    RELEVANCE_SORTING_STR,
)
from news_aggregator_data_access_layer.utils.s3 import (
    dt_to_lexicographic_date_s3_prefix,
    dt_to_lexicographic_s3_prefix,
)

from news_aggregator_service.sourcers.naive import NaiveSourcer

TEST_DT_1 = datetime(2023, 4, 11, 21, 2, 39, 4166)
TEST_DT_2 = datetime(2023, 4, 11, 22, 2, 39, 4166)
TEST_DT_3 = datetime(2023, 4, 11, 22, 2, 45, 4166)
TEST_DT_4 = datetime(2023, 4, 11, 23, 2, 45, 4166)
TEST_PUBLISHED_DATE_1_STR = "2021-04-11T21:02:39+00:00"
TEST_PUBLISHED_DATE_2_STR = "2021-04-11T22:02:39+00:00"
TEST_PUBLISHED_DATE_3_STR = "2021-04-11T22:02:45+00:00"
TEST_PUBLISHED_DATE_4_STR = "2021-04-11T23:02:45+00:00"

TEST_TOPICS = ["topic_1", "topic_2", "topic_3"]
TEST_AGGREGATOR_ID_1 = "aggregator_id_1"
TEST_AGGREGATOR_ID_2 = "aggregator_id_2"
TEST_CATEGORY_1 = "category_1"
TEST_CATEGORY_2 = "category_2"


def test_naive_sourcer_init():
    test_s3_client = "s3_client"
    naive_sourcer = NaiveSourcer(TEST_DT_1, TEST_TOPICS, s3_client=test_s3_client)
    assert naive_sourcer.aggregation_dt == TEST_DT_1
    assert naive_sourcer.aggregation_date_str == dt_to_lexicographic_date_s3_prefix(TEST_DT_1)
    assert naive_sourcer.s3_client == test_s3_client
    assert isinstance(naive_sourcer.candidate_articles, CandidateArticles)
    assert naive_sourcer.topics == TEST_TOPICS
    assert naive_sourcer.sorting is None
    assert naive_sourcer.aggregators == set()
    assert naive_sourcer.article_inventory == dict()
    assert naive_sourcer.sourced_articles == []


def test_naive_sourcer_populate_article_inventory_no_articles():
    with mock.patch.object(CandidateArticles, "load_articles") as mock_load_articles:
        naive_sourcer = NaiveSourcer(TEST_DT_1, TEST_TOPICS)
        mock_load_articles.return_value = []
        naive_sourcer.populate_article_inventory()
        assert naive_sourcer.aggregators == set()
        assert naive_sourcer.article_inventory == {topic: {} for topic in TEST_TOPICS}


@pytest.mark.parametrize(
    "sorting",
    [
        (RELEVANCE_SORTING_STR),
        (DATE_SORTING_STR),
    ],
)
def test_naive_sourcer_populate_article_inventory_single_topic_no_category(sorting):
    raw_article_1_topic_0 = RawArticle(
        article_id="article_id_1",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_1_STR,
        aggregation_index=0,
        topic=TEST_TOPICS[0],
        title="the article title",
        url="url",
        article_data="article_data",
        sorting=sorting,
    )
    raw_article_2_topic_0 = RawArticle(
        article_id="article_id 2",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_2_STR,
        aggregation_index=1,
        topic=TEST_TOPICS[0],
        title="the article title 2",
        url="url 2",
        article_data="article_data 2",
        sorting=sorting,
    )
    raw_articles = [[raw_article_2_topic_0, raw_article_1_topic_0], [], []]
    # these are sorted
    expected_raw_articles_topic_0 = [raw_article_1_topic_0, raw_article_2_topic_0]
    with mock.patch.object(CandidateArticles, "load_articles") as mock_load_articles:
        naive_sourcer = NaiveSourcer(TEST_DT_1, TEST_TOPICS)
        mock_load_articles.side_effect = raw_articles
        naive_sourcer.populate_article_inventory()
        assert naive_sourcer.aggregators == {TEST_AGGREGATOR_ID_1}
        expected_article_inventory: Mapping[str, Any] = {topic: {} for topic in TEST_TOPICS}
        expected_article_inventory[TEST_TOPICS[0]][ALL_CATEGORIES_STR] = {
            TEST_AGGREGATOR_ID_1: expected_raw_articles_topic_0
        }
        assert naive_sourcer.article_inventory == expected_article_inventory


@pytest.mark.parametrize(
    "sorting",
    [
        (RELEVANCE_SORTING_STR),
        (DATE_SORTING_STR),
    ],
)
def test_naive_sourcer_populate_article_inventory_single_topic_multi_category(sorting):
    raw_article_1_topic_0_no_cat = RawArticle(
        article_id="article_id_1",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_1_STR,
        aggregation_index=0,
        topic=TEST_TOPICS[0],
        title="the article title",
        url="url",
        article_data="article_data",
        sorting=sorting,
    )
    raw_article_1_topic_0_cat_1 = RawArticle(
        article_id="article_id 2",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_1_STR,
        aggregation_index=0,
        topic=TEST_TOPICS[0],
        title="the article title 2",
        url="url 2",
        article_data="article_data 2",
        sorting=sorting,
        requested_category=TEST_CATEGORY_1,
    )
    raw_article_2_topic_0_cat_1 = RawArticle(
        article_id="article_id 2",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_2_STR,
        aggregation_index=1,
        topic=TEST_TOPICS[0],
        title="the article title 2",
        url="url 2",
        article_data="article_data 2",
        sorting=sorting,
        requested_category=TEST_CATEGORY_1,
    )
    raw_articles = [
        [raw_article_1_topic_0_no_cat, raw_article_1_topic_0_cat_1, raw_article_2_topic_0_cat_1],
        [],
        [],
    ]
    # these are sorted
    expected_raw_articles_topic_0_no_cat = [raw_article_1_topic_0_no_cat]
    expected_raw_articles_topic_0_cat_1 = [raw_article_1_topic_0_cat_1, raw_article_2_topic_0_cat_1]
    with mock.patch.object(CandidateArticles, "load_articles") as mock_load_articles:
        naive_sourcer = NaiveSourcer(TEST_DT_1, TEST_TOPICS)
        mock_load_articles.side_effect = raw_articles
        naive_sourcer.populate_article_inventory()
        assert naive_sourcer.aggregators == {TEST_AGGREGATOR_ID_1}
        expected_article_inventory: Mapping[str, Any] = {topic: {} for topic in TEST_TOPICS}
        expected_article_inventory[TEST_TOPICS[0]][ALL_CATEGORIES_STR] = {
            TEST_AGGREGATOR_ID_1: expected_raw_articles_topic_0_no_cat
        }
        expected_article_inventory[TEST_TOPICS[0]][TEST_CATEGORY_1] = {
            TEST_AGGREGATOR_ID_1: expected_raw_articles_topic_0_cat_1
        }
        assert naive_sourcer.article_inventory == expected_article_inventory


def test_naive_sourcer_populate_article_inventory_multi_topic_multi_category_multi_aggregator():
    raw_article_1_topic_0_cat_1_agg_1 = RawArticle(
        article_id="article_id 1",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_1_STR,
        aggregation_index=0,
        topic=TEST_TOPICS[0],
        title="the article title 2",
        url="url 2",
        article_data="article_data 2",
        sorting=RELEVANCE_SORTING_STR,
        requested_category=TEST_CATEGORY_1,
    )
    raw_article_2_topic_0_cat_2_agg_1 = RawArticle(
        article_id="article_id 2",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_2_STR,
        aggregation_index=0,
        topic=TEST_TOPICS[0],
        title="the article title 2",
        url="url 2",
        article_data="article_data 2",
        sorting=RELEVANCE_SORTING_STR,
        requested_category=TEST_CATEGORY_2,
    )
    raw_article_1_topic_1_cat_1_agg_1 = RawArticle(
        article_id="article_id 1",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_1_STR,
        aggregation_index=0,
        topic=TEST_TOPICS[1],
        title="the article title 2",
        url="url 2",
        article_data="article_data 2",
        sorting=RELEVANCE_SORTING_STR,
        requested_category=TEST_CATEGORY_1,
    )
    raw_article_2_topic_1_cat_1_agg_2 = RawArticle(
        article_id="article_id 2",
        aggregator_id=TEST_AGGREGATOR_ID_2,
        date_published=TEST_PUBLISHED_DATE_2_STR,
        aggregation_index=0,
        topic=TEST_TOPICS[1],
        title="the article title 2",
        url="url 2",
        article_data="article_data 2",
        sorting=RELEVANCE_SORTING_STR,
        requested_category=TEST_CATEGORY_1,
    )
    raw_articles = [
        [raw_article_1_topic_0_cat_1_agg_1, raw_article_2_topic_0_cat_2_agg_1],
        [raw_article_1_topic_1_cat_1_agg_1, raw_article_2_topic_1_cat_1_agg_2],
        [],
    ]
    # these are sorted
    expected_raw_articles_topic_0_cat_1 = [raw_article_1_topic_0_cat_1_agg_1]
    expected_raw_articles_topic_0_cat_2 = [raw_article_2_topic_0_cat_2_agg_1]
    expected_raw_articles_topic_1_cat_1_agg_1 = [raw_article_1_topic_1_cat_1_agg_1]
    expected_raw_articles_topic_1_cat_1_agg_2 = [raw_article_2_topic_1_cat_1_agg_2]
    with mock.patch.object(CandidateArticles, "load_articles") as mock_load_articles:
        naive_sourcer = NaiveSourcer(TEST_DT_1, TEST_TOPICS)
        mock_load_articles.side_effect = raw_articles
        naive_sourcer.populate_article_inventory()
        assert naive_sourcer.aggregators == {TEST_AGGREGATOR_ID_1, TEST_AGGREGATOR_ID_2}
        expected_article_inventory: Mapping[str, Any] = {topic: {} for topic in TEST_TOPICS}
        expected_article_inventory[TEST_TOPICS[0]][TEST_CATEGORY_1] = {
            TEST_AGGREGATOR_ID_1: expected_raw_articles_topic_0_cat_1
        }
        expected_article_inventory[TEST_TOPICS[0]][TEST_CATEGORY_2] = {
            TEST_AGGREGATOR_ID_1: expected_raw_articles_topic_0_cat_2
        }
        expected_article_inventory[TEST_TOPICS[1]][TEST_CATEGORY_1] = {
            TEST_AGGREGATOR_ID_1: expected_raw_articles_topic_1_cat_1_agg_1,
            TEST_AGGREGATOR_ID_2: expected_raw_articles_topic_1_cat_1_agg_2,
        }
        assert naive_sourcer.article_inventory == expected_article_inventory


@pytest.mark.parametrize(
    "sorting, top_k, expected_sourced_articles_idxs",
    [
        (RELEVANCE_SORTING_STR, 1, [0]),
        (DATE_SORTING_STR, 1, [2]),
        (RELEVANCE_SORTING_STR, 2, [0, 1]),
        (DATE_SORTING_STR, 2, [2, 1]),
        (RELEVANCE_SORTING_STR, 0, []),
        (DATE_SORTING_STR, 0, []),
        (RELEVANCE_SORTING_STR, 3, [0, 1, 2]),
        (DATE_SORTING_STR, 3, [2, 1, 0]),
        (RELEVANCE_SORTING_STR, 4, [0, 1, 2]),
        (DATE_SORTING_STR, 4, [2, 1, 0]),
    ],
)
def test_source_articles_single_topic_single_aggregator_no_category(
    sorting, top_k, expected_sourced_articles_idxs
):
    raw_article_1_topic_0 = RawArticle(
        article_id="article_id_1",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_1_STR,
        aggregation_index=0,
        topic=TEST_TOPICS[0],
        title="the article title",
        url="url",
        article_data="article_data",
        sorting=sorting,
    )
    raw_article_2_topic_0 = RawArticle(
        article_id="article_id 2",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_2_STR,
        aggregation_index=1,
        topic=TEST_TOPICS[0],
        title="the article title 2",
        url="url 2",
        article_data="article_data 2",
        sorting=sorting,
    )
    raw_article_3_topic_0 = RawArticle(
        article_id="article_id 3",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_3_STR,
        aggregation_index=2,
        topic=TEST_TOPICS[0],
        title="the article title 3",
        url="url 3",
        article_data="article_data 3",
        sorting=sorting,
    )
    raw_articles = [[raw_article_1_topic_0, raw_article_2_topic_0, raw_article_3_topic_0], [], []]
    # we only assert the raw article attribute in the sourced article
    expected_sourced_articles_raw_articles = [
        raw_articles[0][i] for i in expected_sourced_articles_idxs
    ]
    with mock.patch.object(CandidateArticles, "load_articles") as mock_load_articles:
        naive_sourcer = NaiveSourcer(TEST_DT_1, TEST_TOPICS)
        mock_load_articles.side_effect = raw_articles
        naive_sourcer.populate_article_inventory()
        actual_sourced_articles = naive_sourcer.source_articles(top_k=top_k)
        for expected_raw_article in expected_sourced_articles_raw_articles:
            assert any(
                expected_raw_article == actual_sourced_article.raw_article
                for actual_sourced_article in actual_sourced_articles
            )


def test_source_articles_single_topic_multi_agg_multi_category_relevance_sorting():
    top_k = 1
    raw_article_1_topic_0_cat_1_agg_1 = RawArticle(
        article_id="article_id 1",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_1_STR,
        aggregation_index=0,
        topic=TEST_TOPICS[0],
        title="the article title 2",
        url="url 2",
        article_data="article_data 2",
        sorting=RELEVANCE_SORTING_STR,
        requested_category=TEST_CATEGORY_1,
    )
    raw_article_2_topic_0_cat_2_agg_1 = RawArticle(
        article_id="article_id 2",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_2_STR,
        aggregation_index=0,
        topic=TEST_TOPICS[0],
        title="the article title 2",
        url="url 2",
        article_data="article_data 2",
        sorting=RELEVANCE_SORTING_STR,
        requested_category=TEST_CATEGORY_2,
    )
    raw_article_3_topic_0_cat_2_agg_1 = RawArticle(
        article_id="article_id 3",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_3_STR,
        aggregation_index=1,
        topic=TEST_TOPICS[0],
        title="the article title 3",
        url="url 3",
        article_data="article_data 3",
        sorting=RELEVANCE_SORTING_STR,
        requested_category=TEST_CATEGORY_2,
    )
    raw_article_4_topic_0_cat_2_agg_2 = RawArticle(
        article_id="article_id 4",
        aggregator_id=TEST_AGGREGATOR_ID_2,
        date_published=TEST_PUBLISHED_DATE_2_STR,
        aggregation_index=1,  # NOTE - this would typically be 0 for a different aggregator; I'm forcing it to be 1 to make the test deterministic
        topic=TEST_TOPICS[0],
        title="the article title 4",
        url="url 4",
        article_data="article_data 4",
        sorting=RELEVANCE_SORTING_STR,
        requested_category=TEST_CATEGORY_2,
    )
    raw_article_1_topic_1_cat_1_agg_1 = RawArticle(
        article_id="article_id 1",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_1_STR,
        aggregation_index=0,
        topic=TEST_TOPICS[1],
        title="the article title 2",
        url="url 2",
        article_data="article_data 2",
        sorting=RELEVANCE_SORTING_STR,
        requested_category=TEST_CATEGORY_1,
    )
    raw_article_2_topic_1_cat_1_agg_2 = RawArticle(
        article_id="article_id 2",
        aggregator_id=TEST_AGGREGATOR_ID_2,
        date_published=TEST_PUBLISHED_DATE_2_STR,
        aggregation_index=1,  # NOTE - this would typically be 0 for a different aggregator; I'm forcing it to be 1 to make the test deterministic
        topic=TEST_TOPICS[1],
        title="the article title 2",
        url="url 2",
        article_data="article_data 2",
        sorting=RELEVANCE_SORTING_STR,
        requested_category=TEST_CATEGORY_1,
    )
    raw_articles = [
        [
            raw_article_1_topic_0_cat_1_agg_1,
            raw_article_2_topic_0_cat_2_agg_1,
            raw_article_3_topic_0_cat_2_agg_1,
            raw_article_4_topic_0_cat_2_agg_2,
        ],
        [raw_article_1_topic_1_cat_1_agg_1, raw_article_2_topic_1_cat_1_agg_2],
        [],
    ]
    # we only assert the raw article attribute in the sourced article
    expected_sourced_articles_raw_articles = [
        raw_article_1_topic_0_cat_1_agg_1,
        raw_article_2_topic_0_cat_2_agg_1,
        raw_article_1_topic_1_cat_1_agg_1,
    ]
    with mock.patch.object(CandidateArticles, "load_articles") as mock_load_articles:
        naive_sourcer = NaiveSourcer(TEST_DT_1, TEST_TOPICS)
        mock_load_articles.side_effect = raw_articles
        naive_sourcer.populate_article_inventory()
        actual_sourced_articles = naive_sourcer.source_articles(top_k=top_k)
        for expected_raw_article in expected_sourced_articles_raw_articles:
            assert any(
                expected_raw_article == actual_sourced_article.raw_article
                for actual_sourced_article in actual_sourced_articles
            )


def test_source_articles_single_topic_multi_agg_multi_category_relevance_sorting_k_2():
    top_k = 2
    raw_article_1_topic_0_cat_1_agg_1 = RawArticle(
        article_id="article_id 1",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_1_STR,
        aggregation_index=0,
        topic=TEST_TOPICS[0],
        title="the article title 2",
        url="url 2",
        article_data="article_data 2",
        sorting=RELEVANCE_SORTING_STR,
        requested_category=TEST_CATEGORY_1,
    )
    raw_article_2_topic_0_cat_2_agg_1 = RawArticle(
        article_id="article_id 2",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_2_STR,
        aggregation_index=1,  # NOTE - this would typically be 0 for a different aggregator; I'm forcing it to be 1 to make the test deterministic
        topic=TEST_TOPICS[0],
        title="the article title 2",
        url="url 2",
        article_data="article_data 2",
        sorting=RELEVANCE_SORTING_STR,
        requested_category=TEST_CATEGORY_2,
    )
    raw_article_3_topic_0_cat_2_agg_1 = RawArticle(
        article_id="article_id 3",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_3_STR,
        aggregation_index=2,
        topic=TEST_TOPICS[0],
        title="the article title 3",
        url="url 3",
        article_data="article_data 3",
        sorting=RELEVANCE_SORTING_STR,
        requested_category=TEST_CATEGORY_2,
    )
    raw_article_4_topic_0_cat_2_agg_2 = RawArticle(
        article_id="article_id 4",
        aggregator_id=TEST_AGGREGATOR_ID_2,
        date_published=TEST_PUBLISHED_DATE_2_STR,
        aggregation_index=0,
        topic=TEST_TOPICS[0],
        title="the article title 4",
        url="url 4",
        article_data="article_data 4",
        sorting=RELEVANCE_SORTING_STR,
        requested_category=TEST_CATEGORY_2,
    )
    raw_article_1_topic_1_cat_1_agg_1 = RawArticle(
        article_id="article_id 1",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_1_STR,
        aggregation_index=1,  # NOTE - this would typically be 0 for a different aggregator; I'm forcing it to be 1 to make the test deterministic
        topic=TEST_TOPICS[1],
        title="the article title 2",
        url="url 2",
        article_data="article_data 2",
        sorting=RELEVANCE_SORTING_STR,
        requested_category=TEST_CATEGORY_1,
    )
    raw_article_2_topic_1_cat_1_agg_2 = RawArticle(
        article_id="article_id 2",
        aggregator_id=TEST_AGGREGATOR_ID_2,
        date_published=TEST_PUBLISHED_DATE_2_STR,
        aggregation_index=0,
        topic=TEST_TOPICS[1],
        title="the article title 2",
        url="url 2",
        article_data="article_data 2",
        sorting=RELEVANCE_SORTING_STR,
        requested_category=TEST_CATEGORY_1,
    )
    raw_articles = [
        [
            raw_article_1_topic_0_cat_1_agg_1,
            raw_article_2_topic_0_cat_2_agg_1,
            raw_article_3_topic_0_cat_2_agg_1,
            raw_article_4_topic_0_cat_2_agg_2,
        ],
        [raw_article_1_topic_1_cat_1_agg_1, raw_article_2_topic_1_cat_1_agg_2],
        [],
    ]
    # we only assert the raw article attribute in the sourced article
    expected_sourced_articles_raw_articles = [
        raw_article_1_topic_0_cat_1_agg_1,
        raw_article_4_topic_0_cat_2_agg_2,
        raw_article_2_topic_0_cat_2_agg_1,
        raw_article_2_topic_1_cat_1_agg_2,
        raw_article_1_topic_1_cat_1_agg_1,
    ]
    with mock.patch.object(CandidateArticles, "load_articles") as mock_load_articles:
        naive_sourcer = NaiveSourcer(TEST_DT_1, TEST_TOPICS)
        mock_load_articles.side_effect = raw_articles
        naive_sourcer.populate_article_inventory()
        actual_sourced_articles = naive_sourcer.source_articles(top_k=top_k)
        for expected_raw_article in expected_sourced_articles_raw_articles:
            assert any(
                expected_raw_article == actual_sourced_article.raw_article
                for actual_sourced_article in actual_sourced_articles
            )


def test_source_articles_single_topic_multi_agg_multi_category_date_sorting():
    top_k = 1
    raw_article_1_topic_0_cat_1_agg_1 = RawArticle(
        article_id="article_id 1",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_1_STR,
        aggregation_index=0,
        topic=TEST_TOPICS[0],
        title="the article title 2",
        url="url 2",
        article_data="article_data 2",
        sorting=DATE_SORTING_STR,
        requested_category=TEST_CATEGORY_1,
    )
    raw_article_2_topic_0_cat_2_agg_1 = RawArticle(
        article_id="article_id 2",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_2_STR,
        aggregation_index=0,
        topic=TEST_TOPICS[0],
        title="the article title 2",
        url="url 2",
        article_data="article_data 2",
        sorting=DATE_SORTING_STR,
        requested_category=TEST_CATEGORY_2,
    )
    raw_article_3_topic_0_cat_2_agg_1 = RawArticle(
        article_id="article_id 3",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_3_STR,
        aggregation_index=1,
        topic=TEST_TOPICS[0],
        title="the article title 3",
        url="url 3",
        article_data="article_data 3",
        sorting=DATE_SORTING_STR,
        requested_category=TEST_CATEGORY_2,
    )
    raw_article_4_topic_0_cat_2_agg_2 = RawArticle(
        article_id="article_id 4",
        aggregator_id=TEST_AGGREGATOR_ID_2,
        date_published=TEST_PUBLISHED_DATE_4_STR,
        aggregation_index=0,
        topic=TEST_TOPICS[0],
        title="the article title 4",
        url="url 4",
        article_data="article_data 4",
        sorting=DATE_SORTING_STR,
        requested_category=TEST_CATEGORY_2,
    )
    raw_article_1_topic_1_cat_1_agg_1 = RawArticle(
        article_id="article_id 1",
        aggregator_id=TEST_AGGREGATOR_ID_1,
        date_published=TEST_PUBLISHED_DATE_1_STR,
        aggregation_index=0,
        topic=TEST_TOPICS[1],
        title="the article title 2",
        url="url 2",
        article_data="article_data 2",
        sorting=DATE_SORTING_STR,
        requested_category=TEST_CATEGORY_1,
    )
    raw_article_2_topic_1_cat_1_agg_2 = RawArticle(
        article_id="article_id 2",
        aggregator_id=TEST_AGGREGATOR_ID_2,
        date_published=TEST_PUBLISHED_DATE_2_STR,
        aggregation_index=0,
        topic=TEST_TOPICS[1],
        title="the article title 2",
        url="url 2",
        article_data="article_data 2",
        sorting=DATE_SORTING_STR,
        requested_category=TEST_CATEGORY_1,
    )
    raw_articles = [
        [
            raw_article_1_topic_0_cat_1_agg_1,
            raw_article_2_topic_0_cat_2_agg_1,
            raw_article_3_topic_0_cat_2_agg_1,
            raw_article_4_topic_0_cat_2_agg_2,
        ],
        [raw_article_1_topic_1_cat_1_agg_1, raw_article_2_topic_1_cat_1_agg_2],
        [],
    ]
    # we only assert the raw article attribute in the sourced article
    expected_sourced_articles_raw_articles = [
        raw_article_1_topic_0_cat_1_agg_1,
        raw_article_4_topic_0_cat_2_agg_2,
        raw_article_2_topic_1_cat_1_agg_2,
    ]
    with mock.patch.object(CandidateArticles, "load_articles") as mock_load_articles:
        naive_sourcer = NaiveSourcer(TEST_DT_1, TEST_TOPICS)
        mock_load_articles.side_effect = raw_articles
        naive_sourcer.populate_article_inventory()
        actual_sourced_articles = naive_sourcer.source_articles(top_k=top_k)
        for expected_raw_article in expected_sourced_articles_raw_articles:
            assert any(
                expected_raw_article == actual_sourced_article.raw_article
                for actual_sourced_article in actual_sourced_articles
            )
