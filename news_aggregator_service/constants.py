from datetime import datetime, timedelta, timezone

from news_aggregator_data_access_layer.constants import ALL_CATEGORIES_STR

DATE_SORTING = "date"
RELEVANCE_SORTING = "relevance"
POPULARITY_SORTING = "popularity"
SUPPORTED_SORTING = {DATE_SORTING, RELEVANCE_SORTING, POPULARITY_SORTING}
# NOTE - no aggregation or sourcing will occur for articles older than this date.
# it could be of course that an aggregator doesn't even go this far back in time which is fine.
OLDEST_SUPPORTED_PUBLISHING_DATE = datetime(2023, 1, 1, tzinfo=timezone.utc)

# TODO - move to app config
SUMMARIZATION_FAILURE_MESSAGE = "Summarization failed."
ARTICLE_SEPARATOR = "===================="
MEDIUM_SUMMARY_DEFINITION = "The summary should be a medium length summary. A medium length summary is between 300-600 words."
SHORT_SUMMARY_DEFINITION = "The summary should be a short length summary. A short length summary should be at most 3 sentences."
# article rewrite
NEWS_REPORTED_INTRO = "You are a world class news reporter, who is known for writing unbiased, informative, and entertaining articles in the ####topic#### space. Don't mention who you are in your articles."
REFINE_REWRITE_PROMPT_TEMPLATE = (
    NEWS_REPORTED_INTRO
    + """
    Your task is to rewrite a news article to ensure that it is unbiased and objective.

    "{text}"

    REWRITE:"""
)
REFINE_REWRITE_REFINE_STEP_TEMPLATE = (
    NEWS_REPORTED_INTRO
    + """
    Your task is to produce a final rewritten news article to ensure that it is unbiased and objective.
    We have provided an existing rewritten article: {existing_answer}
    We have the opportunity to refine the existing rewritten news article (only if needed) with some more context from other news articles covering the same topic below.

    "{text}"
    
    Given the new context, refine the original rewritten news article.
    If the context isn't useful, return the original rewritten news article.
    REWRITE:"""
)
# title rewrite
TITLE_REWRITE_TEMPLATE = (
    NEWS_REPORTED_INTRO
    + """
    Your task is to write an attention grabbing title for a news article based on existing titles for articles covering the same topic that you can use as reference in helping you write this new title.
    The title should be between 5-20 words.

    "{text}"

    TITLE:"""
)
# summary
SUMMARIZATION_TEMPLATE = (
    NEWS_REPORTED_INTRO
    + """
    Your task is to create a summary for a news article to ensure that it is unbiased and objective.
    ####summary_definition####

    "{text}"

    SUMMARY:"""
)
# NOTE - in the future the template should probably take multiple articles in and aggregate them into a single summary.
# Bing News
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
# NewsApi.org
NEWS_API_ORG_PUBLISHED_DATE_REGEX = r"^([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z)$"
# Define the Bing category mapper.
NEWS_API_ORG_CATEGORIES_MAPPER = {
    ALL_CATEGORIES_STR: ALL_CATEGORIES_STR,
    "business": None,
    "entertainment": None,
    "health": None,
    "politics": None,
    "products": None,
    "science-and-technology": None,
    "sports": None,
    "us": None,
    "world": None,
    "world_africa": None,
    "world_americas": None,
    "world_asia": None,
    "world_europe": None,
    "world_middleeast": None,
}
# thenewsapi.com
THE_NEWS_API_COM_PUBLISHED_DATE_REGEX = (
    r"^([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}.[0-9]{6}Z)$"
)
# Define the Bing category mapper.
THE_NEWS_API_COM_CATEGORIES_MAPPER = {
    ALL_CATEGORIES_STR: ALL_CATEGORIES_STR,
    "business": "business",
    "entertainment": "entertainment",
    "health": "health",
    "politics": "politics",
    "products": None,
    "science-and-technology": "science,tech",
    "sports": "sports",
    "us": None,
    "world": None,
    "world_africa": None,
    "world_americas": None,
    "world_asia": None,
    "world_europe": None,
    "world_middleeast": None,
}
