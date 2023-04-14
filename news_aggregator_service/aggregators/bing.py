from typing import Dict, List, Optional, Set, Tuple, Union

import json
import os
from datetime import datetime, timedelta

import boto3
import requests
from news_aggregator_data_access_layer.assets.news_assets import CandidateArticles, RawArticle
from news_aggregator_data_access_layer.constants import AggregatorRunStatus, ResultRefTypes
from news_aggregator_data_access_layer.models.dynamodb import AggregatorRuns

from news_aggregator_service.aggregators.models import bing_news
from news_aggregator_service.aggregators.models.bing_news import NewsArticle
from news_aggregator_service.config import (
    BING_AGGREGATOR_ID,
    BING_NEWS_API_KEY_SECRET_NAME,
    DEFAULT_BING_FRESHNESS,
    DEFAULT_BING_SORTING,
    REGION_NAME,
)
from news_aggregator_service.models.aggregations import AggregationResults
from news_aggregator_service.utils.secrets import get_secret

# Set up Bing News Search API credentials
subscription_key = get_secret(BING_NEWS_API_KEY_SECRET_NAME)

# See https://learn.microsoft.com/en-us/bing/search-apis/bing-news-search/reference/endpoints?source=recommendations#endpoints
# for the most up to date information about each endpoint
# there are 3 endpoints:
# "/news/search" for the news search
# "/news/trendingtopics" for the trending topics
# "/news" for the top news
base_url = "https://api.bing.microsoft.com"
search_url = f"{base_url}/v7.0/news/search"
article_per_request = 100

# Set headers for API request
headers = bing_news.Headers(ocp_apim_subscription_key=subscription_key)  # type: ignore


def generate_article_id(article_idx: int, category: Optional[str]) -> str:
    article_id = f"{article_idx}".zfill(10)
    if category:
        article_id += f"_{category}"
    return article_id


def aggregate_candidates_for_query(
    query: str, categories: Set[str], aggregation_dt: datetime
) -> Tuple[List[AggregationResults], str]:
    aggregator_run = AggregatorRuns(BING_AGGREGATOR_ID, aggregation_dt)
    aggregator_run.save()
    try:
        query_candidates: List[NewsArticle] = []
        aggregation_results = []
        sorting = DEFAULT_BING_SORTING
        freshness = DEFAULT_BING_FRESHNESS
        if not categories:
            print("No categories provided, getting candidates with no specified category...")
            candidates_for_query = get_candidates_for_query(query, freshness, "", sorting)
            print(f"Found {len(candidates_for_query)} candidates for query: {query}")
            query_candidates.extend(candidates_for_query)
        for category in categories:
            candidates_for_query = get_candidates_for_query(query, freshness, category, sorting)
            print(
                f"Found {len(candidates_for_query)} candidates for query: {query} and category: {category}"
            )
            query_candidates.extend(candidates_for_query)
            aggregation_results.append(
                AggregationResults(
                    len(candidates_for_query), category, query, freshness, sorting, None
                )
            )
        store_bucket, store_prefix = store_candidates(
            query, query_candidates, sorting, aggregation_dt
        )
        for agg_result in aggregation_results:
            agg_result.store_prefix = store_prefix
        update_actions = [
            AggregatorRuns.status.set(AggregatorRunStatus.COMPLETE),
            AggregatorRuns.run_end_time.set(datetime.utcnow()),
            AggregatorRuns.result_ref.set(
                {"type": ResultRefTypes.S3.value, "bucket": store_bucket, "key": store_prefix}
            ),
        ]
        aggregator_run.update(actions=update_actions)
        return aggregation_results, store_prefix
    except Exception as e:
        print(
            f"Error while aggregating Bing News for query: {query} and categories: {categories} and aggregation datetime {aggregation_dt}: {e}"
        )
        aggregator_run.update(actions=[AggregatorRuns.status.set(AggregatorRunStatus.FAILED)])
        raise


def store_candidates(
    query: str, candidates: List[NewsArticle], sorting: str, aggregation_dt: datetime
) -> Tuple[str, str]:
    print(
        f"Storing {len(candidates)} candidates for query: {query} and sorting: {sorting} and aggregation datetime {aggregation_dt}..."
    )
    s3_client = boto3.client("s3", region_name=REGION_NAME)
    candidate_articles = CandidateArticles(ResultRefTypes.S3, aggregation_dt)
    raw_articles = []
    for article_idx in range(len(candidates)):
        article = candidates[article_idx]
        category = article.category
        # currently article id is simply the index of the article in the list of candidates
        # and the category, if any
        article_id = generate_article_id(article_idx, category)
        if category:
            article_id += f"_{category}"
        raw_article = RawArticle(
            article_id=article_id,
            aggregator_id=BING_AGGREGATOR_ID,
            topic=query,
            category=article.category,
            title=article.name,
            url=article.url,
            article_data=article.json(),
            sorting=sorting,
        )
        raw_articles.append(raw_article)
    kwargs = {
        "s3_client": s3_client,
        "topic": query,
        "aggregator_id": BING_AGGREGATOR_ID,
        "articles": raw_articles,
    }
    store_bucket, store_prefix = candidate_articles.store_articles(**kwargs)
    return store_bucket, store_prefix


def get_candidates_for_query(
    query: str, freshness: str, category: str, sorting: str
) -> List[NewsArticle]:
    candidates: List[NewsArticle] = []
    offset = 0
    total_estimated_matches = 0
    page = 0
    print(
        f"Retrieving news articles for search term: {query}, category: {category} and freshness: {freshness}..."
    )
    while True:
        # Set query parameters for API request
        params = bing_news.QueryParams(
            sort_by=sorting,
            freshness=freshness,
            q=query,
            offset=offset,
            count=article_per_request,
        )
        if category:
            params.category = category
        # Send API request
        response = requests.get(
            search_url,
            headers=headers.dict(by_alias=True),
            params=params.dict(by_alias=True),
            timeout=5,
        )
        if response.status_code == 200:
            news_answer_json = response.json()
            news_answer = bing_news.NewsAnswerAPIResponse.parse_obj(news_answer_json)
            print(f"Query Context: {news_answer.query_context}")
            if not news_answer.value:
                return candidates
            if total_estimated_matches == 0:
                total_estimated_matches = news_answer.total_estimated_matches  # type: ignore
            articles = news_answer.value
            new_articles = len(articles)
            candidates.extend(articles)
            print(
                f"Retrieved {new_articles} new articles. Total articles: {len(articles)}; Page {page}; Offset: {offset}; Total estimated matches: {total_estimated_matches}"
            )
            page += 1
            offset += len(articles)
        else:
            print(
                f"Error retrieving news articles: Status Codes: {response.status_code}; {response.text}"
            )
            raise Exception(
                f"Error retrieving news articles: Status Codes: {response.status_code}; {response.text}"
            )


def discover_trending_topics():
    raise NotImplementedError("Discover trending topics is not yet implemented.")
