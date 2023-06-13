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

from news_aggregator_service.constants import ARTICLE_SEPARATOR
from news_aggregator_service.sourcers.models.sourced_articles import (
    ArticleClusterGenerator,
    SourcedArticle,
)

TEST_SOURCING_RUN_ID = "test_sourcing_run_id"
TEST_DT_1 = datetime(2023, 4, 11, 21, 2, 39, 4166)
TEST_DT_2 = datetime(2023, 4, 11, 22, 2, 39, 4166)
TEST_DT_3 = datetime(2023, 4, 11, 22, 2, 45, 4166)
TEST_DT_4 = datetime(2023, 4, 11, 23, 2, 45, 4166)
TEST_PUBLISHED_DATE_1_STR = "2021-04-11T21:02:39+00:00"
TEST_DT_1_STR = dt_to_lexicographic_s3_prefix(TEST_DT_1)
TEST_DT_2_STR = dt_to_lexicographic_s3_prefix(TEST_DT_2)
TEST_DT_3_STR = dt_to_lexicographic_s3_prefix(TEST_DT_3)
TEST_DT_4_STR = dt_to_lexicographic_s3_prefix(TEST_DT_4)

TEST_TOPIC_IDS = ["topic_id_1", "topic_id_2", "topic_id_3"]
TEST_TOPICS = ["topic_1", "topic_2", "topic_3"]
TEST_AGGREGATOR_ID_1 = "aggregator_id_1"
TEST_AGGREGATOR_ID_2 = "aggregator_id_2"
TEST_CATEGORY_1 = "category_1"
TEST_CATEGORY_2 = "category_2"

# approximate # of tokens
TEST_TEXT_500_TOKENS = "In the heart of a bustling metropolis, the vibrant city streets were filled with a symphony of sounds and colors. Pedestrians hurried along the sidewalks, their footsteps echoing against the towering skyscrapers that reached towards the heavens. The air was tinged with the scent of freshly brewed coffee from the nearby cafes, intermingling with the aroma of street food wafting from the bustling market stalls. People from all walks of life intertwined, creating a tapestry of diversity and unity. Business executives in sleek suits rushed past street performers, their melodies blending with the honking of car horns and the chatter of passersby. The city was alive with energy, a pulsating rhythm that seemed to emanate from every corner. Amidst the urban chaos, hidden pockets of tranquility could be found—a serene park with blooming cherry blossoms, a hidden alleyway filled with vibrant street art. As night fell, the city transformed into a mesmerizing kaleidoscope of neon lights, casting a magical glow upon the streets below. From rooftop bars, people gazed at the twinkling stars above, a reminder of the vast universe beyond the city's borders. In this bustling urban jungle, dreams were born and shattered, opportunities seized and missed. It was a place where the pursuit of success and the quest for happiness intertwined, a constant dance between ambition and contentment. As the city never slept, its residents carried their hopes and aspirations through the sleepless nights, chasing after their dreams with unwavering determination. This was a city that embraced both the highs and lows of life, a city that nurtured resilience and creativity. It was a city that never ceased to amaze, always evolving and reinventing itself, yet staying true to its core. The city was a testament to the human spirit, a living embodiment of the dreams and aspirations that resided within each individual who called it home."
TEST_TEXT_250_TOKENS_1 = "In the heart of a bustling metropolis, the vibrant city streets were filled with a symphony of sounds and colors. Pedestrians hurried along the sidewalks, their footsteps echoing against the towering skyscrapers that reached towards the heavens. The air was tinged with the scent of freshly brewed coffee from the nearby cafes, intermingling with the aroma of street food wafting from the bustling market stalls. People from all walks of life intertwined, creating a tapestry of diversity and unity. Business executives in sleek suits rushed past street performers, their melodies blending with the honking of car horns and the chatter of passersby. The city was alive with energy, a pulsating rhythm that seemed to emanate from every corner. Amidst the urban chaos, hidden pockets of tranquility could be found—a serene park with blooming cherry blossoms, a hidden alleyway filled with vibrant street art. As night fell, the city transformed into a mesmerizing kaleidoscope of neon lights, casting a magical glow upon the streets below. From rooftop bars, people gazed at the twinkling stars above, a reminder of the vast universe beyond the city's borders. In this bustling urban jungle, dreams were born and shattered, opportunities seized and missed"
TEST_TEXT_250_TOKENS_2 = "It was a place where the pursuit of success and the quest for happiness intertwined, a constant dance between ambition and contentment. As the city never slept, its residents carried their hopes and aspirations through the sleepless nights, chasing after their dreams with unwavering determination. This was a city that embraced both the highs and lows of life, a city that nurtured resilience and creativity. It was a city that never ceased to amaze, always evolving and reinventing itself, yet staying true to its core. The city was a testament to the human spirit, a living embodiment of the dreams and aspirations that resided within each individual who called it home."

TEST_TEXT_4_TOKENS = "Hello world good morning"
TEST_TEXT_2_TOKENS = "My house"
TEST_TEXT_3_TOKENS = "The brown fox"


def test_sourced_article_init():
    test_s3_client = "s3_client"
    article_cluster = [
        RawArticle(
            article_id="article_id_1",
            aggregator_id=TEST_AGGREGATOR_ID_1,
            dt_published=TEST_PUBLISHED_DATE_1_STR,
            aggregation_index=0,
            topic_id=TEST_TOPIC_IDS[0],
            topic=TEST_TOPICS[0],
            title="the article title",
            url="url",
            article_data="article_data",
            sorting=DATE_SORTING_STR,
            category=TEST_CATEGORY_1,
        )
    ]
    sourced_article = SourcedArticle(
        article_cluster,
        TEST_DT_1_STR,
        TEST_TOPIC_IDS[0],
        TEST_TOPICS[0],
        ALL_CATEGORIES_STR,
        TEST_SOURCING_RUN_ID,
        s3_client=test_s3_client,
    )
    assert sourced_article.article_cluster == article_cluster
    assert sourced_article.source_article_ids == [a.article_id for a in article_cluster]
    assert sourced_article.publishing_date_str == TEST_DT_1_STR
    assert sourced_article.topic_id == TEST_TOPIC_IDS[0]
    assert sourced_article.topic == TEST_TOPICS[0]
    assert sourced_article.requested_category == ALL_CATEGORIES_STR
    assert sourced_article.s3_client == test_s3_client
    assert sourced_article.full_article_summary is None
    assert sourced_article.medium_article_summary is None
    assert sourced_article.short_article_summary is None
    # TODO -
    # assert sourced_article._full_summarization_prompt_template is not None
    # assert sourced_article._combine_full_summaries_prompt_template is not None
    # assert sourced_article._full_summarization_llm_chain is not None
    # assert sourced_article.is_processed is False


def test_sourced_article__chunk_text_in_docs_same_docs_equal():
    test_s3_client = "s3_client"
    article_cluster = [
        RawArticle(
            article_id="article_id_1",
            aggregator_id=TEST_AGGREGATOR_ID_1,
            dt_published=TEST_PUBLISHED_DATE_1_STR,
            aggregation_index=0,
            topic_id=TEST_TOPIC_IDS[0],
            topic=TEST_TOPICS[0],
            title="the article title",
            url="url",
            article_data="article_data",
            sorting=DATE_SORTING_STR,
            category=TEST_CATEGORY_1,
        )
    ]
    sourced_article = SourcedArticle(
        article_cluster,
        TEST_DT_1_STR,
        TEST_TOPIC_IDS[0],
        TEST_TOPICS[0],
        ALL_CATEGORIES_STR,
        TEST_SOURCING_RUN_ID,
        s3_client=test_s3_client,
    )
    sourced_article.text_chunk_token_length = 250
    texts = [TEST_TEXT_500_TOKENS, TEST_TEXT_500_TOKENS, TEST_TEXT_500_TOKENS]
    actual_docs = sourced_article._chunk_text_in_docs(texts)
    assert len(actual_docs) == 2
    assert actual_docs[0].page_content.count(TEST_TEXT_250_TOKENS_1) == 3
    assert actual_docs[0].page_content.count(TEST_TEXT_250_TOKENS_2) == 0
    assert actual_docs[1].page_content.count(TEST_TEXT_250_TOKENS_2) == 3
    assert actual_docs[1].page_content.count(TEST_TEXT_250_TOKENS_1) == 0
    assert actual_docs[0].page_content.count(ARTICLE_SEPARATOR) == 2
    assert actual_docs[1].page_content.count(ARTICLE_SEPARATOR) == 2


def test_sourced_article__chunk_text_in_docs_same_docs_unequal():
    test_s3_client = "s3_client"
    article_cluster = [
        RawArticle(
            article_id="article_id_1",
            aggregator_id=TEST_AGGREGATOR_ID_1,
            dt_published=TEST_PUBLISHED_DATE_1_STR,
            aggregation_index=0,
            topic_id=TEST_TOPIC_IDS[0],
            topic=TEST_TOPICS[0],
            title="the article title",
            url="url",
            article_data="article_data",
            sorting=DATE_SORTING_STR,
            category=TEST_CATEGORY_1,
        )
    ]
    sourced_article = SourcedArticle(
        article_cluster,
        TEST_DT_1_STR,
        TEST_TOPIC_IDS[0],
        TEST_TOPICS[0],
        ALL_CATEGORIES_STR,
        TEST_SOURCING_RUN_ID,
        s3_client=test_s3_client,
    )
    sourced_article.text_chunk_token_length = 250
    texts = [TEST_TEXT_500_TOKENS, TEST_TEXT_250_TOKENS_1]
    actual_docs = sourced_article._chunk_text_in_docs(texts)
    assert len(actual_docs) == 2
    assert TEST_TEXT_250_TOKENS_1 in actual_docs[0].page_content
    assert TEST_TEXT_250_TOKENS_2 not in actual_docs[0].page_content
    assert TEST_TEXT_250_TOKENS_2 in actual_docs[1].page_content
    assert TEST_TEXT_250_TOKENS_1 not in actual_docs[1].page_content


def test_sourced_article__chunk_text_in_docs_different_docs():
    test_s3_client = "s3_client"
    article_cluster = [
        RawArticle(
            article_id="article_id_1",
            aggregator_id=TEST_AGGREGATOR_ID_1,
            dt_published=TEST_PUBLISHED_DATE_1_STR,
            aggregation_index=0,
            topic_id=TEST_TOPIC_IDS[0],
            topic=TEST_TOPICS[0],
            title="the article title",
            url="url",
            article_data="article_data",
            sorting=DATE_SORTING_STR,
            category=TEST_CATEGORY_1,
        )
    ]
    sourced_article = SourcedArticle(
        article_cluster,
        TEST_DT_1_STR,
        TEST_TOPIC_IDS[0],
        TEST_TOPICS[0],
        ALL_CATEGORIES_STR,
        TEST_SOURCING_RUN_ID,
        s3_client=test_s3_client,
    )
    sourced_article.text_chunk_token_length = 2
    texts = [TEST_TEXT_4_TOKENS, TEST_TEXT_2_TOKENS, TEST_TEXT_3_TOKENS]
    actual_docs = sourced_article._chunk_text_in_docs(texts)
    assert len(actual_docs) == 2
    doc_1_text_list = ["Hello world", "My house", "The brown"]
    doc_1_text = ARTICLE_SEPARATOR.join(doc_1_text_list)
    # the tokenizer includes a space before each token chunk
    doc_2_text_list = [" good morning", " fox"]
    doc_2_text = ARTICLE_SEPARATOR.join(doc_2_text_list)
    assert actual_docs[0].page_content == doc_1_text
    assert actual_docs[1].page_content == doc_2_text


def test_article_cluster_generator_init():
    raw_articles = [
        RawArticle(
            article_id="article_id_1",
            aggregator_id=TEST_AGGREGATOR_ID_1,
            dt_published=TEST_PUBLISHED_DATE_1_STR,
            aggregation_index=0,
            topic_id=TEST_TOPIC_IDS[0],
            topic=TEST_TOPICS[0],
            title="the article title",
            url="url",
            article_data="article_data",
            sorting=DATE_SORTING_STR,
            category=TEST_CATEGORY_1,
        )
    ]
    cluster_generator = ArticleClusterGenerator(raw_articles)
    assert cluster_generator.raw_articles == raw_articles
    assert cluster_generator.clustered_articles == []
    assert cluster_generator._embedding_model_name == "sentence-transformers/all-mpnet-base-v2"
