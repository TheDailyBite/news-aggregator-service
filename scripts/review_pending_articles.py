import time

import boto3
import typer
from news_aggregator_data_access_layer.config import (
    REGION_NAME,
    S3_ENDPOINT_URL,
    SOURCED_ARTICLES_S3_BUCKET,
)
from news_aggregator_data_access_layer.constants import ArticleApprovalStatus
from news_aggregator_data_access_layer.models.dynamodb import (
    NewsTopics,
    PublishedArticles,
    SourcedArticles,
)
from news_aggregator_data_access_layer.utils.s3 import get_object


def main():
    article_skipped = 0
    articles_published = 0
    articles_rejected = 0
    news_topic_cache = dict()
    newline_char = "\n"
    articles_to_be_reviewed = SourcedArticles.gsi_1.query(
        ArticleApprovalStatus.PENDING, scan_index_forward=True
    )  # oldest first
    for article in articles_to_be_reviewed:
        topic_id = article.topic_id
        if topic_id not in news_topic_cache:
            topic = NewsTopics.get(topic_id)
            news_topic_cache[topic_id] = topic
        else:
            topic = news_topic_cache[topic_id]
        print(
            f"""
We will now evaluate article {article.sourced_article_id} for topic id {topic.topic_id}.
Topic name: {topic.topic} and category {topic.category if topic.category else "No category"}

What we will be evaluation is the quality of the sourced article primarily for the title, short, medium, and full summaries.

Article TITLE:
=====================
{article.title}
=====================

Article SHORT summary text: 
=====================
{get_object(SOURCED_ARTICLES_S3_BUCKET, article.short_summary_ref, boto3.client(service_name="s3", region_name=REGION_NAME, endpoint_url=S3_ENDPOINT_URL))[0]}
=====================

Article MEDIUM summary:
=====================
{get_object(SOURCED_ARTICLES_S3_BUCKET, article.medium_summary_ref, boto3.client(service_name="s3", region_name=REGION_NAME, endpoint_url=S3_ENDPOINT_URL))[0]}
=====================

Article FULL summary:
=====================
{get_object(SOURCED_ARTICLES_S3_BUCKET, article.full_summary_ref, boto3.client(service_name="s3", region_name=REGION_NAME, endpoint_url=S3_ENDPOINT_URL))[0]}
=====================

We will utilize the SOURCE ARTICLE URLS to evaluate the quality of the generated sourced article:
=====================
{newline_char.join(article.source_article_urls)}
=====================
        """
        )
        while True:
            key = input(
                "Enter PUBLISH to publish the article. Enter REJECT to reject the article. Enter SKIP to skip the article. Enter QUIT to quit review.\n"
            )
            if key == "PUBLISH":
                key = input(
                    "Are you sure you want to publish this article? Enter YES to confirm. Enter anything else to cancel.\n"
                )
                if key == "YES":
                    print(f"Changing article {article.sourced_article_id} to APPROVED status.")
                    article.update(
                        actions=[
                            SourcedArticles.article_approval_status.set(
                                ArticleApprovalStatus.APPROVED
                            )
                        ]
                    )
                    print(
                        f"Incrementing published articles item for topic {topic.topic_id} and published date {article.published_date} by 1."
                    )
                    try:
                        published_article = PublishedArticles.get(
                            topic.topic_id, article.date_published
                        )
                        published_article.update(
                            actions=[PublishedArticles.published_article_count.add(1)]
                        )
                    except PublishedArticles.DoesNotExist as e:
                        published_article = PublishedArticles(
                            topic.topic_id, article.date_published, published_article_count=1
                        )
                        published_article.save()
                    articles_published += 1
                    break
                else:
                    print("Cancelling article publish.")
            elif key == "REJECT":
                print(f"Changing article {article.sourced_article_id} to REJECTED status.")
                article.update(
                    actions=[
                        SourcedArticles.article_approval_status.set(ArticleApprovalStatus.REJECTED)
                    ]
                )
                articles_rejected += 1
                break
            elif key == "SKIP":
                print("Skipping article. To review this article again, run this script again.")
                article_skipped += 1
                break
            elif key == "QUIT":
                print("Quitting review.")
                _print_review_summary(article_skipped, articles_published, articles_rejected)
                return
            else:
                print(
                    "Invalid input. Make sure the input matches the options exactly. Please try again."
                )
        print(
            """



            Continuing to next article...
            Fetching next article...


        """
        )
        time.sleep(5)
    _print_review_summary(article_skipped, articles_published, articles_rejected)


def _print_review_summary(article_skipped, articles_published, articles_rejected):
    print(
        f"""
Review summary:
=====================

Articles skipped: {article_skipped}
Articles published: {articles_published}
Articles rejected: {articles_rejected}
=====================
    """
    )


if __name__ == "__main__":
    typer.run(main)
