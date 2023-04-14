import os

REGION_NAME = os.environ.get("REGION_NAME", "us-west-1")
BING_NEWS_API_KEY_SECRET_NAME = os.environ.get("BING_NEWS_API_KEY_SECRET_NAME", "bing-search-key")
DEFAULT_BING_SORTING = os.environ.get("DEFAULT_BING_SORTING", "Relevance")
assert DEFAULT_BING_SORTING in ["Relevance", "Date"]
DEFAULT_BING_FRESHNESS = os.environ.get("DEFAULT_BING_FRESHNESS", "Day")
assert DEFAULT_BING_FRESHNESS in ["Day", "Week", "Month"]
BING_AGGREGATOR_ID = "bing-news"
