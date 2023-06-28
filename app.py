from typing import List, Set, Tuple

import json
import math
from datetime import datetime, timedelta, timezone

import boto3
from news_aggregator_data_access_layer.constants import (
    ALL_CATEGORIES_STR,
    SUPPORTED_AGGREGATION_CATEGORIES,
    NewsAggregatorsEnum,
)
from news_aggregator_data_access_layer.models.dynamodb import (
    NewsAggregators,
    NewsTopics,
    PreviewUsers,
    TrustedNewsProviders,
    UserTopicSubscriptions,
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
    DAILY_SOURCING_FREQUENCY,
    DEFAULT_DAILY_PUBLISHING_LIMIT,
    LOCAL_TESTING,
    NEWS_AGGREGATION_QUEUE_NAME,
    NEWS_SOURCING_QUEUE_NAME,
)
from news_aggregator_service.exceptions import (
    PreviewUserNotExistsException,
    UnsupportedCategoryException,
)

create_tables()

from news_aggregator_service.utils.telemetry import setup_logger

logger = setup_logger(__name__)


def fetch_aggregator(aggregator_id: str) -> AggregatorInterface:
    if aggregator_id == NewsAggregatorsEnum.BING_NEWS.value:
        return BingAggregator()
    elif aggregator_id == NewsAggregatorsEnum.NEWS_API_ORG.value:
        return NewsApiOrgAggregator()
    else:
        raise ValueError(f"Aggregator {aggregator_id} is not supported")


def update_news_topic_last_aggregation_dts(
    news_topic: NewsTopics, aggregator_id: str, aggregation_data_end_dt: datetime
) -> None:
    if aggregator_id == NewsAggregatorsEnum.BING_NEWS.value:
        news_topic.update(
            actions=[
                NewsTopics.dt_last_aggregated.set(datetime.now(timezone.utc)),
                NewsTopics.bing_aggregation_last_end_time.set(aggregation_data_end_dt),
            ]
        )
    elif aggregator_id == NewsAggregatorsEnum.NEWS_API_ORG.value:
        news_topic.update(
            actions=[
                NewsTopics.dt_last_aggregated.set(datetime.now(timezone.utc)),
                NewsTopics.news_api_org_aggregation_last_end_time.set(aggregation_data_end_dt),
            ]
        )
    else:
        raise ValueError(f"Aggregator {aggregator_id} is not supported")


def get_aggregation_timeframe(
    news_topic: NewsTopics, aggregator_id: str
) -> tuple[datetime, datetime]:
    aggregator = fetch_aggregator(aggregator_id)
    if aggregator_id == NewsAggregatorsEnum.BING_NEWS.value:
        last_end_dt = news_topic.bing_aggregation_last_end_time
        if last_end_dt is None:
            last_end_dt = datetime.now(timezone.utc) + aggregator.historical_articles_days_ago_start
    elif aggregator_id == NewsAggregatorsEnum.NEWS_API_ORG.value:
        last_end_dt = news_topic.news_api_org_aggregation_last_end_time
        if last_end_dt is None:
            last_end_dt = datetime.now(timezone.utc) + aggregator.historical_articles_days_ago_start
    else:
        raise ValueError(f"Aggregator {aggregator_id} is not supported")
    aggregation_data_start_dt = last_end_dt
    aggregation_data_end_dt = aggregation_data_start_dt + timedelta(
        days=1
    )  # NOTE - currently the window is 1 day
    return aggregation_data_start_dt, aggregation_data_end_dt


def get_oldest_publishing_date() -> datetime:
    supported_historical_articles_days_ago_start: list[timedelta] = []
    for aggregator in NewsAggregatorsEnum:
        aggregator_id = aggregator.value
        agg = fetch_aggregator(aggregator_id)
        # this is a negative days timedelta timedelta(days=-<days>) so we will take the min to get the oldest
        supported_historical_articles_days_ago_start.append(agg.historical_articles_days_ago_start)
    oldest_publishing_date: datetime = datetime.now(timezone.utc) + min(
        supported_historical_articles_days_ago_start
    )
    logger.info(f"Oldest publishing date is {oldest_publishing_date}")
    return oldest_publishing_date


def aggregation_scheduler(event, context):
    try:
        aggregation_requests_scheduled = 0
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        aggregators = [
            aggregator.aggregator_id.value
            for aggregator in NewsAggregators.scan()
            if aggregator.is_active == True
        ]
        news_topics = NewsTopics.scan()
        for news_topic in news_topics:
            if news_topic.is_active is False:
                logger.info(f"Skipping inactive news topic {news_topic.topic_id}")
                continue
            for aggregator_id in aggregators:
                agg = fetch_aggregator(aggregator_id)
                if not agg.is_category_supported(news_topic.category):
                    logger.info(
                        f"Skipping aggregator {aggregator_id} for news topic {news_topic.topic_id} because category {news_topic.category} is not supported"
                    )
                    continue
                aggregation_data_start_dt, aggregation_data_end_dt = get_aggregation_timeframe(
                    news_topic, aggregator_id
                )
                # enqueue aggregation requests until today
                while aggregation_data_start_dt <= today:
                    aggregation_request_message = json.dumps(
                        {
                            "topic_id": news_topic.topic_id,
                            "aggregator_id": aggregator_id,
                            "aggregation_data_start_dt": aggregation_data_start_dt.isoformat(),
                            "aggregation_data_end_dt": aggregation_data_end_dt.isoformat(),
                        }
                    )
                    message_group_id = f"{aggregator_id}-{news_topic.topic_id}"
                    logger.info(
                        f"Enqueuing aggregation request {aggregation_request_message} with message group id {message_group_id} to queue {NEWS_AGGREGATION_QUEUE_NAME} for timeframe {aggregation_data_start_dt.isoformat()} to {aggregation_data_end_dt.isoformat()}"
                    )
                    enqueue_aggregation_request(
                        NEWS_AGGREGATION_QUEUE_NAME, aggregation_request_message, message_group_id
                    )
                    aggregation_requests_scheduled += 1
                    aggregation_data_start_dt = aggregation_data_end_dt
                    aggregation_data_end_dt += timedelta(days=1)
        return {
            "statusCode": 200,
            "body": {"aggregation_requests_scheduled": aggregation_requests_scheduled},
        }
    except Exception as e:
        logger.error(
            f"Failed to schedule aggregation requests with error: {e}",
            exc_info=True,
        )
        return {"statusCode": 500, "body": {"error": str(e)}}


def enqueue_aggregation_request(queue_name: str, message_body: str, message_group_id: str) -> None:
    if LOCAL_TESTING:
        logger.info(
            f"Skipping enqueueing message {message_body} with message group id {message_group_id} to queue {queue_name} because local testing is enabled"
        )
        return
    sqs = boto3.resource("sqs")
    # Get the queue. This returns an SQS.Queue instance
    queue = sqs.get_queue_by_name(QueueName=queue_name)
    queue.send_message(MessageBody=message_body, MessageGroupId=message_group_id)


def sourcing_scheduler(event, context):
    try:
        sourcing_requests_scheduled = 0
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        news_topics = NewsTopics.scan()
        for news_topic in news_topics:
            if news_topic.is_active is False:
                logger.info(
                    f"Skipping sourcing scheduling inactive news topic {news_topic.topic_id}"
                )
                continue
            logger.info(f"Scheduling sourcing for news topic {news_topic.topic_id}")
            last_publishing_date = news_topic.last_publishing_date
            if last_publishing_date is None:
                # this is a fictitious date that is before the oldest publishing date supported by the aggregators
                last_publishing_date = get_oldest_publishing_date() + timedelta(days=-1)
            last_publishing_date = last_publishing_date.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            # if last publishing date is in the past (i.e. not today), then we need to source for tomorrow since all aggregations have occurred for today
            if last_publishing_date != today:
                sourcing_date = last_publishing_date + timedelta(days=1)
            # if last publishing date is today, then we need to source still for today since not all aggregations have not occurred for today
            else:
                sourcing_date = last_publishing_date
            while sourcing_date <= today:
                logger.info(
                    f"Sourcing date for news topic {news_topic.topic_id} is {sourcing_date.isoformat()} for current date {today.isoformat()}"
                )
                sourcing_request_message = json.dumps(
                    {
                        "topic_id": news_topic.topic_id,
                        "sourcing_date": sourcing_date.isoformat(),
                        "daily_sourcing_frequency": DAILY_SOURCING_FREQUENCY,
                    }
                )
                message_group_id = f"{news_topic.topic_id}"
                logger.info(
                    f"Enqueuing sourcing request {sourcing_request_message} with message group id {message_group_id} to queue {NEWS_SOURCING_QUEUE_NAME}"
                )
                enqueue_aggregation_request(
                    NEWS_SOURCING_QUEUE_NAME, sourcing_request_message, message_group_id
                )
                sourcing_requests_scheduled += 1
                sourcing_date += timedelta(days=1)
        return {
            "statusCode": 200,
            "body": {"sourcing_requests_scheduled": sourcing_requests_scheduled},
        }
    except Exception as e:
        logger.error(
            f"Failed to schedule sourcing requests with error: {e}",
            exc_info=True,
        )
        return {"statusCode": 500, "body": {"error": str(e)}}


def aggregate_news_topic(event, context):
    try:
        logger.info(f"Received event: {event}")
        event = json.loads(event)
        if len(event["Records"]) != 1:
            raise Exception(f"Expected 1 record but received {len(event['Records'])}")
        message_body = event["Records"][0]["body"]
        topic_id = message_body.get("topic_id", "")
        aggregator_id = message_body.get("aggregator_id", "")
        news_aggregator = NewsAggregators.get(
            NewsAggregatorsEnum.get_member_by_value(aggregator_id)
        )
        if not news_aggregator or not news_aggregator.is_active:
            raise ValueError(f"Aggregator with id {aggregator_id} does not exist or is not active")
        aggregation_data_start_dt = datetime.fromisoformat(
            message_body["aggregation_data_start_dt"]
        )
        aggregation_data_end_dt = datetime.fromisoformat(message_body["aggregation_data_end_dt"])
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


def source_news_topic(event, context):
    try:
        from news_aggregator_service.sourcers.naive import NaiveSourcer

        logger.info(f"Received event: {event}")
        event = json.loads(event)
        if len(event["Records"]) != 1:
            raise Exception(f"Expected 1 record but received {len(event['Records'])}")
        message_body = event["Records"][0]["body"]
        topic_id = message_body.get("topic_id", "")
        if not topic_id:
            raise ValueError("topic_id must be specified")
        sourcing_date = message_body.get("sourcing_date")
        if not sourcing_date:
            raise ValueError("sourcing_date must be specified")
        sourcing_date = datetime.fromisoformat(sourcing_date)
        daily_sourcing_frequency = message_body.get("daily_sourcing_frequency")
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


def subscribe_news_topics(event, context):
    try:
        logger.info(f"Received event: {event}")
        user_id = event.get("user_id", "")
        if not user_id:
            raise ValueError("user_id must be specified")
        news_topics_to_unsubscribe = event.get("news_topics_to_unsubscribe", None)
        if news_topics_to_unsubscribe is None:
            raise ValueError("news_topics_to_unsubscribe must be specified")
        news_topics_to_subscribe = event.get("news_topics_to_subscribe", None)
        if news_topics_to_subscribe is None:
            raise ValueError("news_topics_to_subscribe must be specified")
        for topic_id in news_topics_to_unsubscribe:
            logger.info(f"Unsubscribing user id {user_id} from topic id {topic_id}")
            try:
                UserTopicSubscriptions(user_id, topic_id).delete()
            except Exception as e:
                logger.error(
                    f"Failed to unsubscribe user id {user_id} from topic id {topic_id} with error: {e}",
                    exc_info=True,
                )
                # TODO - emit metric
                continue
        for topic_id in news_topics_to_subscribe:
            logger.info(f"Subscribing user id {user_id} to topic id {topic_id}")
            try:
                UserTopicSubscriptions(
                    user_id, topic_id, date_subscribed=get_current_dt_utc_attribute()
                ).save()
            except Exception as e:
                logger.error(
                    f"Failed to subscribe user id {user_id} to topic id {topic_id} with error: {e}",
                    exc_info=True,
                )
                # TODO - emit metric
                continue
        return {"statusCode": 200, "body": {"message": "Success"}}
    except ValueError as ve:
        logger.error(
            f"Failed to subscribe to news topics for user id {user_id} with error: {ve}",
            exc_info=True,
        )
        return {"statusCode": 400, "body": {"error": "Invalid request"}}
    except Exception as e:
        logger.error(
            f"Failed to subscribe to news topics for user id {user_id} with error: {e}",
            exc_info=True,
        )
        return {"statusCode": 500, "body": {"error": "Internal server error"}}


def get_news_topics(event, context):
    try:
        logger.info(f"Received event: {event}")
        user_id = event.get("user_id", "")
        if not user_id:
            raise ValueError("user_id must be specified")
        try:
            user = PreviewUsers.get(user_id)
        except PreviewUsers.DoesNotExist:
            raise PreviewUserNotExistsException()
        user_news_topics = UserTopicSubscriptions.query(user_id)
        user_news_topic_ids = [user_news_topic.topic_id for user_news_topic in user_news_topics]
        news_topics = NewsTopics.scan()
        published_news_topics = [
            {
                "topic_id": news_topic.topic_id,
                "topic": news_topic.topic,
                "category": news_topic.category,
                "last_publishing_date": news_topic.last_publishing_date.isoformat()
                if news_topic.last_publishing_date
                else "",
                "is_user_subscribed": news_topic.topic_id in user_news_topic_ids,
            }
            for news_topic in news_topics
            if news_topic.is_published
        ]
        return {"statusCode": 200, "body": {"results": published_news_topics}}
    except ValueError as ve:
        logger.error(
            f"Failed to get news topics for user id {user_id} with error: {ve}",
            exc_info=True,
        )
        return {"statusCode": 400, "body": {"error": "Invalid request"}}
    except Exception as e:
        logger.error(
            f"Failed to get news topics for user id {user_id} with error: {e}",
            exc_info=True,
        )
        return {"statusCode": 500, "body": {"error": "Internal server error"}}


def validate_preview_user(event, context):
    try:
        logger.info(f"Received event: {event}")
        user_id = event.get("user_id", "")
        if not user_id:
            raise ValueError("user_id must be specified")
        try:
            preview_user = PreviewUsers.get(user_id)
            return {
                "statusCode": 200,
                "body": {"user_id": preview_user.user_id, "name": preview_user.name},
            }
        except PreviewUsers.DoesNotExist:
            raise PreviewUserNotExistsException()
    except ValueError as ve:
        logger.error(
            f"Failed to validate preview user with error: {ve}",
            exc_info=True,
        )
        return {"statusCode": 400, "body": {"error": "Invalid request."}}
    except PreviewUserNotExistsException as e:
        logger.error(
            f"Failed to validate preview user with error: {e}",
            exc_info=True,
        )
        return {"statusCode": 401, "body": {"error": "Preview user does not exist."}}
    except Exception as e:
        logger.error(
            f"Failed to validate preview user with error: {e}",
            exc_info=True,
        )
        return {"statusCode": 500, "body": {"error": "Internal server error"}}
