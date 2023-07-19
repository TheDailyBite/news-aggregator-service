from typing import List, Optional

from enum import Enum

from pydantic import BaseModel, Field


class SortByEnum(str, Enum):
    RELEVANCE = "relevance_score"
    PUBLISHED_AT = "published_at"


class SearchInEnum(str, Enum):
    TITLE = "title"
    DESCRIPTION = "description"
    KEYWORDS = "keywords"
    MAIN_TEXT = "main_text"

    TITLE_DESCRIPTION = "title,description"
    TITLE_KEYWORDS = "title,keywords"
    TITLE_MAIN_TEXT = "title,main_text"
    DESCRIPTION_KEYWORDS = "description,keywords"
    DESCRIPTION_MAIN_TEXT = "description,main_text"
    KEYWORDS_MAIN_TEXT = "keywords,main_text"

    TITLE_DESCRIPTION_KEYWORDS = "title,description,keywords"
    TITLE_DESCRIPTION_MAIN_TEXT = "title,description,main_text"
    TITLE_KEYWORDS_MAIN_TEXT = "title,keywords,main_text"
    DESCRIPTION_KEYWORDS_MAIN_TEXT = "description,keywords,main_text"

    TITLE_DESCRIPTION_KEYWORDS_MAIN_TEXT = "title,description,keywords,main_text"


class Meta(BaseModel):
    found: int
    returned: int
    limit: int
    page: int


class Article(BaseModel):
    uuid: str
    title: str
    description: str
    keywords: str
    snippet: str
    url: str
    image_url: str
    language: str
    published_at: str
    source: str
    categories: list[str]
    relevance_score: Optional[float]
    locale: Optional[str]


class AllNewsResponse(BaseModel):
    meta: Meta
    data: list[Article]


class AllNewsRequest(BaseModel):
    api_token: str
    search: str
    search_fields: Optional[str]
    categories: Optional[str]
    exclude_categories: Optional[str]
    # A comma-seperated string of domains (eg bbc.co.uk, techcrunch.com, engadget.com) to restrict the search to.
    domains: Optional[str] = None
    exclude_domains: Optional[str] = None
    # Comma separated list of source_ids to include. List of source_ids can be obtained through our Sources endpoint, found further down this page.
    source_ids: Optional[str] = None
    exclude_source_ids: Optional[str] = None
    # Comma separated list of language to include. Default is all.
    language: str
    # Find all articles published before the specified date. Supported formats include: Y-m-d\TH:i:s | Y-m-d\TH:i | Y-m-d\TH | Y-m-d | Y-m | Y.
    published_before: Optional[str] = None
    # Find all articles published after the specified date. Supported formats include: Y-m-d\TH:i:s | Y-m-d\TH:i | Y-m-d\TH | Y-m-d | Y-m | Y.
    published_after: Optional[str] = None
    # Find all articles published on the specified date. Supported formats include: Y-m-d.
    published_on: Optional[str] = None
    # Sort by published_at or relevance_score (only available when used in conjunction with search). Default is published_at unless search is used and sorting by published_at is not included, in which case relevance_score is used.
    sort: str
    # Specify the number of articles you want to return in the request. The maximum limit is based on your plan. The default limit is the maximum specified for your plan.
    limit: Optional[int] = None
    # Use this to paginate through the result set. Default is 1. Note that the max result set can't exceed 20,000. For example if your limit is 50, the max page you can have is 400 (50 * 400 = 20,000).
    page: Optional[int] = None


class Error(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: Error
