from typing import Dict, List, Optional, Set, Tuple, Union

import json
import os
import time
from datetime import datetime, timedelta

import boto3
import requests
from news_aggregator_data_access_layer.assets.news_assets import CandidateArticles, RawArticle
from news_aggregator_data_access_layer.config import S3_ENDPOINT_URL
from news_aggregator_data_access_layer.constants import AggregatorRunStatus, ResultRefTypes
from news_aggregator_data_access_layer.models.dynamodb import AggregatorRuns

from news_aggregator_service.aggregators.models import bing_news
from news_aggregator_service.aggregators.models.aggregations import AggregationResults
from news_aggregator_service.aggregators.models.bing_news import NewsArticle
from news_aggregator_service.config import (
    BING_AGGREGATOR_ID,
    BING_NEWS_API_KEY,
    BING_NEWS_API_KEY_SECRET_NAME,
    DEFAULT_BING_FRESHNESS,
    DEFAULT_BING_SORTING,
    DEFAULT_MAX_BING_AGGREGATOR_RESULTS,
    REGION_NAME,
    REQUESTS_SLEEP_TIME_S,
)
from news_aggregator_service.utils.secrets import get_secret

# Set up Bing News Search API credentials
# NOTE - this is just used for testing locally
# in production, we use the secrets manager
if BING_NEWS_API_KEY:
    subscription_key = BING_NEWS_API_KEY
else:
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
    query: str, categories: Set[str], aggregation_dt: datetime, max_aggregator_results: int = -1
) -> Tuple[List[AggregationResults], str]:
    aggregator_run = AggregatorRuns(BING_AGGREGATOR_ID, aggregation_dt)
    aggregator_run.save()
    if max_aggregator_results <= 0:
        print(
            f"No valid max aggregator results provided, using default value {DEFAULT_MAX_BING_AGGREGATOR_RESULTS}..."
        )
        max_aggregator_results = DEFAULT_MAX_BING_AGGREGATOR_RESULTS
    try:
        query_candidates: List[NewsArticle] = []
        aggregation_results = []
        sorting = DEFAULT_BING_SORTING
        freshness = DEFAULT_BING_FRESHNESS
        if not categories:
            print("No categories provided, getting candidates with no specified category...")
            candidates_for_query = get_candidates_for_query(
                query, freshness, "", sorting, max_aggregator_results
            )
            print(f"Found {len(candidates_for_query)} candidates for query: {query}")
            query_candidates.extend(candidates_for_query)
        for category in categories:
            candidates_for_query = get_candidates_for_query(
                query, freshness, category, sorting, max_aggregator_results
            )
            print(
                f"Found {len(candidates_for_query)} candidates for query: {query} and category: {category}"
            )
            query_candidates.extend(candidates_for_query)
            aggregation_results.append(
                AggregationResults(  # type: ignore
                    articles_aggregated_count=len(candidates_for_query),
                    category=category,
                    query=query,
                    freshness=freshness,
                    sorting=sorting,
                )
            )
        store_bucket, store_prefix = store_candidates(
            query, query_candidates, sorting, aggregation_dt
        )
        for agg_result in aggregation_results:
            agg_result.store_prefix = store_prefix
        update_actions = [
            AggregatorRuns.run_status.set(AggregatorRunStatus.COMPLETE),
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
        aggregator_run.update(actions=[AggregatorRuns.run_status.set(AggregatorRunStatus.FAILED)])
        raise


def store_candidates(
    query: str, candidates: List[NewsArticle], sorting: str, aggregation_dt: datetime
) -> Tuple[str, str]:
    print(
        f"Storing {len(candidates)} candidates for query: {query} and sorting: {sorting} and aggregation datetime {aggregation_dt}..."
    )
    s3_client = boto3.client("s3", region_name=REGION_NAME, endpoint_url=S3_ENDPOINT_URL)
    candidate_articles = CandidateArticles(ResultRefTypes.S3, aggregation_dt)
    raw_articles = []
    for article_idx in range(len(candidates)):
        article = candidates[article_idx]
        category = article.category
        # currently article id is simply the index of the article in the list of candidates
        # and the category, if any
        article_id = generate_article_id(article_idx, category)
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
    query: str, freshness: str, category: str, sorting: str, max_aggregator_results: int
) -> List[NewsArticle]:
    candidates: List[NewsArticle] = []
    offset = 0
    total_estimated_matches = 0
    page = 0
    print(
        f"Retrieving a max of {max_aggregator_results} news articles results for search term: {query}, category: {category} and freshness: {freshness}..."
    )
    # currently we use the url only to check for duplicates
    unique_articles_db: Set[str] = set()
    while True:
        if len(candidates) >= max_aggregator_results:
            print(f"Reached max aggregator results, returning {len(candidates)} candidates...")
            return candidates
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
        print(f"Request sent URL: {response.request.url}...")
        if response.status_code == 200:
            news_answer_json = response.json()
            news_answer = bing_news.NewsAnswerAPIResponse.parse_obj(news_answer_json)
            print(f"Query Context: {news_answer.query_context}")
            if not news_answer.value:
                return candidates
            total_estimated_matches = news_answer.total_estimated_matches  # type: ignore
            articles = news_answer.value
            new_articles_count = len(articles)
            processed_articles = process_articles(articles, unique_articles_db, category)
            processed_new_articles_count = len(processed_articles)
            needed_articles_count = max_aggregator_results - len(candidates)
            processed_articles = processed_articles[:needed_articles_count]
            candidates.extend(processed_articles)
            print(
                f"Retrieved {new_articles_count} new articles of which {processed_new_articles_count} are unique and relevant. Needed articles to reach max {needed_articles_count} Total articles retrieve in aggregation: {len(candidates)}; Page {page}; Offset: {offset}; Total estimated matches: {total_estimated_matches}"
            )
            page += 1
            offset += new_articles_count
            print(f"Sleeping for {REQUESTS_SLEEP_TIME_S} seconds to avoid rate limiting...")
            time.sleep(REQUESTS_SLEEP_TIME_S)
        else:
            print(
                f"Error retrieving news articles: Status Codes: {response.status_code}; {response.text}"
            )
            raise Exception(
                f"Error retrieving news articles: Status Codes: {response.status_code}; {response.text}"
            )


def process_articles(
    articles: List[NewsArticle], unique_articles_db: Set[str], requested_category: str
) -> List[NewsArticle]:
    processed_articles_list = []
    for article in articles:
        # we have observed that a request for a specific category may return articles with a different category
        # we filter them out currently
        # NOTE - we may need special treatment in the future when non parent category is requested
        # as this may still return a child category which we don't want to filter out
        # see: https://learn.microsoft.com/en-us/bing/search-apis/bing-news-search/reference/query-parameters#news-categories-by-market
        if requested_category and article.category != requested_category:
            print(
                f"Article with url: {article.url} has category {article.category} which is different than the requested category {requested_category}, skipping..."
            )
            continue
        if is_unique_article(article, unique_articles_db):
            processed_articles_list.append(article)
    return processed_articles_list


def is_unique_article(article: NewsArticle, unique_articles_db: Set[str]) -> bool:
    # currently a unique article is defined by a unique url
    if article.url in unique_articles_db:
        print(f"Article with url: {article.url} already exists, skipping...")
        return False
    unique_articles_db.add(article.url)
    return True


def discover_trending_topics():
    raise NotImplementedError("Discover trending topics is not yet implemented.")
