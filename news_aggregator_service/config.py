import os

REGION_NAME = os.environ.get("REGION_NAME", "us-west-1")
# NOTE - this is just used for testing locally
# in production, we use the secrets manager
BING_NEWS_API_KEY = os.environ.get("BING_NEWS_API_KEY", None)
BING_NEWS_API_KEY_SECRET_NAME = os.environ.get("BING_NEWS_API_KEY_SECRET_NAME", "bing-search-key")
FAKE_OPENAI_API_KEY = "sk-000000000000000000000000000000000000000000000000"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", None)
OPENAI_API_KEY_SECRET_NAME = os.environ.get("OPENAI_API_KEY_SECRET_NAME", "openai-api-key")
FAKE_HUGGINGFACE_API_KEY = "hf_0000000000000000000000000000000000"
HUGGINGFACE_API_KEY = os.environ.get("HUGGINGFACE_API_KEY", None)
HUGGINGFACE_API_KEY_SECRET_NAME = os.environ.get(
    "HUGGINGFACE_API_KEY_SECRET_NAME", "huggingface-api-key"
)
FAKE_PINECONE_API_KEY = "838f27c8-96da-4afb-8474-7eb577cda375"
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", None)
PINECONE_API_KEY_SECRET_NAME = os.environ.get("PINECONE_API_KEY_SECRET_NAME", "pinecone-api-key")
DEFAULT_BING_SORTING = os.environ.get("DEFAULT_BING_SORTING", "Relevance")
assert DEFAULT_BING_SORTING in ["Relevance", "Date"]
# this is a multiplier of the max aggregation results for the number of articles to fetch for each aggregator
# this provides a buffer before validation and filtering is applied to the aggregated articles
AGGREGATOR_FETCHED_ARTICLES_MULTIPLIER = int(
    os.environ.get("AGGREGATOR_FETCHED_ARTICLES_MULTIPLIER", 4)
)
# this is the approximate max number of articles to publish each day for each topic
DEFAULT_DAILY_PUBLISHING_LIMIT = int(os.environ.get("DEFAULT_DAILY_PUBLISHING_LIMIT", 5))
# AGGREGATOR IDS ARE NAMED camelCase
BING_AGGREGATOR_ID = "bingNews"
DEFAULT_MAX_BING_AGGREGATOR_RESULTS = int(
    os.environ.get("DEFAULT_MAX_BING_AGGREGATOR_RESULTS", 100)
)
# NOTE - comma separated list
DEFAULT_ENABLED_AGGREGATORS = f"{BING_AGGREGATOR_ID}"
ENABLED_AGGREGATORS = [
    a.strip() for a in os.environ.get("ENABLED_AGGREGATORS", DEFAULT_ENABLED_AGGREGATORS).split(",")
]
REQUESTS_SLEEP_TIME_S = 1
DEFAULT_LOGGER_NAME = "news_aggregator_service"
LOCAL_TESTING = os.environ.get("LOCAL_TESTING", "false").lower() in ["true"]
DEFAULT_NAMESPACE = os.environ.get("DEFAULT_NAMESPACE", "NewsAggregatorService")
MINIMUM_ARTICLE_INVENTORY_SIZE_TO_SOURCE = int(os.environ.get("MINIMUM_ARTICLE_INVENTORY_SIZE", 5))
SUMMARIZATION_MODEL_NAME = os.environ.get("SUMMARIZATION_MODEL_NAME", "gpt-3.5-turbo")
# TODO - what should this be?
SUMMARIZATION_TEMPERATURE = float(os.environ.get("SUMMARIZATION_TEMPERATURE", 0.0))
ARTICLE_CLUSTERING_MODEL_NAME = os.environ.get("CLUSTERING_MODEL_NAME", "gpt-3.5-turbo")
ARTICLE_CLUSTERING_TEMPERATURE = float(os.environ.get("CLUSTERING_TEMPERATURE", 0.0))
os.environ["TOKENIZERS_PARALLELISM"] = "false"
