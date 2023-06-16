from typing import Any, Dict, List, Optional, Set, Tuple, Union

import json
import os
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

import boto3
import requests
from news_aggregator_data_access_layer.assets.news_assets import CandidateArticles, RawArticle
from news_aggregator_data_access_layer.config import S3_ENDPOINT_URL
from news_aggregator_data_access_layer.constants import (
    ALL_CATEGORIES_STR,
    AggregatorRunStatus,
    NewsAggregatorsEnum,
    ResultRefTypes,
)
from news_aggregator_data_access_layer.models.dynamodb import (
    AggregatorRuns,
    TrustedNewsProviders,
    get_current_dt_utc_attribute,
    get_uuid4_attribute,
)
from news_aggregator_data_access_layer.utils.datetime import generate_standardized_published_date
from news_aggregator_data_access_layer.utils.news_topics import AggregatorCategoryMapper
from news_aggregator_data_access_layer.utils.s3 import (
    dt_to_lexicographic_date_dash_s3_prefix,
    dt_to_lexicographic_date_s3_prefix,
)

from news_aggregator_service.aggregators.models import bing_news, news_api_org
from news_aggregator_service.aggregators.models.aggregations import AggregationResults
from news_aggregator_service.config import (
    BING_NEWS_API_KEY,
    BING_NEWS_API_KEY_SECRET_NAME,
    DEFAULT_MAX_BING_AGGREGATOR_RESULTS,
    NEWS_API_ORG_API_KEY,
    NEWS_API_ORG_API_KEY_SECRET_NAME,
    REGION_NAME,
    REQUESTS_SLEEP_TIME_S,
)
from news_aggregator_service.constants import (
    BING_CATEGORIES_MAPPER,
    BING_NEWS_PUBLISHED_DATE_REGEX,
    DATE_SORTING,
    NEWS_API_ORG_CATEGORIES_MAPPER,
    NEWS_API_ORG_PUBLISHED_DATE_REGEX,
    POPULARITY_SORTING,
    RELEVANCE_SORTING,
    SUPPORTED_SORTING,
    THE_NEWS_API_COM_CATEGORIES_MAPPER,
    THE_NEWS_API_COM_PUBLISHED_DATE_REGEX,
)
from news_aggregator_service.exceptions import UnsupportedCategoryException
from news_aggregator_service.utils.secrets import get_secret
from news_aggregator_service.utils.telemetry import setup_logger

logger = setup_logger(__name__)


class AggregatorInterface(ABC):
    @abstractmethod
    def get_candidates_for_topic(
        self,
        topic_id: str,
        topic: str,
        category: str,
        start_time: datetime,
        end_time: datetime,
        sorting: str,
        max_aggregator_results: int,
        fetched_articles_count: int,
        trusted_news_providers: Optional[list[TrustedNewsProviders]] = [],
    ) -> tuple[list[RawArticle], datetime, datetime]:
        pass

    def aggregate_candidates_for_topic(
        self,
        topic_id: str,
        topic: str,
        category: str,
        start_time: datetime,
        end_time: datetime,
        max_aggregator_results: int,
        fetched_articles_count: int,
        trusted_news_providers: Optional[list[TrustedNewsProviders]] = [],
    ) -> tuple[AggregationResults, datetime]:
        aggregation_start_dt = datetime.now(timezone.utc)
        aggregation_start_date = dt_to_lexicographic_date_s3_prefix(aggregation_start_dt)
        if max_aggregator_results <= 0:
            raise ValueError(
                f"max_aggregator_results must be a positive integer, got: {max_aggregator_results}"
            )
        if not self.is_category_supported(category):
            failure_message = (
                f"Category {category} is not supported by aggregator {self.aggregator_id}"
            )
            logger.warning(failure_message)
            raise UnsupportedCategoryException(failure_message)
        aggregator_run = AggregatorRuns(
            aggregation_start_date=aggregation_start_date,
            aggregation_run_id=get_uuid4_attribute(),
            aggregator_id=self.aggregator_id,
            topic_id=topic_id,
            aggregation_data_start_time=start_time,
            aggregation_data_end_time=end_time,
            execution_start_time=get_current_dt_utc_attribute(),
        )
        aggregator_run.save(condition=AggregatorRuns.aggregation_run_id.does_not_exist())
        aggregation_run_id = aggregator_run.aggregation_run_id
        try:
            (
                candidates_for_topic,
                start_published_dt,
                end_published_dt,
            ) = self.get_candidates_for_topic(
                topic_id,
                topic,
                category,
                start_time,
                end_time,
                self.sorting,
                max_aggregator_results,
                fetched_articles_count,
                trusted_news_providers,
            )
            logger.info(
                f"Found {len(candidates_for_topic)} candidates for topic: {topic} and requested category: {category} for timeframe {start_time} - {end_time}. Start published date of aggregated articles: {start_published_dt}, End published date: {end_published_dt}"
            )
            aggregation_result = AggregationResults(
                articles_aggregated_count=len(candidates_for_topic),
                topic=topic,
                requested_category=category,
                data_start_time=start_published_dt.isoformat(),
                data_end_time=end_published_dt.isoformat(),
                sorting=self.sorting,
            )
            store_bucket, store_paths = self.store_candidates(
                candidates_for_topic, topic_id, aggregation_run_id
            )
            store_paths_str = ",".join(store_paths)
            aggregation_result.store_paths = store_paths_str
            update_actions = [
                AggregatorRuns.aggregation_data_start_time.set(start_published_dt),
                AggregatorRuns.aggregation_data_end_time.set(end_published_dt),
                AggregatorRuns.run_status.set(AggregatorRunStatus.COMPLETE),
                AggregatorRuns.execution_end_time.set(get_current_dt_utc_attribute()),
                AggregatorRuns.aggregated_articles_ref.set(
                    {
                        "type": ResultRefTypes.S3.value,
                        "bucket": store_bucket,
                        "paths": store_paths_str,
                    }
                ),
                AggregatorRuns.aggregated_articles_count.set(len(candidates_for_topic)),
            ]
            aggregator_run.update(actions=update_actions)
            return aggregation_result, end_published_dt
        except Exception as e:
            logger.error(
                f"Error while aggregating news with aggregator {self.aggregator_id} for topic: {topic} and category: {category} and timeframe {start_time} - {end_time}: {e}",
                exc_info=True,
            )
            aggregator_run.update(
                actions=[
                    AggregatorRuns.run_status.set(AggregatorRunStatus.FAILED),
                    AggregatorRuns.execution_end_time.set(get_current_dt_utc_attribute()),
                ]
            )
            raise

    @abstractmethod
    def postprocess_articles(
        self,
        candidates: list[Any],
        topic_id: str,
        topic: str,
        requested_category: str,
        mapped_requested_category: str,
        start_time: datetime,
        end_time: datetime,
        sorting: str,
        max_aggregator_results: int,
        trusted_news_providers: Optional[list[TrustedNewsProviders]] = [],
    ) -> tuple[list[RawArticle], datetime, datetime]:
        pass

    @property
    @abstractmethod
    def aggregator_id(self):
        pass

    @property
    @abstractmethod
    def category_mapper(self):
        pass

    @property
    @abstractmethod
    def sorting(self):
        pass

    @property
    @abstractmethod
    def historical_articles_days_ago_start(self):
        pass

    def is_category_supported(self, category: str) -> bool:
        return self.category_mapper.get_category(category) is not None

    def generate_article_id(
        self,
        article_idx: int,
    ) -> str:
        padded_article_idx = str(article_idx).zfill(6)
        return f"{padded_article_idx}#{str(uuid.uuid4())}"

    def get_api_key(self, api_key: Optional[str], api_key_secret_name: str) -> str:
        if api_key:
            return api_key
        else:
            return get_secret(api_key_secret_name)

    def store_candidates(
        self, aggregated_candidates: list[RawArticle], topic_id: str, aggregation_run_id: str
    ) -> tuple[str, list[str]]:
        logger.info(
            f"Storing {len(aggregated_candidates)} total candidates for topic {topic_id} for aggregation run id {aggregation_run_id}..."
        )
        s3_client = boto3.client("s3", region_name=REGION_NAME, endpoint_url=S3_ENDPOINT_URL)
        candidate_articles = CandidateArticles(
            ResultRefTypes.S3,
            topic_id=topic_id,
        )
        kwargs = {
            "s3_client": s3_client,
            "articles": aggregated_candidates,
            "aggregation_run_id": aggregation_run_id,
        }
        store_bucket, store_prefixes = candidate_articles.store_articles(**kwargs)
        return store_bucket, store_prefixes


class BingAggregator(AggregatorInterface):
    def __init__(self):
        self._aggregator_id = NewsAggregatorsEnum.BING_NEWS.value
        self.base_url = "https://api.bing.microsoft.com"
        self.search_url = f"{self.base_url}/v7.0/news/search"
        self.api_key = self.get_api_key(BING_NEWS_API_KEY, BING_NEWS_API_KEY_SECRET_NAME)
        self._category_mapper = AggregatorCategoryMapper(BING_CATEGORIES_MAPPER)
        self.headers = bing_news.Headers(ocp_apim_subscription_key=self.api_key)  # type: ignore
        # bing news search only supports "freshness" topicing of news with supported values of "Day", "Week", "Month"
        self.supported_timeframes_days = {1: "Day", 7: "Week", 30: "Month"}
        # this comes from the documentation
        self.max_articles_per_request = 100
        self.published_date_regex = BING_NEWS_PUBLISHED_DATE_REGEX
        self.published_date_attr_name = "date_published"
        self.start_page = 0
        self._sorting = RELEVANCE_SORTING
        assert self._sorting in SUPPORTED_SORTING
        self.sorting_mapping = {
            RELEVANCE_SORTING: bing_news.SortByEnum.RELEVANCE,
            DATE_SORTING: news_api_org.SortByEnum.PUBLISHED_AT,
        }
        self.sorting_api_param = self.sorting_mapping[self._sorting]
        self._historical_articles_days_ago_start = timedelta(days=-1)

    @property
    def aggregator_id(self):
        return self._aggregator_id

    @property
    def category_mapper(self):
        return self._category_mapper

    @property
    def sorting(self):
        return self._sorting

    @property
    def historical_articles_days_ago_start(self):
        return self._historical_articles_days_ago_start

    def _get_data_timeframe(self, start_time: datetime, end_time: datetime) -> str:
        timeframe_days = (end_time - start_time).days
        if timeframe_days not in self.supported_timeframes_days:
            raise ValueError(
                f"Timeframe of {timeframe_days} days is not supported by bing news search, supported timeframes are: {self.supported_timeframes_days}"
            )
        return self.supported_timeframes_days[timeframe_days]

    def postprocess_articles(
        self,
        candidates: list[Any],
        topic_id: str,
        topic: str,
        requested_category: str,
        mapped_requested_category: str,
        start_time: datetime,
        end_time: datetime,
        sorting: str,
        max_aggregator_results: int,
        trusted_news_providers: Optional[list[TrustedNewsProviders]] = [],
    ) -> tuple[list[RawArticle], datetime, datetime]:
        # TODO - at some point candidates can be some interface class which will have guaranteed certain fields
        aggregated_articles: list[RawArticle] = []
        min_start_time = datetime.max.replace(tzinfo=timezone.utc)
        max_end_time = datetime.min.replace(tzinfo=timezone.utc)
        if sorting == DATE_SORTING:
            raise NotImplementedError(
                f"Sorting by {sorting} is not implemented yet in post-processing."
            )
        article_idx = 0
        for article in candidates:
            if len(aggregated_articles) >= max_aggregator_results:
                break
            # we have observed that a request for a specific category may return articles with a different category
            # we filter them out currently
            # NOTE - we may need special treatment in the future when non parent category is requested
            # as this may still return a child category which we don't want to filter out
            # see: https://learn.microsoft.com/en-us/bing/search-apis/bing-news-search/reference/topic-parameters#news-categories-by-market
            if (
                mapped_requested_category != ALL_CATEGORIES_STR
                and article.category != mapped_requested_category
            ):
                logger.info(
                    f"Article with url: {article.url} has category {article.category} which is different than the mapped requested category {mapped_requested_category}, skipping..."
                )
                continue
            standardized_published_date = generate_standardized_published_date(
                getattr(article, self.published_date_attr_name), self.published_date_regex
            )
            standardized_published_dt = datetime.fromisoformat(standardized_published_date)
            if standardized_published_dt < start_time or standardized_published_dt > end_time:
                logger.error(
                    f"Article with url: {article.url} has published date {standardized_published_dt} which is outside the requested timeframe {start_time} - {end_time}, skipping..."
                )
                continue
            if standardized_published_dt < min_start_time:
                min_start_time = standardized_published_dt
            if standardized_published_dt > max_end_time:
                max_end_time = standardized_published_dt
            article_id = self.generate_article_id(article_idx)
            logger.info(f"Generated article id {article_id} for article with url: {article.url}")
            raw_article = RawArticle(
                article_id=article_id,
                aggregator_id=self.aggregator_id,
                dt_published=standardized_published_date,
                aggregation_index=article_idx,
                topic_id=topic_id,
                topic=topic,
                requested_category=requested_category,
                category=article.category,
                title=article.name,
                url=article.url,
                article_data=article.json(),
                sorting=sorting,
            )
            # NOTE - this will extract article text and more data from the article url
            raw_article.process_article_data()
            if not raw_article.article_processed_data:
                logger.warning(
                    f"Article with url: {article.url} has no processed data, skipping..."
                )
                continue
            aggregated_articles.append(raw_article)
            article_idx += 1
        return aggregated_articles, min_start_time, max_end_time

    def get_candidates_for_topic(
        self,
        topic_id: str,
        topic: str,
        category: str,
        start_time: datetime,
        end_time: datetime,
        sorting: str,
        max_aggregator_results: int,
        fetched_articles_count: int,
        trusted_news_providers: Optional[list[TrustedNewsProviders]] = [],
    ) -> tuple[list[RawArticle], datetime, datetime]:
        candidates: list[bing_news.NewsArticle] = []
        offset = 0
        total_estimated_matches = 0
        page = self.start_page
        data_timeframe = self._get_data_timeframe(start_time, end_time)
        aggregator_mapped_category = self.category_mapper.get_category(category)
        logger.info(
            f"Retrieving a max of {fetched_articles_count} news articles results for search term: {topic}, requested category: {category} (mapped category {aggregator_mapped_category}) and timeframe: {data_timeframe}..."
        )
        # currently we use the url only to check for duplicates
        unique_articles_db: set[str] = set()
        # NOTE - we will try to fetch fetched_articles_count articles
        # we will only remove duplicate urls ("preprocessing")
        # after this is complete, we will postprocess the results which will perform filtering and validation
        # on the fetched articles and impose the max_aggregator_results
        while True:
            if len(candidates) >= fetched_articles_count:
                logger.info(
                    f"Reached fetched articles count, will process {len(candidates)} candidates..."
                )
                break
            # Set topic parameters for API request
            params = bing_news.QueryParams(
                sort_by=sorting,
                freshness=data_timeframe,
                q=topic,
                offset=offset,
                count=self.max_articles_per_request,
            )
            if aggregator_mapped_category != ALL_CATEGORIES_STR:
                params.category = aggregator_mapped_category
            # Send API request
            response = requests.get(
                self.search_url,
                headers=self.headers.dict(by_alias=True),
                params=params.dict(by_alias=True),
                timeout=5,
            )
            logger.info(f"Request sent URL: {response.request.url}...")
            if response.status_code == 200:
                news_answer_json = response.json()
                news_answer = bing_news.NewsAnswerAPIResponse.parse_obj(news_answer_json)
                logger.info(f"Query Context: {news_answer.query_context}")
                if not news_answer.value:
                    logger.info("No more articles found in latest request, breaking...")
                    break
                total_estimated_matches = news_answer.total_estimated_matches  # type: ignore
                articles = news_answer.value
                new_articles_count = len(articles)
                preprocessed_articles = self.preprocess_articles(articles, unique_articles_db)
                preprocessed_new_articles_count = len(preprocessed_articles)
                needed_articles_count = fetched_articles_count - len(candidates)
                if preprocessed_new_articles_count == 0:
                    logger.info(
                        f"Preprocessed articles count is 0, breaking despite needed articles count being {needed_articles_count}... (total articles retrieved in aggregation: {len(candidates)}; Page {page}; Offset: {offset}; Total estimated matches: {total_estimated_matches})"
                    )
                    break
                preprocessed_articles = preprocessed_articles[:needed_articles_count]
                candidates.extend(preprocessed_articles)
                logger.info(
                    f"Retrieved {new_articles_count} new articles of which {preprocessed_new_articles_count} are unique. Needed articles to reach max {needed_articles_count}. Total articles retrieved in aggregation: {len(candidates)}; Page {page}; Offset: {offset}; Total estimated matches: {total_estimated_matches}"
                )
                page += 1
                offset += new_articles_count
                logger.info(
                    f"Sleeping for {REQUESTS_SLEEP_TIME_S} seconds to avoid rate limiting..."
                )
                time.sleep(REQUESTS_SLEEP_TIME_S)
            else:
                logger.error(
                    f"Error retrieving news articles: Status Codes: {response.status_code}; {response.text}",
                    exc_info=True,
                )
                raise Exception(
                    f"Error retrieving news articles: Status Codes: {response.status_code}; {response.text}"
                )
        logger.info(
            f"Finished retrieving news articles. Total candidates retrieved {len(candidates)}. Max aggregator results: {max_aggregator_results}. Fetched articles count {fetched_articles_count}. Post-processing will now occur to filter and ensure result accuracy..."
        )
        return self.postprocess_articles(
            candidates,
            topic_id,
            topic,
            category,
            aggregator_mapped_category,
            start_time,
            end_time,
            sorting,
            max_aggregator_results,
            trusted_news_providers,
        )

    def preprocess_articles(
        self, articles: list[bing_news.NewsArticle], unique_articles_db: set[str]
    ) -> list[bing_news.NewsArticle]:
        # TODO - these can be moved to abc when input articles is a common model
        preprocessed_articles_list = []
        for article in articles:
            # TODO - in the future we could rely on additional processing (for example from NewsPlease) to get the published date if the aggregator doesn't provide it
            if not article.date_published:
                logger.warning(
                    f"Article with url: {article.url} has no date published, skipping..."
                )
                continue
            if self.is_unique_article(article, unique_articles_db):
                preprocessed_articles_list.append(article)
        return preprocessed_articles_list

    def is_unique_article(
        self, article: bing_news.NewsArticle, unique_articles_db: set[str]
    ) -> bool:
        # currently a unique article is defined by a unique url
        if article.url in unique_articles_db:
            logger.info(f"Article with url: {article.url} already exists, skipping...")
            return False
        unique_articles_db.add(article.url)
        return True


class NewsApiOrgAggregator(AggregatorInterface):
    def __init__(self):
        self._aggregator_id = NewsAggregatorsEnum.NEWS_API_ORG.value
        self.base_url = "https://newsapi.org"
        self.search_url = f"{self.base_url}/v2/everything"
        self.api_key = self.get_api_key(NEWS_API_ORG_API_KEY, NEWS_API_ORG_API_KEY_SECRET_NAME)
        self._category_mapper = AggregatorCategoryMapper(NEWS_API_ORG_CATEGORIES_MAPPER)
        self.headers = news_api_org.Headers(api_key=self.api_key)  # type: ignore
        # this comes from the documentation
        self.max_articles_per_request = 100
        self.published_date_regex = NEWS_API_ORG_PUBLISHED_DATE_REGEX
        self.published_date_attr_name = "published_at"
        self.request_date_format = "%Y-%m-%dT%H:%M:%S"
        self.start_page = 1
        self._sorting = RELEVANCE_SORTING
        assert self._sorting in SUPPORTED_SORTING
        self.sorting_mapping = {
            RELEVANCE_SORTING: news_api_org.SortByEnum.RELEVANCE,
            POPULARITY_SORTING: news_api_org.SortByEnum.POPULARITY,
            DATE_SORTING: news_api_org.SortByEnum.PUBLISHED_AT,
        }
        self.sorting_api_param = self.sorting_mapping[self._sorting]
        # TODO - this should change after upgrading to premium subscription
        self._historical_articles_days_ago_start = timedelta(days=-30)

    @property
    def aggregator_id(self):
        return self._aggregator_id

    @property
    def category_mapper(self):
        return self._category_mapper

    @property
    def sorting(self):
        return self._sorting

    @property
    def historical_articles_days_ago_start(self):
        return self._historical_articles_days_ago_start

    def _get_data_timeframe(self, start_time: datetime, end_time: datetime) -> tuple[str, str]:
        start_time_str = start_time.strftime(self.request_date_format)
        end_time_str = end_time.strftime(self.request_date_format)
        return start_time_str, end_time_str

    def postprocess_articles(
        self,
        candidates: list[Any],
        topic_id: str,
        topic: str,
        requested_category: str,
        mapped_requested_category: str,
        start_time: datetime,
        end_time: datetime,
        sorting: str,
        max_aggregator_results: int,
        trusted_news_providers: Optional[list[TrustedNewsProviders]] = [],
    ) -> tuple[list[RawArticle], datetime, datetime]:
        # TODO - at some point candidates can be some interface class which will have guaranteed certain fields
        aggregated_articles: list[RawArticle] = []
        min_start_time = datetime.max.replace(tzinfo=timezone.utc)
        max_end_time = datetime.min.replace(tzinfo=timezone.utc)
        if sorting == DATE_SORTING:
            raise NotImplementedError(
                f"Sorting by {sorting} is not implemented yet in post-processing."
            )
        article_idx = 0
        for article in candidates:
            if len(aggregated_articles) >= max_aggregator_results:
                break
            # NewsApiOrg doesn't provide the category as a request parameter or in the response.
            standardized_published_date = generate_standardized_published_date(
                getattr(article, self.published_date_attr_name), self.published_date_regex
            )
            standardized_published_dt = datetime.fromisoformat(standardized_published_date)
            if standardized_published_dt < start_time or standardized_published_dt > end_time:
                logger.error(
                    f"Article with url: {article.url} has published date {standardized_published_dt} which is outside the requested timeframe {start_time} - {end_time}, skipping..."
                )
                # TODO - emit metric
                continue
            if standardized_published_dt < min_start_time:
                min_start_time = standardized_published_dt
            if standardized_published_dt > max_end_time:
                max_end_time = standardized_published_dt
            article_id = self.generate_article_id(article_idx)
            logger.info(f"Generated article id {article_id} for article with url: {article.url}")
            raw_article = RawArticle(
                article_id=article_id,
                aggregator_id=self.aggregator_id,
                dt_published=standardized_published_date,
                aggregation_index=article_idx,
                topic_id=topic_id,
                topic=topic,
                requested_category=requested_category,
                title=article.title,
                url=article.url,
                author=article.author,
                article_text_snippet=article.content,
                article_data=article.json(),
                sorting=sorting,
            )
            # NOTE - this will extract article text and more data from the article url
            raw_article.process_article_data()
            if not raw_article.article_processed_data:
                logger.warning(
                    f"Article with url: {article.url} has no processed data, skipping..."
                )
                continue
            aggregated_articles.append(raw_article)
            article_idx += 1
        return aggregated_articles, min_start_time, max_end_time

    def get_candidates_for_topic(
        self,
        topic_id: str,
        topic: str,
        category: str,
        start_time: datetime,
        end_time: datetime,
        sorting: str,
        max_aggregator_results: int,
        fetched_articles_count: int,
        trusted_news_providers: Optional[list[TrustedNewsProviders]] = [],
    ) -> tuple[list[RawArticle], datetime, datetime]:
        candidates: list[news_api_org.Article] = []
        total_matches = 0
        page = self.start_page
        data_from_date, data_to_date = self._get_data_timeframe(start_time, end_time)
        aggregator_mapped_category = self.category_mapper.get_category(category)
        logger.info(
            f"Retrieving a max of {fetched_articles_count} news articles results for search term: {topic}, requested category: {category} (mapped category {aggregator_mapped_category}) and timeframe: {data_from_date} - {data_to_date}..."
        )
        # currently we use the url only to check for duplicates
        unique_articles_db: set[str] = set()
        # NOTE - we will try to fetch fetched_articles_count articles
        # we will only remove duplicate urls ("preprocessing")
        # after this is complete, we will postprocess the results which will perform filtering and validation
        # on the fetched articles and impose the max_aggregator_results
        while True:
            if len(candidates) >= fetched_articles_count:
                logger.info(
                    f"Reached fetched articles count, will process {len(candidates)} candidates..."
                )
                break
            # Set topic parameters for API request
            params = news_api_org.EverythingV2Request(  # type:ignore
                q=topic,
                from_date_iso8061=data_from_date,
                to_date_iso8061=data_to_date,
                sort_by=self.sorting_api_param,
                page=page,
            )
            # Send API request
            response = requests.get(
                self.search_url,
                headers=self.headers.dict(by_alias=True),
                params=params.dict(by_alias=True, exclude_none=True),
                timeout=5,
            )
            logger.info(f"Request sent URL: {response.request.url}...")
            if response.status_code == 200:
                news_answer_json = response.json()
                news_answer = news_api_org.EverythingV2Response.parse_obj(news_answer_json)
                if news_answer.status == news_api_org.StatusEnum.ERROR:
                    failure_message = f"Error in response from news aggregator {self.aggregator_id}: Code={news_answer.code}; Message={news_answer.message}"
                    logger.error(
                        failure_message,
                    )
                    raise Exception(failure_message)
                if not news_answer.articles:
                    logger.info("No more articles found in latest request, breaking...")
                    break
                total_matches = news_answer.total_results
                logger.info(
                    f"Retrieved {len(news_answer.articles)} articles in response for page {page}. Total matches {total_matches}..."
                )
                articles = news_answer.articles
                new_articles_count = len(articles)
                preprocessed_articles = self.preprocess_articles(articles, unique_articles_db)
                preprocessed_new_articles_count = len(preprocessed_articles)
                needed_articles_count = fetched_articles_count - len(candidates)
                if preprocessed_new_articles_count == 0:
                    logger.info(
                        f"Preprocessed articles count is 0, breaking despite needed articles count being {needed_articles_count}... (total articles retrieved in aggregation: {len(candidates)}; Page {page}; Total matches: {total_matches})"
                    )
                    break
                preprocessed_articles = preprocessed_articles[:needed_articles_count]
                candidates.extend(preprocessed_articles)
                logger.info(
                    f"Retrieved {new_articles_count} new articles of which {preprocessed_new_articles_count} are unique. Needed articles to reach max {needed_articles_count}. Total articles retrieved in aggregation: {len(candidates)}; Page {page}; Total matches: {total_matches}"
                )
                page += 1
                logger.info(
                    f"Sleeping for {REQUESTS_SLEEP_TIME_S} seconds to avoid rate limiting..."
                )
                time.sleep(REQUESTS_SLEEP_TIME_S)
            else:
                logger.error(
                    f"Error retrieving news articles: Status Codes: {response.status_code}; {response.text}",
                    exc_info=True,
                )
                raise Exception(
                    f"Error retrieving news articles: Status Codes: {response.status_code}; {response.text}"
                )
        logger.info(
            f"Finished retrieving news articles. Total candidates retrieved {len(candidates)}. Max aggregator results: {max_aggregator_results}. Fetched articles count {fetched_articles_count}. Post-processing will now occur to filter and ensure result accuracy..."
        )
        return self.postprocess_articles(
            candidates,
            topic_id,
            topic,
            category,
            aggregator_mapped_category,
            start_time,
            end_time,
            sorting,
            max_aggregator_results,
            trusted_news_providers,
        )

    def preprocess_articles(
        self, articles: list[news_api_org.Article], unique_articles_db: set[str]
    ) -> list[news_api_org.Article]:
        # TODO - these can be moved to abc when input articles is a common model
        preprocessed_articles_list = []
        for article in articles:
            # TODO - in the future we could rely on additional processing (for example from NewsPlease) to get the published date if the aggregator doesn't provide it
            if not article.published_at:
                logger.warning(
                    f"Article with url: {article.url} has no date published, skipping..."
                )
                continue
            if self.is_unique_article(article, unique_articles_db):
                preprocessed_articles_list.append(article)
        return preprocessed_articles_list

    def is_unique_article(
        self, article: news_api_org.Article, unique_articles_db: set[str]
    ) -> bool:
        # currently a unique article is defined by a unique url
        if article.url in unique_articles_db:
            logger.info(f"Article with url: {article.url} already exists, skipping...")
            return False
        unique_articles_db.add(article.url)
        return True
