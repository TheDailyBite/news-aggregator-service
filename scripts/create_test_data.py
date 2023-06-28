# Description: Creates test data for the news aggregator service
# Usage: python create_test_data.py
# NOTE - this should only be used locally for testing purposes. Not when writing to any resources in AWS.
import json
import sys

# caution: path[0] is reserved for script path (or '' in REPL)
# this is to make news_aggregator_service available
sys.path.insert(1, "../")

import os
from datetime import datetime, timezone

import boto3
import create_news_topic
import typer
from news_aggregator_data_access_layer.config import (
    REGION_NAME,
    S3_ENDPOINT_URL,
    SOURCED_ARTICLES_S3_BUCKET,
)
from news_aggregator_data_access_layer.constants import (
    SUPPORTED_AGGREGATION_CATEGORIES,
    ArticleApprovalStatus,
)
from news_aggregator_data_access_layer.models.dynamodb import (
    NewsTopics,
    PreviewUsers,
    SourcedArticles,
    create_tables,
    get_current_dt_utc_attribute,
    get_uuid4_attribute,
)
from news_aggregator_data_access_layer.utils.s3 import read_objects_from_prefix_with_extension

from news_aggregator_service.config import DEFAULT_DAILY_PUBLISHING_LIMIT

# class Article()


def upload_directory_to_s3(bucket_name, directory_path, s3_prefix="") -> set:
    """Uploads an entire local directory to an S3 bucket.

    Args:
      bucket_name: The name of the S3 bucket.
      directory_path: The path to the local directory.
      s3_prefix: The prefix to use for the S3 keys.
    """

    s3 = boto3.client("s3", region_name=REGION_NAME, endpoint_url=S3_ENDPOINT_URL)
    article_prefixes = set()
    for root, subdirs, files in os.walk(directory_path):
        for file in files:
            full_file_path = os.path.join(root, file)
            s3_key = os.path.join(s3_prefix, os.path.relpath(full_file_path, directory_path))
            print(f"S3 KEY: {s3_key}")
            s3.upload_file(full_file_path, bucket_name, s3_key)
            article_prefix = "/".join(s3_key.split("/")[:-2])
            article_prefixes.add(article_prefix)
    return article_prefixes


def get_article_prefixes(directory_path) -> set:
    """Get article prefixes from a local directory.

    Args:
      directory_path: The path to the local directory.
    """

    article_prefixes = set()
    for root, subdirs, files in os.walk(directory_path):
        for file in files:
            full_file_path = os.path.join(root, file)
            full_key = os.path.join(os.path.relpath(full_file_path, directory_path))
            article_prefix = "/".join(full_key.split("/")[:-2])
            article_prefixes.add(article_prefix)
    return article_prefixes


def create_test_data():
    print("Creating tables...")
    create_tables()
    print("Creating test data...")
    user_id = get_uuid4_attribute()
    print(f"Creating preview user with id {user_id}...")
    PreviewUsers(user_id=user_id, name="Michael the Admin").save()
    print("Creating news topics...")
    topic_id = "e63037e4-f815-4d96-ac99-12381ed7fcca"
    topic = "Generative AI"
    print(f"Creating news topic with id {topic_id} and topic {topic}...")
    news_topic = NewsTopics(
        topic_id=topic_id,
        topic=topic,
        category="",
        is_active=True,
        is_published=True,
        date_created=datetime(2023, 6, 7, tzinfo=timezone.utc),
        max_aggregator_results=25,
        daily_publishing_limit=10,
        last_publishing_date=datetime(2023, 6, 8, tzinfo=timezone.utc),
    )
    news_topic.save()
    article_prefixes = get_article_prefixes("test_data/sourced_articles/")
    for article_prefix in article_prefixes:
        article = read_objects_from_prefix_with_extension(
            SOURCED_ARTICLES_S3_BUCKET, article_prefix, ".json"
        )[0][1]
        article = json.loads(article)
        sourced_article = SourcedArticles(
            topic_id=topic_id,
            sourced_article_id=article["article_id"],
            dt_sourced=datetime(2023, 6, 8, 19, 59, 52, tzinfo=timezone.utc),
            dt_published=datetime(2023, 6, 8, 19, 59, 52, tzinfo=timezone.utc),
            date_published="2023/06/08",
            title=article["article_title"],
            topic=article["article_topic"],
            source_article_ids=article["source_article_ids"],
            source_article_urls=article["source_article_urls"],
            providers=article["source_article_provider_domains"],
            article_approval_status=ArticleApprovalStatus.APPROVED,
            short_summary_ref=article_prefix + "Short_summary.txt",
            medium_summary_ref=article_prefix + "Medium_summary.txt",
            full_summary_ref=article_prefix + "Full_summary.txt",
            sourcing_run_id="somerunid",
            article_processing_cost=0.52,
        )
        print(f"Creating sourced article with id {article['article_id']}...")
        sourced_article.save()


if __name__ == "__main__":
    typer.run(create_test_data)
