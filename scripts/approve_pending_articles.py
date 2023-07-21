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


def approve_pending_articles(topic_id: str) -> None:
    articles_published = 0
    k = input(
        f"You are about to mark as approved all PENDING articles for topic {topic_id}. This is a very serious operation. Enter 'YES' to continue.\n"
    )
    if k != "YES":
        print("Aborting.")
        return
    articles = SourcedArticles.query(
        topic_id,
        filter_condition=SourcedArticles.article_approval_status == ArticleApprovalStatus.PENDING,
    )
    for article in articles:
        print(f"Changing article {article.sourced_article_id} to APPROVED status.")
        article.update(
            actions=[SourcedArticles.article_approval_status.set(ArticleApprovalStatus.APPROVED)]
        )
        print(
            f"Incrementing published articles item for topic {topic_id} and published date {article.date_published} by 1."
        )
        try:
            published_article = PublishedArticles.get(topic_id, article.date_published)
            published_article.update(actions=[PublishedArticles.published_article_count.add(1)])
        except PublishedArticles.DoesNotExist as e:
            published_article = PublishedArticles(
                topic_id, article.date_published, published_article_count=1
            )
            published_article.save()
        articles_published += 1
        time.sleep(1)
    print(f"Approved {articles_published} articles for topic {topic_id}.")


if __name__ == "__main__":
    typer.run(approve_pending_articles)
