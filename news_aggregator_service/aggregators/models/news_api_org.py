from typing import List, Optional

from enum import Enum

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


class SortByEnum(str, Enum):
    RELEVANCE = "relevancy"
    POPULARITY = "popularity"
    PUBLISHED_AT = "publishedAt"


class SearchInEnum(str, Enum):
    TITLE = "title"
    DESCRIPTION = "description"
    CONTENT = "content"
    TITLE_DESCRIPTION = "title,description"
    TITLE_CONTENT = "title,content"
    DESCRIPTION_CONTENT = "description,content"
    TITLE_DESCRIPTION_CONTENT = "title,description,content"


class StatusEnum(str, Enum):
    OK = "ok"
    ERROR = "error"


class Source(CamelModel):
    id: Optional[str]
    name: str


class Article(CamelModel):
    source: Source
    author: Optional[str] = ""
    title: str
    # A description or snippet from the article.
    description: str
    url: str
    url_to_image: Optional[str]
    # The date and time that the article was published, in UTC (+000)
    published_at: str
    # The unformatted content of the article, where available. This is truncated to 200 chars.
    content: Optional[str]


class EverythingV2Response(CamelModel):
    status: StatusEnum
    code: Optional[str]
    message: Optional[str]
    # The total number of results available for your request.
    # Only a limited number are shown at a time though, so use the page parameter in your requests to page through them.
    total_results: int
    articles: list[Article]


class Headers(BaseModel):
    api_key: str = Field(alias="X-Api-Key")

    class Config:
        allow_population_by_field_name = True


class EverythingV2Request(CamelModel):
    q: str
    search_in: Optional[str]
    # A comma-seperated string of identifiers (maximum 20) for the news sources or blogs you want headlines from.
    # Use the /sources endpoint to locate these programmatically or look at the sources index.
    sources: Optional[str] = None
    # A comma-seperated string of domains (eg bbc.co.uk, techcrunch.com, engadget.com) to restrict the search to.
    domains: Optional[str] = None
    exclude_domains: Optional[str] = None
    # A date and optional time for the oldest article allowed. This should be in ISO 8601 format (e.g. 2023-06-15 or 2023-06-15T18:38:46)
    from_date_iso8061: str = Field(alias="from")
    to_date_iso8061: str = Field(alias="to")
    # The 2-letter ISO-639-1 code of the language you want to get headlines for. Possible options: ar,de,en,es,fr,he,it,nl,no,pt,ru,se,ud,zh.
    language: str
    # relevancy = articles more closely related to q come first.
    # popularity = articles from popular sources and publishers come first.
    # publishedAt = newest articles come first.
    sort_by: SortByEnum
    page_size: int = 100
    page: int = 1
