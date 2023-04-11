from typing import Dict, Union

import json
import os
import pprint
from datetime import datetime, timedelta

import requests

from news_aggregator_service.aggregators.models import bing_news
from news_aggregator_service.config import BING_NEWS_API_KEY_SECRET_NAME
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

# Define search parameters
test_search_term = "Generative AI"
test_category = "Technology"

# Get current date and date from 24 hours ago
now = datetime.utcnow()
yesterday = now - timedelta(days=1)

# Format dates for Bing News Search API query
now_str = now.strftime("%Y-%m-%dT%H:%M:%SZ")
yesterday_str = yesterday.strftime("%Y-%m-%dT%H:%M:%SZ")

# Set headers for API request
headers = bing_news.Headers(ocp_apim_subscription_key=subscription_key)


def run(search_term: str, category: str, freshness):
    articles = []
    offset = 0
    count = 100
    total_estimated_matches = 0
    page = 0
    print(
        f"Retrieving news articles for search term: {search_term}, category: {category} and freshness: {freshness}..."
    )
    while True:
        # Set query parameters for API request
        params = bing_news.QueryParams(
            category=category,
            sort_by="Relevance",
            freshness=freshness,
            q=search_term,
            offset=offset,
            count=count,
        )
        # Send API request
        response = requests.get(
            search_url, headers=headers.dict(by_alias=True), params=params.dict(by_alias=True)
        )
        if response.status_code == 200:
            news_answer_json = response.json()
            news_answer = bing_news.NewsAnswerAPIResponse.parse_obj(news_answer_json)
            print(f"Query Context: {news_answer.query_context}")
            if news_answer.total_estimated_matches is None:
                return articles
            if total_estimated_matches == 0:
                total_estimated_matches = news_answer.total_estimated_matches
            arts = news_answer.value
            articles.extend(arts)
            new_arts = len(arts)
            print(
                f"Retrieved {new_arts} new articles. Total articles: {len(articles)}; Page {page}; Offset: {offset}; Total estimated matches: {total_estimated_matches}"
            )
            if len(articles) >= total_estimated_matches:
                return articles
            page += 1
            offset += len(arts)
        else:
            print(
                f"Error retrieving news articles: Status Codes: {response.status_code}; {response.text}"
            )
            raise Exception(
                f"Error retrieving news articles: Status Codes: {response.status_code}; {response.text}"
            )


# Print list of extracted article data
# pprint(articles)
