from typing import List, Optional

from humps import camelize, pascalize
from pydantic import BaseModel, Field


def to_camel(string: str) -> str:
    return camelize(string)


def to_pascal(string: str) -> str:
    return pascalize(string)


class CamelModel(BaseModel):
    class Config:
        alias_generator = to_camel
        allow_population_by_field_name = True


class PascalModel(BaseModel):
    class Config:
        alias_generator = to_pascal
        allow_population_by_field_name = True


class Error(CamelModel):
    code: str
    message: str
    more_details: str
    parameter: str
    sub_code: str
    value: str


class QueryContext(CamelModel):
    adult_intent: Optional[bool]
    alteration_override_query: Optional[str]
    altered_query: Optional[str]
    original_query: Optional[str]


class APIErrorResponse(CamelModel):
    errors: List[Error]


class Thing(CamelModel):
    name: str  # The name of the entity that the article mentions.


class Organization(CamelModel):
    name: str


class MediaSize(CamelModel):
    height: int
    width: int


class Thumbnail(CamelModel):
    content_url: Optional[str]
    height: int
    width: int


class Image(CamelModel):
    provider: Optional[List[Organization]]
    thumbnail: Optional[Thumbnail]
    url: Optional[str]


class Video(CamelModel):
    allow_https_embed: Optional[bool]
    embed_html: Optional[str]
    motion_thumbnail_url: Optional[str]
    name: str
    thumbnail: MediaSize
    thumbnail_url: Optional[str]


class Query(CamelModel):
    """TODO - add for all once fully defined
    Defines the search query string.

    Attributes:
    - text (str): # A query string that returns the trending topic.
    """

    text: str


class Topic(CamelModel):
    image: Image
    is_breaking_news: bool
    name: str
    news_search_url: str
    query: Query
    web_search_url: str


class SortValue(CamelModel):
    name: str
    id: str
    url: str
    is_selected: Optional[bool]


class NewsArticle(CamelModel):
    category: Optional[str]
    clustered_articles: Optional[List["NewsArticle"]]
    date_published: Optional[
        str
    ]  # The date and time that Bing discovered the article. The date is in the format, YYYY-MM-DDTHH:MM:SS. Not sure why this isn't always present.
    description: str
    headline: Optional[bool]
    Id: Optional[str]
    image: Optional[Image]
    mentions: Optional[List[Thing]]
    name: str
    provider: List[Organization]
    url: str
    video: Optional[Video]


class RelatedTopic(CamelModel):
    related_news: List[NewsArticle]
    name: str
    web_search_url: str


class TrendingTopicsAPIResponse(CamelModel):
    value: List[Topic]


class NewsAnswerAPIResponse(CamelModel):
    related_topics: Optional[List[RelatedTopic]]
    sort: Optional[List[SortValue]]
    total_estimated_matches: Optional[int]
    value: List[NewsArticle]
    query_context: Optional[QueryContext]


class SearchRequest(CamelModel):
    q: str
    count: Optional[int] = 10
    offset: Optional[int] = 0
    mkt: Optional[str] = "en-US"
    safe_search: Optional[str] = "Moderate"
    freshness: Optional[str] = "Day"
    category: Optional[str]
    original_image: Optional[bool] = False
    text_format: Optional[str] = "Raw"


class QueryParams(CamelModel):
    # Use this query parameter and the Accept-Language header only if you specify multiple languages.
    # Otherwise, you should use the mkt and setLang query parameters.
    # This parameter and the mkt query parameter are mutually exclusive — do not specify both.
    cc: Optional[str] = None
    # Use this parameter only with news category requests
    category: Optional[str] = None
    # You may use this parameter along with the offset parameter to page results.
    # For example, if your user interface presents 20 articles per page, set count to 20 and offset to 0 to get the first page of results.
    # For each subsequent page, increment offset by 20 (for example, 0, 20, 40).
    # NOTE - It is possible for multiple pages to include some overlap in results.
    # Use this parameter only when calling the /news/search endpoint.
    count: Optional[int] = 100
    # Filter news articles by the following age values of when they were discovered
    freshness: Optional[str] = "Day"
    mkt: Optional[str] = "en-US"
    offset: Optional[int] = 0
    # A Boolean value that determines whether the Image object include the contentUrl field or only the thumbnail field.
    # Use this parameter only when calling the /news/search endpoint.
    # Do not specify this parameter when calling the /news or /news/trendingtopics endpoint.
    original_img: Optional[bool] = False
    # The user's search query term. If the term is empty (for example, q=), the response includes the top news stories.
    # The term may contain Bing Advanced Operators. For example, to limit results to a specific domain, use the site: operator (q=fishing+site:fishing.contoso.com). Note that the results may contain results from other sites depending on the number of relevant results found on the specified site.
    # Use this parameter only when calling the /news/search endpoint. Do not specify this parameter when calling the /news or /news/trendingtopics endpoint.
    q: Optional[str] = None
    safe_search: Optional[str] = "Moderate"
    set_lang: Optional[str] = "en"
    # The UNIX epoch time (Unix timestamp) that Bing uses to select the trending topics.
    # Bing returns trending topics that it discovered on or after the specified date and time, not the date the topic was published.
    # To use this parameter, also specify the sortBy parameter and set it to Date.
    # NOTE - I believe this is only use with the /news/trendingtopics endpoint.
    since: Optional[int] = None
    sort_by: Optional[str] = None
    text_decorations: Optional[bool] = False
    text_format: Optional[str] = "Raw"


class Headers(BaseModel):
    accept: Optional[str] = Field(default="application/json", alias="Accept")
    accept_language: Optional[str] = Field(default=None, alias="Accept-Language")
    ocp_apim_subscription_key: str = Field(alias="Ocp-Apim-Subscription-Key")

    class Config:
        allow_population_by_field_name = True
