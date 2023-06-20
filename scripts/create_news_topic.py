import sys
import urllib.parse

# caution: path[0] is reserved for script path (or '' in REPL)
# this is to make news_aggregator_service available
sys.path.insert(1, "../")

import typer
from news_aggregator_data_access_layer.constants import SUPPORTED_AGGREGATION_CATEGORIES
from news_aggregator_data_access_layer.models.dynamodb import (
    NewsTopics,
    get_current_dt_utc_attribute,
    get_uuid4_attribute,
)

from news_aggregator_service.config import DEFAULT_DAILY_PUBLISHING_LIMIT


def news_topic_exists(topic: str, category: str) -> bool:
    news_topics = NewsTopics.scan()
    for news_topic in news_topics:
        if news_topic.topic == topic and news_topic.category == category:
            return True
    return False


def main(
    topic: str,
    category: str,
    max_aggregator_results: int,
    daily_publishing_limit: int = DEFAULT_DAILY_PUBLISHING_LIMIT,
) -> str:
    try:
        topic = topic.lower()
        category = category.lower()
        if category not in SUPPORTED_AGGREGATION_CATEGORIES:
            raise ValueError(
                f"Category {category} is not supported. Supported categories: {SUPPORTED_AGGREGATION_CATEGORIES}"
            )
        input_topic = topic
        topic = urllib.parse.quote_plus(topic)
        print(f"Url encoded topic: {topic} from original input topic {input_topic}")
        if max_aggregator_results <= 0:
            raise ValueError(
                f"max_aggregator_results must be greater than 0. Got {max_aggregator_results}"
            )
        if news_topic_exists(topic, category):
            raise ValueError(f"Topic {topic} and category {category} already exist.")
        print(
            f"Creating news topic with topic: {topic}, category: {category}, max aggregator results: {max_aggregator_results}, daily publishing limit: {daily_publishing_limit}"
        )
        topic_id = get_uuid4_attribute()
        news_topic = NewsTopics(
            topic_id=topic_id,
            topic=topic,
            category=category,
            is_active=True,
            is_published=True,
            date_created=get_current_dt_utc_attribute(),
            max_aggregator_results=max_aggregator_results,
            daily_publishing_limit=daily_publishing_limit,
        )
        news_topic.save(condition=NewsTopics.topic_id.does_not_exist())
        return topic_id
    except Exception as e:
        print(
            f"Failed to create news topic with topic: {topic}, category: {category}, max aggregator results: {max_aggregator_results} with error: {e}"
        )
        raise


if __name__ == "__main__":
    typer.run(main)
