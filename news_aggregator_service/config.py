import os

REGION_NAME = os.environ.get("REGION_NAME", "us-east-1")
# NOTE - this is just used for testing locally
# in production, we use the secrets manager
BING_NEWS_API_KEY = os.environ.get("BING_NEWS_API_KEY", None)
BING_NEWS_API_KEY_SECRET_NAME = os.environ.get("BING_NEWS_API_KEY_SECRET_NAME", "bing-search-key")
NEWS_API_ORG_API_KEY = os.environ.get("NEWS_API_ORG_API_KEY", None)
NEWS_API_ORG_API_KEY_SECRET_NAME = os.environ.get(
    "NEWS_API_ORG_API_KEY_SECRET_NAME", "news-api-org-key"
)
THE_NEWS_API_COM_API_KEY = os.environ.get("THE_NEWS_API_COM_API_KEY", None)
THE_NEWS_API_COM_API_KEY_SECRET_NAME = os.environ.get(
    "THE_NEWS_API_COM_API_KEY_SECRET_NAME", "the-news-api-com-key"
)
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
# this is a multiplier of the max aggregation results for the number of articles to fetch for each aggregator
# this provides a buffer before validation and filtering is applied to the aggregated articles
AGGREGATOR_FETCHED_ARTICLES_MULTIPLIER = int(
    os.environ.get("AGGREGATOR_FETCHED_ARTICLES_MULTIPLIER", 2)
)
# this is the approximate max number of articles to publish each day for each topic
DEFAULT_DAILY_PUBLISHING_LIMIT = int(os.environ.get("DEFAULT_DAILY_PUBLISHING_LIMIT", 5))
# AGGREGATOR IDS ARE NAMED camelCase
DEFAULT_MAX_BING_AGGREGATOR_RESULTS = int(
    os.environ.get("DEFAULT_MAX_BING_AGGREGATOR_RESULTS", 100)
)
REQUESTS_SLEEP_TIME_S = 1
DEFAULT_LOGGER_NAME = "news_aggregator_service"
LOCAL_TESTING = os.environ.get("LOCAL_TESTING", "false").lower() in ["true"]
DEFAULT_NAMESPACE = os.environ.get("DEFAULT_NAMESPACE", "NewsAggregatorService")
# NOTE - the inventory size impacts the clustering quality. Anectodatlly, 10 is a good number.
MINIMUM_ARTICLE_INVENTORY_SIZE_TO_SOURCE = int(
    os.environ.get("MINIMUM_ARTICLE_INVENTORY_SIZE_TO_SOURCE", 10)
)
SUMMARIZATION_MODEL_NAME = os.environ.get("SUMMARIZATION_MODEL_NAME", "gpt-3.5-turbo")
LONG_SUMMARIZATION_MODEL_NAME = os.environ.get("LONG_SUMMARIZATION_MODEL_NAME", "gpt-3.5-turbo-16k")
# TODO - what should this be?
SUMMARIZATION_TEMPERATURE = float(os.environ.get("SUMMARIZATION_TEMPERATURE", 0.0))
os.environ["TOKENIZERS_PARALLELISM"] = "false"
NEWS_AGGREGATION_QUEUE_NAME = os.environ.get(
    "NEWS_AGGREGATION_QUEUE_NAME", "news-aggregation-queue.fifo"
)
NEWS_SOURCING_QUEUE_NAME = os.environ.get("NEWS_SOURCING_QUEUE_NAME", "news-sourcing-queue.fifo")
DAILY_SOURCING_FREQUENCY = float(os.environ.get("DAILY_SOURCING_FREQUENCY", 1))
NEWS_LANGUAGE = os.environ.get("NEWS_LANGUAGE", "en")
