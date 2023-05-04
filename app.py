from typing import List, Set

import urllib.parse
from datetime import datetime, timedelta

from news_aggregator_data_access_layer.config import ALL_CATEGORIES_STR, SELF_USER_ID
from news_aggregator_data_access_layer.models.dynamodb import (
    TrustedNewsProviders,
    UserTopics,
    create_tables,
)

from news_aggregator_service.aggregators import bing
from news_aggregator_service.sourcers.naive import NaiveSourcer

create_tables()

test_self_user_topic_event_with_category = {
    "topic": "Generative AI",
    "categories": ["ScienceAndTechnology"],
    "max_aggregator_results": 25,
}
test_self_user_topic_event_without_category = {
    "topic": "Generative AI",
    "categories": [ALL_CATEGORIES_STR],
    "max_aggregator_results": 25,
}

from news_aggregator_service.utils.telemetry import setup_logger

logger = setup_logger(__name__)


def aggregate_bing_news_self(event, context):
    logger.info(f"Aggregating Bing News for self user {SELF_USER_ID}...")
    try:
        trusted_news_providers = [tnp for tnp in TrustedNewsProviders.scan()]
        user_topics = UserTopics.query(SELF_USER_ID)
        results: list[str] = []
        for user_topic in user_topics:
            if user_topic.is_active:
                aggregation_dt = datetime.utcnow()
                max_aggregator_results = user_topic.max_aggregator_results
                # user_topic.max_aggregator_results - can use in the future if we want to limit the number of results
                aggregation_results, store_prefix = bing.aggregate_candidates_for_query(
                    user_topic.topic, user_topic.categories, aggregation_dt, max_aggregator_results
                )
                results.extend([a_r.json() for a_r in aggregation_results])
        return {"statusCode": 200, "body": {"results": results}}
    except Exception as e:
        logger.error(
            f"Failed to aggregate Bing News for self user {SELF_USER_ID} with error: {e}",
            exc_info=True,
        )
        return {"statusCode": 500, "body": {"error": str(e)}}


def source_articles_self(event, context):
    # NOT sure in future maybe lambda to scan dynamodb when multi user
    now_dt = datetime.utcnow()
    # the aggregation datetime for sourcing is always the day before
    # for this reason it is important to schedule this lambda to run after midnight UTC
    # and to account for retries
    aggregation_dt = now_dt - timedelta(days=1)
    active_topics: list[str] = [
        user_topic.topic for user_topic in UserTopics.query(SELF_USER_ID) if user_topic.is_active
    ]
    logger.info(
        f"Sourcing articles for self user {SELF_USER_ID} and active topics {active_topics} an aggregation datetime {aggregation_dt}. Now datetime {now_dt}..."
    )
    naive_sourcer = NaiveSourcer(aggregation_dt, active_topics)
    sourced_articles = naive_sourcer.source_articles()
    naive_sourcer.store_articles()


def create_user_topic(event, context):
    topic = event["topic"]
    topic = urllib.parse.quote_plus(topic)
    logger.info(f"Url encoded topic: {topic} from original input topic {event['topic']}")
    categories = set(event["categories"])
    max_aggregator_results = event.get("max_aggregator_results")
    logger.info(
        f"Creating user topic for self user {SELF_USER_ID} with topic: {topic}, categories: {categories}, max aggregator results: {max_aggregator_results}..."
    )
    try:
        UserTopics(
            SELF_USER_ID,
            topic,
            categories=categories,
            is_active=True,
            max_aggregator_results=max_aggregator_results,
        ).save()
        return {
            "statusCode": 200,
            "body": {
                "message": f"Created user topic for self user {SELF_USER_ID} with topic: {topic}, categories: {categories}, max aggregator results: {max_aggregator_results}"
            },
        }
    except Exception as e:
        logger.error(
            f"Failed to create user topic for self user {SELF_USER_ID} with topic: {topic}, categories: {categories}, max aggregator results: {max_aggregator_results} with error: {e}",
            exc_info=True,
        )
        return {"statusCode": 500, "body": {"error": str(e)}}
