from news_aggregator_data_access_layer.constants import ALL_CATEGORIES_STR

# TODO - move to app config
SUMMARIZATION_FAILURE_MESSAGE = "Summarization failed."
SUMMARIZATION_TEMPLATE = """You are a world class news reporter, who is known for writing unbiased, informative, and entertaining articles. Your task is to summarize news articles.
            You will summarize the article in one of the following requested summarization lengths: medium, short.
            A medium summarization is 50% of full length of the original article (or at most 1000 words, whichever is less).
            A short summarization is 10% of full length of the original article (or at most 200 words, whichever is less).
            You will be provided the query that was used to discover the article for additional context.
            If you are unable to access the article or don't feel confident about the result of your summarization you must answer {failure_message}.
            You are given the following article from URL to summarize:
            Article URL: {url}
            Requested summarization length: {length}
            Query: {query}
            After the summarization, please also include the requested summarization length (in this format: "Requested Summarization Length=") and the full words length of the original article (in this format: "Original Article Length=").
            Summary:"""
# NOTE - in the future the template should probably take multiple articles in and aggregate them into a single summary.
BING_NEWS_PUBLISHED_DATE_REGEX = (
    r"^([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}.[0-9]{7}Z)$"
)
# Define the Bing category mapper.
BING_CATEGORIES_MAPPER = {
    ALL_CATEGORIES_STR: ALL_CATEGORIES_STR,
    "business": "Business",
    "entertainment": "Entertainment",
    "health": "Health",
    "politics": "Politics",
    "products": "Products",
    "science-and-technology": "ScienceAndTechnology",
    "sports": "Sports",
    "us": "US",
    "world": "World",
    "world_africa": "World_Africa",
    "world_americas": "World_Americas",
    "world_asia": "World_Asia",
    "world_europe": "World_Europe",
    "world_middleeast": "World_MiddleEast",
}
