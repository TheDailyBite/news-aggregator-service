import os

REGION_NAME = os.environ.get("REGION_NAME", "us-west-1")
# NOTE - this is just used for testing locally
# in production, we use the secrets manager
BING_NEWS_API_KEY = os.environ.get("BING_NEWS_API_KEY", None)
BING_NEWS_API_KEY_SECRET_NAME = os.environ.get("BING_NEWS_API_KEY_SECRET_NAME", "bing-search-key")
DEFAULT_BING_SORTING = os.environ.get("DEFAULT_BING_SORTING", "Relevance")
assert DEFAULT_BING_SORTING in ["Relevance", "Date"]
DEFAULT_BING_FRESHNESS = os.environ.get("DEFAULT_BING_FRESHNESS", "Day")
assert DEFAULT_BING_FRESHNESS in ["Day", "Week", "Month"]
BING_AGGREGATOR_ID = "bing-news"
DEFAULT_MAX_BING_AGGREGATOR_RESULTS = int(
    os.environ.get("DEFAULT_MAX_BING_AGGREGATOR_RESULTS", 100)
)
REQUESTS_SLEEP_TIME_S = 1
DEFAULT_LOGGER_NAME = "news_aggregator_service"
LOCAL_TESTING = os.environ.get("LOCAL_TESTING", "false").lower() in ["true"]
DEFAULT_NAMESPACE = os.environ.get("DEFAULT_NAMESPACE", "NewsAggregatorService")
