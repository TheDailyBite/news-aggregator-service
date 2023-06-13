from typing import Any, List

from collections.abc import Mapping
from datetime import datetime, timezone
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

# _1 is oldest, _4 is newest
TEST_DT_1 = datetime(2023, 4, 11, 21, 2, 39, 4166)
TEST_DT_2 = datetime(2023, 4, 11, 22, 2, 39, 4166)
TEST_DT_3 = datetime(2023, 4, 11, 22, 2, 45, 4166)
TEST_DT_4 = datetime(2023, 4, 11, 23, 2, 45, 4166)
TEST_PUBLISHED_DATE_1_STR = "2021-04-11T21:02:39+00:00"
TEST_PUBLISHED_DATE_2_STR = "2021-04-11T22:02:39+00:00"
TEST_PUBLISHED_DATE_3_STR = "2021-04-11T22:02:45+00:00"
TEST_PUBLISHED_DATE_4_STR = "2021-04-11T23:02:45+00:00"

TEST_SOURCING_DT = datetime(2023, 4, 11, tzinfo=timezone.utc)
TEST_SOURCING_DT_STR = "2023/04/11"

TEST_TOPIC_ID = "topic_id_1"
TEST_TOPIC = "topic_1"
TEST_AGGREGATOR_ID_1 = "aggregator_id_1"
TEST_AGGREGATOR_ID_2 = "aggregator_id_2"
TEST_CATEGORY_1 = "category_1"
TEST_CATEGORY_2 = "category_2"
TEST_PUBLISHING_DAILY_LIMIT_1 = 10
TEST_TOP_K = 5
TEST_ARTICLE_METADATA = dict()
TEST_ARTICLE_TAGS = dict()


def test_naive_sourcer_init():
    test_s3_client = "s3_client"
    naive_sourcer = NaiveSourcer(
        topic_id=TEST_TOPIC_ID,
        topic=TEST_TOPIC,
        category=TEST_CATEGORY_1,
        top_k=TEST_TOP_K,
        sourcing_date=TEST_SOURCING_DT,
        daily_publishing_limit=TEST_PUBLISHING_DAILY_LIMIT_1,
        s3_client=test_s3_client,
    )
    assert naive_sourcer.topic_id == TEST_TOPIC_ID
    assert naive_sourcer.topic == TEST_TOPIC
    assert naive_sourcer.category == TEST_CATEGORY_1
    assert naive_sourcer.top_k == TEST_TOP_K
    assert naive_sourcer.sourcing_date == TEST_SOURCING_DT
    assert naive_sourcer.sourcing_date_str == TEST_SOURCING_DT_STR
    assert naive_sourcer.daily_publishing_limit == TEST_PUBLISHING_DAILY_LIMIT_1
    assert naive_sourcer.s3_client == test_s3_client
    assert naive_sourcer.sorting == RELEVANCE_SORTING_STR
    assert isinstance(naive_sourcer.candidate_articles, CandidateArticles)
    assert naive_sourcer.article_inventory == []
    assert naive_sourcer.sourced_articles == []


def test_naive_sourcer_populate_article_inventory_no_articles():
    test_s3_client = "s3_client"
    with mock.patch.object(CandidateArticles, "load_articles") as mock_load_articles:
        naive_sourcer = NaiveSourcer(
            topic_id=TEST_TOPIC_ID,
            topic=TEST_TOPIC,
            category=TEST_CATEGORY_1,
            top_k=TEST_TOP_K,
            sourcing_date=TEST_SOURCING_DT,
            daily_publishing_limit=TEST_PUBLISHING_DAILY_LIMIT_1,
            s3_client=test_s3_client,
        )
        mock_load_articles.return_value = ([], dict(), dict())
        naive_sourcer.populate_article_inventory()
        assert naive_sourcer.article_inventory == []


def test_naive_sourcer_populate_article_inventory_relevance_sorting():
    test_s3_client = "s3_client"
    with mock.patch.object(CandidateArticles, "load_articles") as mock_load_articles:
        naive_sourcer = NaiveSourcer(
            topic_id=TEST_TOPIC_ID,
            topic=TEST_TOPIC,
            category=TEST_CATEGORY_1,
            top_k=TEST_TOP_K,
            sourcing_date=TEST_SOURCING_DT,
            daily_publishing_limit=TEST_PUBLISHING_DAILY_LIMIT_1,
            s3_client=test_s3_client,
        )
        naive_sourcer.sorting = RELEVANCE_SORTING_STR
        raw_article_1 = RawArticle(
            article_id="article_id_1",
            aggregator_id="aggregator_id",
            dt_published=TEST_PUBLISHED_DATE_3_STR,
            aggregation_index=1,
            topic_id=TEST_TOPIC_ID,
            topic="topic",
            title="the article title",
            url="url",
            article_data="article_data",
            sorting="some_sorting",
        )
        raw_article_2 = RawArticle(
            article_id="article_id_2",
            aggregator_id="aggregator_id",
            dt_published=TEST_PUBLISHED_DATE_2_STR,
            aggregation_index=0,
            topic_id=TEST_TOPIC_ID,
            topic="topic",
            title="the article title",
            url="url",
            article_data="article_data",
            sorting="some_sorting",
        )
        raw_article_3 = RawArticle(
            article_id="article_id_3",
            aggregator_id="aggregator_id",
            dt_published=TEST_PUBLISHED_DATE_1_STR,
            aggregation_index=2,
            topic_id=TEST_TOPIC_ID,
            topic="topic",
            title="the article title",
            url="url",
            article_data="article_data",
            sorting="some_sorting",
        )
        raw_articles = [raw_article_1, raw_article_2, raw_article_3]
        articles_metadata = [TEST_ARTICLE_METADATA, TEST_ARTICLE_METADATA, TEST_ARTICLE_METADATA]
        articles_tags = [TEST_ARTICLE_TAGS, TEST_ARTICLE_TAGS, TEST_ARTICLE_TAGS]
        mock_load_articles.return_value = [
            (raw_article, article_metadata, article_tag)
            for raw_article, article_metadata, article_tag in zip(
                raw_articles, articles_metadata, articles_tags
            )
        ]
        naive_sourcer.populate_article_inventory()
        assert naive_sourcer.article_inventory == [raw_article_2, raw_article_1, raw_article_3]


def test_naive_sourcer_populate_article_inventory_date_sorting():
    test_s3_client = "s3_client"
    with mock.patch.object(CandidateArticles, "load_articles") as mock_load_articles:
        naive_sourcer = NaiveSourcer(
            topic_id=TEST_TOPIC_ID,
            topic=TEST_TOPIC,
            category=TEST_CATEGORY_1,
            top_k=TEST_TOP_K,
            sourcing_date=TEST_SOURCING_DT,
            daily_publishing_limit=TEST_PUBLISHING_DAILY_LIMIT_1,
            s3_client=test_s3_client,
        )
        naive_sourcer.sorting = DATE_SORTING_STR
        raw_article_1 = RawArticle(
            article_id="article_id_1",
            aggregator_id="aggregator_id",
            dt_published=TEST_PUBLISHED_DATE_3_STR,
            aggregation_index=1,
            topic_id=TEST_TOPIC_ID,
            topic="topic",
            title="the article title",
            url="url",
            article_data="article_data",
            sorting="some_sorting",
        )
        raw_article_2 = RawArticle(
            article_id="article_id_2",
            aggregator_id="aggregator_id",
            dt_published=TEST_PUBLISHED_DATE_2_STR,
            aggregation_index=0,
            topic_id=TEST_TOPIC_ID,
            topic="topic",
            title="the article title",
            url="url",
            article_data="article_data",
            sorting="some_sorting",
        )
        raw_article_3 = RawArticle(
            article_id="article_id_3",
            aggregator_id="aggregator_id",
            dt_published=TEST_PUBLISHED_DATE_1_STR,
            aggregation_index=2,
            topic_id=TEST_TOPIC_ID,
            topic="topic",
            title="the article title",
            url="url",
            article_data="article_data",
            sorting="some_sorting",
        )
        raw_articles = [raw_article_1, raw_article_2, raw_article_3]
        articles_metadata = [TEST_ARTICLE_METADATA, TEST_ARTICLE_METADATA, TEST_ARTICLE_METADATA]
        articles_tags = [TEST_ARTICLE_TAGS, TEST_ARTICLE_TAGS, TEST_ARTICLE_TAGS]
        mock_load_articles.return_value = [
            (raw_article, article_metadata, article_tag)
            for raw_article, article_metadata, article_tag in zip(
                raw_articles, articles_metadata, articles_tags
            )
        ]
        naive_sourcer.populate_article_inventory()
        assert naive_sourcer.article_inventory == [raw_article_1, raw_article_2, raw_article_3]


# # @pytest.mark.parametrize(
# #     "sorting, top_k, expected_sourced_articles_idxs",
# #     [
# #         (RELEVANCE_SORTING_STR, 1, [0]),
# #         (DATE_SORTING_STR, 1, [2]),
# #         (RELEVANCE_SORTING_STR, 2, [0, 1]),
# #         (DATE_SORTING_STR, 2, [2, 1]),
# #         (RELEVANCE_SORTING_STR, 0, []),
# #         (DATE_SORTING_STR, 0, []),
# #         (RELEVANCE_SORTING_STR, 3, [0, 1, 2]),
# #         (DATE_SORTING_STR, 3, [2, 1, 0]),
# #         (RELEVANCE_SORTING_STR, 4, [0, 1, 2]),
# #         (DATE_SORTING_STR, 4, [2, 1, 0]),
# #     ],
# # )
# # def test_source_articles_single_topic_single_aggregator_no_category(
# #     sorting, top_k, expected_sourced_articles_idxs
# # ):
# #     raw_article_1_topic_0 = RawArticle(
# #         article_id="article_id_1",
# #         aggregator_id=TEST_AGGREGATOR_ID_1,
# #         dt_published=TEST_PUBLISHED_DATE_1_STR,
# #         aggregation_index=0,
# #         topic=TEST_TOPIC,
# #         title="the article title",
# #         url="url",
# #         article_data="article_data",
# #         sorting=sorting,
# #     )
# #     raw_article_2_topic_0 = RawArticle(
# #         article_id="article_id 2",
# #         aggregator_id=TEST_AGGREGATOR_ID_1,
# #         dt_published=TEST_PUBLISHED_DATE_2_STR,
# #         aggregation_index=1,
# #         topic=TEST_TOPIC,
# #         title="the article title 2",
# #         url="url 2",
# #         article_data="article_data 2",
# #         sorting=sorting,
# #     )
# #     raw_article_3_topic_0 = RawArticle(
# #         article_id="article_id 3",
# #         aggregator_id=TEST_AGGREGATOR_ID_1,
# #         dt_published=TEST_PUBLISHED_DATE_3_STR,
# #         aggregation_index=2,
# #         topic=TEST_TOPIC,
# #         title="the article title 3",
# #         url="url 3",
# #         article_data="article_data 3",
# #         sorting=sorting,
# #     )
# #     raw_articles = [[raw_article_1_topic_0, raw_article_2_topic_0, raw_article_3_topic_0], [], []]
# #     # we only assert the raw article attribute in the sourced article
# #     expected_sourced_articles_raw_articles = [
# #         raw_articles[0][i] for i in expected_sourced_articles_idxs
# #     ]
# #     with mock.patch.object(CandidateArticles, "load_articles") as mock_load_articles:
# #         naive_sourcer = NaiveSourcer(TEST_DT_1, TEST_TOPICS)
# #         mock_load_articles.side_effect = raw_articles
# #         naive_sourcer.populate_article_inventory()
# #         actual_sourced_articles = naive_sourcer.source_articles(top_k=top_k)
# #         for expected_raw_article in expected_sourced_articles_raw_articles:
# #             assert any(
# #                 expected_raw_article == actual_sourced_article.raw_article
# #                 for actual_sourced_article in actual_sourced_articles
# #             )


# # def test_source_articles_single_topic_multi_agg_multi_category_relevance_sorting():
# #     top_k = 1
# #     raw_article_1_topic_0_cat_1_agg_1 = RawArticle(
# #         article_id="article_id 1",
# #         aggregator_id=TEST_AGGREGATOR_ID_1,
# #         dt_published=TEST_PUBLISHED_DATE_1_STR,
# #         aggregation_index=0,
# #         topic=TEST_TOPIC,
# #         title="the article title 2",
# #         url="url 2",
# #         article_data="article_data 2",
# #         sorting=RELEVANCE_SORTING_STR,
# #         requested_category=TEST_CATEGORY_1,
# #     )
# #     raw_article_2_topic_0_cat_2_agg_1 = RawArticle(
# #         article_id="article_id 2",
# #         aggregator_id=TEST_AGGREGATOR_ID_1,
# #         dt_published=TEST_PUBLISHED_DATE_2_STR,
# #         aggregation_index=0,
# #         topic=TEST_TOPIC,
# #         title="the article title 2",
# #         url="url 2",
# #         article_data="article_data 2",
# #         sorting=RELEVANCE_SORTING_STR,
# #         requested_category=TEST_CATEGORY_2,
# #     )
# #     raw_article_3_topic_0_cat_2_agg_1 = RawArticle(
# #         article_id="article_id 3",
# #         aggregator_id=TEST_AGGREGATOR_ID_1,
# #         dt_published=TEST_PUBLISHED_DATE_3_STR,
# #         aggregation_index=1,
# #         topic=TEST_TOPIC,
# #         title="the article title 3",
# #         url="url 3",
# #         article_data="article_data 3",
# #         sorting=RELEVANCE_SORTING_STR,
# #         requested_category=TEST_CATEGORY_2,
# #     )
# #     raw_article_4_topic_0_cat_2_agg_2 = RawArticle(
# #         article_id="article_id 4",
# #         aggregator_id=TEST_AGGREGATOR_ID_2,
# #         dt_published=TEST_PUBLISHED_DATE_2_STR,
# #         aggregation_index=1,  # NOTE - this would typically be 0 for a different aggregator; I'm forcing it to be 1 to make the test deterministic
# #         topic=TEST_TOPIC,
# #         title="the article title 4",
# #         url="url 4",
# #         article_data="article_data 4",
# #         sorting=RELEVANCE_SORTING_STR,
# #         requested_category=TEST_CATEGORY_2,
# #     )
# #     raw_article_1_topic_1_cat_1_agg_1 = RawArticle(
# #         article_id="article_id 1",
# #         aggregator_id=TEST_AGGREGATOR_ID_1,
# #         dt_published=TEST_PUBLISHED_DATE_1_STR,
# #         aggregation_index=0,
# #         topic=TEST_TOPICS[1],
# #         title="the article title 2",
# #         url="url 2",
# #         article_data="article_data 2",
# #         sorting=RELEVANCE_SORTING_STR,
# #         requested_category=TEST_CATEGORY_1,
# #     )
# #     raw_article_2_topic_1_cat_1_agg_2 = RawArticle(
# #         article_id="article_id 2",
# #         aggregator_id=TEST_AGGREGATOR_ID_2,
# #         dt_published=TEST_PUBLISHED_DATE_2_STR,
# #         aggregation_index=1,  # NOTE - this would typically be 0 for a different aggregator; I'm forcing it to be 1 to make the test deterministic
# #         topic=TEST_TOPICS[1],
# #         title="the article title 2",
# #         url="url 2",
# #         article_data="article_data 2",
# #         sorting=RELEVANCE_SORTING_STR,
# #         requested_category=TEST_CATEGORY_1,
# #     )
# #     raw_articles = [
# #         [
# #             raw_article_1_topic_0_cat_1_agg_1,
# #             raw_article_2_topic_0_cat_2_agg_1,
# #             raw_article_3_topic_0_cat_2_agg_1,
# #             raw_article_4_topic_0_cat_2_agg_2,
# #         ],
# #         [raw_article_1_topic_1_cat_1_agg_1, raw_article_2_topic_1_cat_1_agg_2],
# #         [],
# #     ]
# #     # we only assert the raw article attribute in the sourced article
# #     expected_sourced_articles_raw_articles = [
# #         raw_article_1_topic_0_cat_1_agg_1,
# #         raw_article_2_topic_0_cat_2_agg_1,
# #         raw_article_1_topic_1_cat_1_agg_1,
# #     ]
# #     with mock.patch.object(CandidateArticles, "load_articles") as mock_load_articles:
# #         naive_sourcer = NaiveSourcer(TEST_DT_1, TEST_TOPICS)
# #         mock_load_articles.side_effect = raw_articles
# #         naive_sourcer.populate_article_inventory()
# #         actual_sourced_articles = naive_sourcer.source_articles(top_k=top_k)
# #         for expected_raw_article in expected_sourced_articles_raw_articles:
# #             assert any(
# #                 expected_raw_article == actual_sourced_article.raw_article
# #                 for actual_sourced_article in actual_sourced_articles
# #             )


# # def test_source_articles_single_topic_multi_agg_multi_category_relevance_sorting_k_2():
# #     top_k = 2
# #     raw_article_1_topic_0_cat_1_agg_1 = RawArticle(
# #         article_id="article_id 1",
# #         aggregator_id=TEST_AGGREGATOR_ID_1,
# #         dt_published=TEST_PUBLISHED_DATE_1_STR,
# #         aggregation_index=0,
# #         topic=TEST_TOPIC,
# #         title="the article title 2",
# #         url="url 2",
# #         article_data="article_data 2",
# #         sorting=RELEVANCE_SORTING_STR,
# #         requested_category=TEST_CATEGORY_1,
# #     )
# #     raw_article_2_topic_0_cat_2_agg_1 = RawArticle(
# #         article_id="article_id 2",
# #         aggregator_id=TEST_AGGREGATOR_ID_1,
# #         dt_published=TEST_PUBLISHED_DATE_2_STR,
# #         aggregation_index=1,  # NOTE - this would typically be 0 for a different aggregator; I'm forcing it to be 1 to make the test deterministic
# #         topic=TEST_TOPIC,
# #         title="the article title 2",
# #         url="url 2",
# #         article_data="article_data 2",
# #         sorting=RELEVANCE_SORTING_STR,
# #         requested_category=TEST_CATEGORY_2,
# #     )
# #     raw_article_3_topic_0_cat_2_agg_1 = RawArticle(
# #         article_id="article_id 3",
# #         aggregator_id=TEST_AGGREGATOR_ID_1,
# #         dt_published=TEST_PUBLISHED_DATE_3_STR,
# #         aggregation_index=2,
# #         topic=TEST_TOPIC,
# #         title="the article title 3",
# #         url="url 3",
# #         article_data="article_data 3",
# #         sorting=RELEVANCE_SORTING_STR,
# #         requested_category=TEST_CATEGORY_2,
# #     )
# #     raw_article_4_topic_0_cat_2_agg_2 = RawArticle(
# #         article_id="article_id 4",
# #         aggregator_id=TEST_AGGREGATOR_ID_2,
# #         dt_published=TEST_PUBLISHED_DATE_2_STR,
# #         aggregation_index=0,
# #         topic=TEST_TOPIC,
# #         title="the article title 4",
# #         url="url 4",
# #         article_data="article_data 4",
# #         sorting=RELEVANCE_SORTING_STR,
# #         requested_category=TEST_CATEGORY_2,
# #     )
# #     raw_article_1_topic_1_cat_1_agg_1 = RawArticle(
# #         article_id="article_id 1",
# #         aggregator_id=TEST_AGGREGATOR_ID_1,
# #         dt_published=TEST_PUBLISHED_DATE_1_STR,
# #         aggregation_index=1,  # NOTE - this would typically be 0 for a different aggregator; I'm forcing it to be 1 to make the test deterministic
# #         topic=TEST_TOPICS[1],
# #         title="the article title 2",
# #         url="url 2",
# #         article_data="article_data 2",
# #         sorting=RELEVANCE_SORTING_STR,
# #         requested_category=TEST_CATEGORY_1,
# #     )
# #     raw_article_2_topic_1_cat_1_agg_2 = RawArticle(
# #         article_id="article_id 2",
# #         aggregator_id=TEST_AGGREGATOR_ID_2,
# #         dt_published=TEST_PUBLISHED_DATE_2_STR,
# #         aggregation_index=0,
# #         topic=TEST_TOPICS[1],
# #         title="the article title 2",
# #         url="url 2",
# #         article_data="article_data 2",
# #         sorting=RELEVANCE_SORTING_STR,
# #         requested_category=TEST_CATEGORY_1,
# #     )
# #     raw_articles = [
# #         [
# #             raw_article_1_topic_0_cat_1_agg_1,
# #             raw_article_2_topic_0_cat_2_agg_1,
# #             raw_article_3_topic_0_cat_2_agg_1,
# #             raw_article_4_topic_0_cat_2_agg_2,
# #         ],
# #         [raw_article_1_topic_1_cat_1_agg_1, raw_article_2_topic_1_cat_1_agg_2],
# #         [],
# #     ]
# #     # we only assert the raw article attribute in the sourced article
# #     expected_sourced_articles_raw_articles = [
# #         raw_article_1_topic_0_cat_1_agg_1,
# #         raw_article_4_topic_0_cat_2_agg_2,
# #         raw_article_2_topic_0_cat_2_agg_1,
# #         raw_article_2_topic_1_cat_1_agg_2,
# #         raw_article_1_topic_1_cat_1_agg_1,
# #     ]
# #     with mock.patch.object(CandidateArticles, "load_articles") as mock_load_articles:
# #         naive_sourcer = NaiveSourcer(TEST_DT_1, TEST_TOPICS)
# #         mock_load_articles.side_effect = raw_articles
# #         naive_sourcer.populate_article_inventory()
# #         actual_sourced_articles = naive_sourcer.source_articles(top_k=top_k)
# #         for expected_raw_article in expected_sourced_articles_raw_articles:
# #             assert any(
# #                 expected_raw_article == actual_sourced_article.raw_article
# #                 for actual_sourced_article in actual_sourced_articles
# #             )


# # def test_source_articles_single_topic_multi_agg_multi_category_date_sorting():
# #     top_k = 1
# #     raw_article_1_topic_0_cat_1_agg_1 = RawArticle(
# #         article_id="article_id 1",
# #         aggregator_id=TEST_AGGREGATOR_ID_1,
# #         dt_published=TEST_PUBLISHED_DATE_1_STR,
# #         aggregation_index=0,
# #         topic=TEST_TOPIC,
# #         title="the article title 2",
# #         url="url 2",
# #         article_data="article_data 2",
# #         sorting=DATE_SORTING_STR,
# #         requested_category=TEST_CATEGORY_1,
# #     )
# #     raw_article_2_topic_0_cat_2_agg_1 = RawArticle(
# #         article_id="article_id 2",
# #         aggregator_id=TEST_AGGREGATOR_ID_1,
# #         dt_published=TEST_PUBLISHED_DATE_2_STR,
# #         aggregation_index=0,
# #         topic=TEST_TOPIC,
# #         title="the article title 2",
# #         url="url 2",
# #         article_data="article_data 2",
# #         sorting=DATE_SORTING_STR,
# #         requested_category=TEST_CATEGORY_2,
# #     )
# #     raw_article_3_topic_0_cat_2_agg_1 = RawArticle(
# #         article_id="article_id 3",
# #         aggregator_id=TEST_AGGREGATOR_ID_1,
# #         dt_published=TEST_PUBLISHED_DATE_3_STR,
# #         aggregation_index=1,
# #         topic=TEST_TOPIC,
# #         title="the article title 3",
# #         url="url 3",
# #         article_data="article_data 3",
# #         sorting=DATE_SORTING_STR,
# #         requested_category=TEST_CATEGORY_2,
# #     )
# #     raw_article_4_topic_0_cat_2_agg_2 = RawArticle(
# #         article_id="article_id 4",
# #         aggregator_id=TEST_AGGREGATOR_ID_2,
# #         dt_published=TEST_PUBLISHED_DATE_4_STR,
# #         aggregation_index=0,
# #         topic=TEST_TOPIC,
# #         title="the article title 4",
# #         url="url 4",
# #         article_data="article_data 4",
# #         sorting=DATE_SORTING_STR,
# #         requested_category=TEST_CATEGORY_2,
# #     )
# #     raw_article_1_topic_1_cat_1_agg_1 = RawArticle(
# #         article_id="article_id 1",
# #         aggregator_id=TEST_AGGREGATOR_ID_1,
# #         dt_published=TEST_PUBLISHED_DATE_1_STR,
# #         aggregation_index=0,
# #         topic=TEST_TOPICS[1],
# #         title="the article title 2",
# #         url="url 2",
# #         article_data="article_data 2",
# #         sorting=DATE_SORTING_STR,
# #         requested_category=TEST_CATEGORY_1,
# #     )
# #     raw_article_2_topic_1_cat_1_agg_2 = RawArticle(
# #         article_id="article_id 2",
# #         aggregator_id=TEST_AGGREGATOR_ID_2,
# #         dt_published=TEST_PUBLISHED_DATE_2_STR,
# #         aggregation_index=0,
# #         topic=TEST_TOPICS[1],
# #         title="the article title 2",
# #         url="url 2",
# #         article_data="article_data 2",
# #         sorting=DATE_SORTING_STR,
# #         requested_category=TEST_CATEGORY_1,
# #     )
# #     raw_articles = [
# #         [
# #             raw_article_1_topic_0_cat_1_agg_1,
# #             raw_article_2_topic_0_cat_2_agg_1,
# #             raw_article_3_topic_0_cat_2_agg_1,
# #             raw_article_4_topic_0_cat_2_agg_2,
# #         ],
# #         [raw_article_1_topic_1_cat_1_agg_1, raw_article_2_topic_1_cat_1_agg_2],
# #         [],
# #     ]
# #     # we only assert the raw article attribute in the sourced article
# #     expected_sourced_articles_raw_articles = [
# #         raw_article_1_topic_0_cat_1_agg_1,
# #         raw_article_4_topic_0_cat_2_agg_2,
# #         raw_article_2_topic_1_cat_1_agg_2,
# #     ]
# #     with mock.patch.object(CandidateArticles, "load_articles") as mock_load_articles:
# #         naive_sourcer = NaiveSourcer(TEST_DT_1, TEST_TOPICS)
# #         mock_load_articles.side_effect = raw_articles
# #         naive_sourcer.populate_article_inventory()
# #         actual_sourced_articles = naive_sourcer.source_articles(top_k=top_k)
# #         for expected_raw_article in expected_sourced_articles_raw_articles:
# #             assert any(
# #                 expected_raw_article == actual_sourced_article.raw_article
# #                 for actual_sourced_article in actual_sourced_articles
# #             )
