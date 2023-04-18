from typing import List, Set

import urllib.parse
from datetime import datetime

from news_aggregator_data_access_layer.config import SELF_USER_ID
from news_aggregator_data_access_layer.models.dynamodb import (
    TrustedNewsProviders,
    UserTopics,
    create_tables,
)

from news_aggregator_service.aggregators import bing

create_tables()

test_self_user_topic_event = {
    "topic": "Generative AI",
    "categories": ["ScienceAndTechnology"],
    "max_aggregator_results": 50,
}


def aggregate_bing_news_self(event, context):
    print(f"Aggregating Bing News for self user {SELF_USER_ID}...")
    try:
        trusted_news_providers = [tnp for tnp in TrustedNewsProviders.scan()]
        user_topics = UserTopics.query(SELF_USER_ID)
        results: List[str] = []
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
        print(f"Failed to aggregate Bing News for self user {SELF_USER_ID} with error: {e}")
        return {"statusCode": 500, "body": {"error": str(e)}}


def create_user_topic(event, context):
    topic = event["topic"]
    topic = urllib.parse.quote_plus(topic)
    print(f"Url encoded topic: {topic} from original input topic {event['topic']}")
    categories = None
    if event["categories"]:
        categories = set(event["categories"])
    max_aggregator_results = event.get("max_aggregator_results")
    print(
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
        print(
            f"Failed to create user topic for self user {SELF_USER_ID} with topic: {topic}, categories: {categories}, max aggregator results: {max_aggregator_results} with error: {e}"
        )
        return {"statusCode": 500, "body": {"error": str(e)}}