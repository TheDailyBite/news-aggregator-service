from datetime import datetime

from news_aggregator_data_access_layer.config import SELF_USER_ID
from news_aggregator_data_access_layer.models.dynamodb import (
    TrustedNewsProviders,
    UserTopics,
    create_tables,
)

from news_aggregator_service.aggregators import bing

create_tables()


def aggregate_bing_news_self(event, context):
    print(f"Aggregating Bing News for self user {SELF_USER_ID}...")
    try:
        trusted_news_providers = [tnp for tnp in TrustedNewsProviders.scan()]
        user_topics = UserTopics.query(SELF_USER_ID)
        results = []
        for user_topic in user_topics:
            if user_topic.is_active:
                aggregation_dt = datetime.utcnow()
                # user_topic.max_aggregator_results - can use in the future if we want to limit the number of results
                aggregation_results, store_prefix = bing.aggregate_candidates_for_query(
                    user_topic.topic, user_topic.categories, aggregation_dt
                )
                results.extend([str(a_r) for a_r in aggregation_results])
        return {"statusCode": 200, "body": {"results": results}}
    except Exception as e:
        print(f"Failed to aggregate Bing News for self user {SELF_USER_ID} with error: {e}")
        return {"statusCode": 500, "body": {"error": str(e)}}
