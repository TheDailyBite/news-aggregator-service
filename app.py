from typing import List, Set

import math
import urllib.parse
from datetime import datetime, timedelta, timezone

from news_aggregator_data_access_layer.config import SELF_USER_ID
from news_aggregator_data_access_layer.constants import (
    ALL_CATEGORIES_STR,
    SUPPORTED_AGGREGATION_CATEGORIES,
)
from news_aggregator_data_access_layer.models.dynamodb import (
    NewsTopics,
    TrustedNewsProviders,
    create_tables,
    get_current_dt_utc_attribute,
    get_uuid4_attribute,
)

from news_aggregator_service.aggregators.news_aggregators import (
    AggregatorInterface,
    BingAggregator,
    NewsApiOrgAggregator,
)
from news_aggregator_service.config import (
    AGGREGATOR_FETCHED_ARTICLES_MULTIPLIER,
    BING_AGGREGATOR_ID,
    DEFAULT_DAILY_PUBLISHING_LIMIT,
    ENABLED_AGGREGATORS,
    NEWS_API_ORG_AGGREGATOR_ID,
)
from news_aggregator_service.exceptions import UnsupportedCategoryException
from news_aggregator_service.sourcers.naive import NaiveSourcer

create_tables()

test_news_topic_event_with_category = {
    "topic": "Generative AI",
    "category": "science-and-technology",
    "max_aggregator_results": 25,
}
test_news_topic_event_without_category = {
    "topic": "Generative AI",
    "category": ALL_CATEGORIES_STR,
    "max_aggregator_results": 25,
}

from news_aggregator_service.utils.telemetry import setup_logger

logger = setup_logger(__name__)


def fetch_aggregator(aggregator_id: str) -> AggregatorInterface:
    if aggregator_id == BING_AGGREGATOR_ID:
        return BingAggregator()
    elif aggregator_id == NEWS_API_ORG_AGGREGATOR_ID:
        return NewsApiOrgAggregator()
    else:
        raise ValueError(f"Aggregator {aggregator_id} is not supported")


def update_news_topic_last_aggregation_dts(
    news_topic: NewsTopics, aggregator_id: str, aggregation_data_end_dt: datetime
) -> None:
    if aggregator_id == BING_AGGREGATOR_ID:
        news_topic.update(
            actions=[
                NewsTopics.dt_last_aggregated.set(datetime.now(timezone.utc)),
                NewsTopics.bing_aggregation_last_end_time.set(aggregation_data_end_dt),
            ]
        )
    elif aggregator_id == NEWS_API_ORG_AGGREGATOR_ID:
        news_topic.update(
            actions=[
                NewsTopics.dt_last_aggregated.set(datetime.now(timezone.utc)),
                NewsTopics.news_api_org_aggregation_last_end_time.set(aggregation_data_end_dt),
            ]
        )
    else:
        raise ValueError(f"Aggregator {aggregator_id} is not supported")


def aggregation_scheduler(event, context):
    return {"statusCode": 200, "body": "Hello World from Aggregation!"}


def sourcing_scheduler(event, context):
    return {"statusCode": 200, "body": "Hello World from Sourcing!"}


def aggregate_news_topic(event, context):
    return {"statusCode": 200, "body": event}


def source_news_topic(event, context):
    return {"statusCode": 200, "body": event}


def aggregate_news(event, context):
    try:
        # TODO - we'll probably have a queue of topic id + aggregator id + aggregation_data_start_dt messages to aggregate
        # and pull from that queue here
        # we can also add an aggregator_id field and then fetch the aggregator class
        topic_id = event.get("topic_id", "")
        aggregator_id = event.get("aggregator_id", "")
        if aggregator_id not in ENABLED_AGGREGATORS:
            raise ValueError(f"Aggregator {aggregator_id} is not enabled")
        # TODO - not sure what this format will be like.
        # example: "2023-05-30T17:51:22"
        aggregation_data_start_dt = datetime.fromisoformat(event["aggregation_data_start_dt"])
        aggregation_data_end_dt = datetime.fromisoformat(event["aggregation_data_end_dt"])
        news_topic = NewsTopics.get(topic_id)
        if not news_topic:
            raise ValueError(f"News Topic with id {topic_id} does not exist")
        if news_topic.is_active is False:
            raise ValueError(f"News Topic with id {topic_id} is not active")
        max_aggregator_results = news_topic.max_aggregator_results
        fetched_articles_count = max_aggregator_results * AGGREGATOR_FETCHED_ARTICLES_MULTIPLIER
        logger.info(
            f"Aggregating news from aggregator {aggregator_id} for topic id: {topic_id} (topic: {news_topic.topic} category: {news_topic.category}). Max aggregator results {max_aggregator_results}"
        )
        trusted_news_providers = [tnp for tnp in TrustedNewsProviders.scan()]
        aggregator = fetch_aggregator(aggregator_id)
        try:
            aggregation_result, end_published_dt = aggregator.aggregate_candidates_for_topic(
                news_topic.topic_id,
                news_topic.topic,
                news_topic.category,
                aggregation_data_start_dt,
                aggregation_data_end_dt,
                max_aggregator_results,
                fetched_articles_count,
                trusted_news_providers,
            )
        except UnsupportedCategoryException as e:
            logger.info(
                f"Aggregator {aggregator_id} does not support category {news_topic.category}. Skipping aggregation for topic id: {topic_id} (topic: {news_topic.topic} category: {news_topic.category})"
            )
            return {"statusCode": 200, "body": {"message": str(e)}}
        update_news_topic_last_aggregation_dts(news_topic, aggregator_id, end_published_dt)
        results = aggregation_result.json()
        return {"statusCode": 200, "body": {"results": results}}
    except ValueError as ve:
        logger.error(
            f"Failed to aggregate topic id {topic_id} for aggregator {aggregator_id} with error: {ve}",
            exc_info=True,
        )
        return {"statusCode": 400, "body": {"error": str(ve)}}
    except Exception as e:
        logger.error(
            f"Failed to aggregate topic id {topic_id} for aggregator {aggregator_id} with error: {e}",
            exc_info=True,
        )
        return {"statusCode": 500, "body": {"error": str(e)}}


def source_articles(event, context):
    try:
        # TODO - we'll probably have a queue of topic id + aggregator id + aggregation_data_start_dt messages to aggregate
        # and pull from that queue here
        # we can also add an aggregator_id field and then fetch the aggregator class
        topic_id = event.get("topic_id", "")
        if not topic_id:
            raise ValueError("topic_id must be specified")
        sourcing_date = event.get("sourcing_date")
        if not sourcing_date:
            raise ValueError("sourcing_date must be specified")
        sourcing_date = datetime.fromisoformat(sourcing_date)
        daily_sourcing_frequency = event.get("daily_sourcing_frequency")
        if not daily_sourcing_frequency:
            raise ValueError("daily_sourcing_frequency must be specified")
        daily_sourcing_frequency = float(daily_sourcing_frequency)
        news_topic = NewsTopics.get(topic_id)
        if not news_topic:
            raise ValueError(f"News Topic with id {topic_id} does not exist")
        if news_topic.is_active is False:
            raise ValueError(f"News Topic with id {topic_id} is not active")
        daily_publishing_limit = news_topic.daily_publishing_limit
        top_k = math.ceil(float(daily_publishing_limit) / daily_sourcing_frequency)
        logger.info(
            f"Sourcing news for sourcing date {sourcing_date}, topic id: {topic_id} (topic: {news_topic.topic} category: {news_topic.category}). Top k {top_k}."
        )
        naive_sourcer = NaiveSourcer(
            topic_id,
            news_topic.topic,
            news_topic.category,
            top_k,
            sourcing_date,
            daily_publishing_limit,
        )
        sourced_articles = naive_sourcer.source_articles()
        if not sourced_articles:
            logger.info(
                f"No articles found for sourcing date {sourcing_date}, topic id: {topic_id} (topic: {news_topic.topic} category: {news_topic.category}). Top k {top_k}."
            )
            return {"statusCode": 200, "body": {"results": []}}
        naive_sourcer.store_articles()
        news_topic.update(
            actions=[
                NewsTopics.last_publishing_date.set(sourcing_date),
            ]
        )
        results = [sourced_article.sourced_article_id for sourced_article in sourced_articles]
        return {"statusCode": 200, "body": {"results": results}}
    except ValueError as ve:
        logger.error(
            f"Failed to source topic id {topic_id} for top k {top_k} with error: {ve}",
            exc_info=True,
        )
        return {"statusCode": 400, "body": {"error": str(ve)}}
    except Exception as e:
        logger.error(
            f"Failed to source topic id {topic_id} for top k {top_k} with error: {e}",
            exc_info=True,
        )
        return {"statusCode": 500, "body": {"error": str(e)}}


def news_topic_exists(topic: str, category: str) -> bool:
    news_topics = NewsTopics.scan()
    for news_topic in news_topics:
        if news_topic.topic == topic and news_topic.category == category:
            return True
    return False


def create_news_topic(event, context):
    try:
        topic = event.get("topic").lower()
        category = event.get("category").lower()
        max_aggregator_results = event.get("max_aggregator_results")
        if category not in SUPPORTED_AGGREGATION_CATEGORIES:
            raise ValueError(
                f"Category {category} is not supported. Supported categories: {SUPPORTED_AGGREGATION_CATEGORIES}"
            )
        topic = urllib.parse.quote_plus(topic)
        logger.info(f"Url encoded topic: {topic} from original input topic {event['topic']}")
        if max_aggregator_results <= 0:
            raise ValueError(
                f"max_aggregator_results must be greater than 0. Got {max_aggregator_results}"
            )
        if news_topic_exists(topic, category):
            raise ValueError(f"Topic {topic} and category {category} already exist.")
        logger.info(
            f"Creating news topic with topic: {topic}, category: {category}, max aggregator results: {max_aggregator_results}"
        )
        topic_id = get_uuid4_attribute()
        news_topic = NewsTopics(
            topic_id=topic_id,
            topic=topic,
            category=category,
            is_active=True,
            is_published=False,
            date_created=get_current_dt_utc_attribute(),
            max_aggregator_results=max_aggregator_results,
            daily_publishing_limit=DEFAULT_DAILY_PUBLISHING_LIMIT,
        )
        news_topic.save(condition=NewsTopics.topic_id.does_not_exist())
        return {
            "statusCode": 200,
            "body": {
                "message": f"Successfully created news topic with topic: {topic}, category: {category}, max aggregator results: {max_aggregator_results}",
                "topic_id": topic_id,
            },
        }
    except Exception as e:
        logger.error(
            f"Failed to create news topic with topic: {topic}, category: {category}, max aggregator results: {max_aggregator_results} with error: {e}",
            exc_info=True,
        )
        return {"statusCode": 500, "body": {"error": str(e)}}
