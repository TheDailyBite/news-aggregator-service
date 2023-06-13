from news_aggregator_data_access_layer.constants import ALL_CATEGORIES_STR

# TODO - move to app config
SUMMARIZATION_FAILURE_MESSAGE = "Summarization failed."
ARTICLE_SEPARATOR = "===================="
MEDIUM_SUMMARY_DEFINITION = "The summary should be a medium length summary. A medium length summary is 50% of length of the original text (at most 1000 words)."
SHORT_SUMMARY_DEFINITION = "The summary should be a short length summary. A short length summary is 10% of length of the original text (at most 200 words)."
# rewrite
NEWS_REPORTED_INTRO = "You are a world class news reporter, who is known for writing unbiased, informative, and entertaining articles in the ####topic#### space. "
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
# summary
SUMMARIZATION_TEMPLATE = (
    NEWS_REPORTED_INTRO
    + """
    Your task is to create a summary for a news article to ensure that it is unbiased and objective.
    ####summary_definition####

    "{text}"

    SUMMARY:"""
)
# TODO - can probably remove these
MAP_SUMMARIZATION_TEMPLATE = (
    NEWS_REPORTED_INTRO
    + """
            Your task is to create a summary for a news article to ensure that it is unbiased and objective.
            ####summary_definition####

            "{text}"

            SUMMARY:"""
)
COMBINE_SUMMARIZATION_TEMPLATE = (
    NEWS_REPORTED_INTRO
    + """
            Your task is to create a summary for a news article to ensure that it is unbiased and objective. 
            ####summary_definition####

            "{text}"

            SUMMARY:"""
)
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
