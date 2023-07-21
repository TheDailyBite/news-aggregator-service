from typing import Any, Dict, List, Optional, Set, Tuple, Union

import json
import os
import time
import urllib.parse
import uuid
from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

import boto3
import requests
from news_aggregator_data_access_layer.assets.news_assets import CandidateArticles, RawArticle
from news_aggregator_data_access_layer.config import S3_ENDPOINT_URL
from news_aggregator_data_access_layer.constants import (
    NO_CATEGORY_STR,
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

from news_aggregator_service.aggregators.models import bing_news, news_api_org, the_news_api_com
from news_aggregator_service.aggregators.models.aggregations import AggregationResults
from news_aggregator_service.config import (
    BING_NEWS_API_KEY,
    BING_NEWS_API_KEY_SECRET_NAME,
    DEFAULT_MAX_BING_AGGREGATOR_RESULTS,
    NEWS_API_ORG_API_KEY,
    NEWS_API_ORG_API_KEY_SECRET_NAME,
    NEWS_LANGUAGE,
    REGION_NAME,
    REQUESTS_SLEEP_TIME_S,
    THE_NEWS_API_COM_API_KEY,
    THE_NEWS_API_COM_API_KEY_SECRET_NAME,
)
from news_aggregator_service.constants import (
    BING_CATEGORIES_MAPPER,
    BING_NEWS_PUBLISHED_DATE_REGEX,
    DATE_SORTING,
    NEWS_API_ORG_CATEGORIES_MAPPER,
    NEWS_API_ORG_PUBLISHED_DATE_REGEX,
    OLDEST_SUPPORTED_PUBLISHING_DATE,
    POPULARITY_SORTING,
    RELEVANCE_SORTING,
    SUPPORTED_SORTING,
    THE_NEWS_API_COM_CATEGORIES_MAPPER,
    THE_NEWS_API_COM_PUBLISHED_DATE_REGEX,
)
from news_aggregator_service.utils.secrets import get_secret
from news_aggregator_service.utils.telemetry import setup_logger

logger = setup_logger(__name__)


class AggregatorInterface(ABC):
    @abstractmethod
    def get_candidates_for_topic(
        self,
        topic_id: str,
        topic: str,
        start_time: datetime,
        end_time: datetime,
        sorting: str,
        max_aggregator_results: int,
        fetched_articles_count: int,
        trusted_news_providers: list[TrustedNewsProviders],
    ) -> tuple[list[RawArticle], datetime, datetime]:
        pass

    def aggregate_candidates_for_topic(
        self,
        topic_id: str,
        topic: str,
        start_time: datetime,
        end_time: datetime,
        max_aggregator_results: int,
        fetched_articles_count: int,
        trusted_news_providers: list[TrustedNewsProviders],
    ) -> tuple[AggregationResults, datetime]:
        aggregation_start_dt = datetime.now(timezone.utc)
        aggregation_start_date = dt_to_lexicographic_date_s3_prefix(aggregation_start_dt)
        if max_aggregator_results <= 0:
            raise ValueError(
                f"max_aggregator_results must be a positive integer, got: {max_aggregator_results}"
            )
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
                start_time,
                end_time,
                self.sorting,
                max_aggregator_results,
                fetched_articles_count,
                trusted_news_providers,
            )
            logger.info(
                f"Found {len(candidates_for_topic)} candidates for topic: {topic} for timeframe {start_time} - {end_time}. Start published date of aggregated articles: {start_published_dt}, End published date: {end_published_dt}"
            )
            aggregation_result = AggregationResults(
                articles_aggregated_count=len(candidates_for_topic),
                topic=topic,
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
                f"Error while aggregating news with aggregator {self.aggregator_id} for topic: {topic} and timeframe {start_time} - {end_time}: {e}",
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
        start_time: datetime,
        end_time: datetime,
        sorting: str,
        max_aggregator_results: int,
        trusted_news_providers: list[TrustedNewsProviders],
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
            DATE_SORTING: bing_news.SortByEnum.PUBLISHED_AT,
        }
        self.sorting_api_param = self.sorting_mapping[self._sorting]
        self._historical_articles_days_ago_start: timedelta = max(
            timedelta(days=-1),
            OLDEST_SUPPORTED_PUBLISHING_DATE
            - datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0),
        )
        logger.info(
            f"Historical articles days ago start: {self._historical_articles_days_ago_start} supported for aggregator {self._aggregator_id}"
        )

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
        start_time: datetime,
        end_time: datetime,
        sorting: str,
        max_aggregator_results: int,
        trusted_news_providers: list[TrustedNewsProviders],
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
                category=self.category_mapper.get_category(article.category),
                title=article.name,
                url=article.url,
                article_text_description=article.description,
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
        start_time: datetime,
        end_time: datetime,
        sorting: str,
        max_aggregator_results: int,
        fetched_articles_count: int,
        trusted_news_providers: list[TrustedNewsProviders],
    ) -> tuple[list[RawArticle], datetime, datetime]:
        candidates: list[bing_news.NewsArticle] = []
        offset = 0
        total_estimated_matches = 0
        page = self.start_page
        data_timeframe = self._get_data_timeframe(start_time, end_time)
        topic = urllib.parse.quote_plus(topic)
        logger.info(
            f"Retrieving a max of {fetched_articles_count} news articles results for url encoded search term: {topic}) and timeframe: {data_timeframe}..."
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
        self.search_in = news_api_org.SearchInEnum.TITLE_DESCRIPTION.value
        self._sorting = POPULARITY_SORTING
        assert self._sorting in SUPPORTED_SORTING
        self.sorting_mapping = {
            RELEVANCE_SORTING: news_api_org.SortByEnum.RELEVANCE,
            POPULARITY_SORTING: news_api_org.SortByEnum.POPULARITY,
            DATE_SORTING: news_api_org.SortByEnum.PUBLISHED_AT,
        }
        self.sorting_api_param = self.sorting_mapping[self._sorting]
        # newsapi.org doesn't explicitly state a maximum. We will set an arbitrary value and see if someday it fails
        self.max_include_domain_filter_count = 500
        # TODO - this should change after upgrading to premium subscription
        # TODO - instead of -30 it can probably be set to the oldest supported publishing date by the aggregator
        self._historical_articles_days_ago_start: timedelta = max(
            timedelta(days=-30),
            OLDEST_SUPPORTED_PUBLISHING_DATE
            - datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0),
        )
        logger.info(
            f"Historical articles days ago start: {self._historical_articles_days_ago_start} for aggregator {self._aggregator_id}"
        )

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
        start_time: datetime,
        end_time: datetime,
        sorting: str,
        max_aggregator_results: int,
        trusted_news_providers: list[TrustedNewsProviders],
    ) -> tuple[list[RawArticle], datetime, datetime]:
        # TODO - at some point candidates can be some interface class which will have guaranteed certain fields
        aggregated_articles: list[RawArticle] = []
        min_start_time = datetime.max.replace(tzinfo=timezone.utc)
        max_end_time = datetime.min.replace(tzinfo=timezone.utc)
        if sorting == DATE_SORTING:
            raise NotImplementedError(
                f"Sorting by {sorting} is not implemented yet in post-processing."
            )
        include_domains = [tnp.provider_domain for tnp in trusted_news_providers]
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
                title=article.title,
                url=article.url,
                author=article.author,
                article_text_snippet=article.content,
                article_text_description=article.description,
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
            if not raw_article.get_article_text_description():
                logger.warning(f"Article with url: {article.url} has no description, skipping...")
                continue
            if not raw_article.provider_domain in include_domains:
                logger.warning(
                    f"Article with url: {raw_article.url} has provider domain {raw_article.provider_domain} which is not in the list of trusted news providers. This should not have reached postprocessing. skipping..."
                )
                # TODO - emit metric
                continue
            aggregated_articles.append(raw_article)
            article_idx += 1
        return aggregated_articles, min_start_time, max_end_time

    def get_candidates_for_topic(
        self,
        topic_id: str,
        topic: str,
        start_time: datetime,
        end_time: datetime,
        sorting: str,
        max_aggregator_results: int,
        fetched_articles_count: int,
        trusted_news_providers: list[TrustedNewsProviders],
    ) -> tuple[list[RawArticle], datetime, datetime]:
        candidates: list[news_api_org.Article] = []
        total_matches = 0
        page = self.start_page
        data_from_date, data_to_date = self._get_data_timeframe(start_time, end_time)
        topic = urllib.parse.quote_plus(topic)
        if len(trusted_news_providers) > self.max_include_domain_filter_count:
            raise ValueError(
                f"Cannot include more than {self.max_include_domain_filter_count} domains in the include_domains filter for aggregator {self.aggregator_id}. Requested include domains count {len(trusted_news_providers)}"
            )
        include_domains = ",".join(
            [provider.provider_domain for provider in trusted_news_providers]
        )
        logger.info(f"Include domains for aggregator {self.aggregator_id}: {include_domains}")
        logger.info(
            f"Retrieving a max of {fetched_articles_count} news articles results for search term: {topic}) and timeframe: {data_from_date} - {data_to_date}..."
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
                domains=include_domains,
                search_in=self.search_in,
                language=NEWS_LANGUAGE,
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


class TheNewsApiComAggregator(AggregatorInterface):
    def __init__(self):
        self._aggregator_id = NewsAggregatorsEnum.THE_NEWS_API_COM.value
        self.base_url = "https://api.thenewsapi.com"
        self.search_url = f"{self.base_url}/v1/news/all"
        self.api_key = self.get_api_key(
            THE_NEWS_API_COM_API_KEY, THE_NEWS_API_COM_API_KEY_SECRET_NAME
        )
        self._category_mapper = AggregatorCategoryMapper(THE_NEWS_API_COM_CATEGORIES_MAPPER)
        self.headers = dict()
        # this comes from the documentation and is based on pricing plan
        self.max_articles_per_request = 100
        self.published_date_regex = THE_NEWS_API_COM_PUBLISHED_DATE_REGEX
        self.published_date_attr_name = "published_at"
        self.request_date_format = "%Y-%m-%dT%H:%M:%S"
        self.start_page = 1
        self._sorting = RELEVANCE_SORTING
        self.search_in = the_news_api_com.SearchInEnum.TITLE_DESCRIPTION.value
        assert self._sorting in SUPPORTED_SORTING
        self.sorting_mapping = {
            RELEVANCE_SORTING: the_news_api_com.SortByEnum.RELEVANCE,
            DATE_SORTING: the_news_api_com.SortByEnum.PUBLISHED_AT,
        }
        self.sorting_api_param = self.sorting_mapping[self._sorting]
        # thenewsapi.com doesn't explicitly state a maximum. I thought I read somewhere that it is 50 but I can't find it now
        # I'll set it to 50 for now and then can verify that it can be increased if we do add sources
        self.max_include_domain_filter_count = 50
        # TODO - this should change after upgrading to premium subscription
        # TODO - instead of -30 it can probably be set to the oldest supported publishing date by the aggregator
        self._historical_articles_days_ago_start: timedelta = max(
            timedelta(days=-30),
            OLDEST_SUPPORTED_PUBLISHING_DATE
            - datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0),
        )
        logger.info(
            f"Historical articles days ago start: {self._historical_articles_days_ago_start} for aggregator {self._aggregator_id}"
        )

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
        start_time: datetime,
        end_time: datetime,
        sorting: str,
        max_aggregator_results: int,
        trusted_news_providers: list[TrustedNewsProviders],
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
        include_domains = [tnp.provider_domain for tnp in trusted_news_providers]
        for article in candidates:
            if len(aggregated_articles) >= max_aggregator_results:
                break
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
                category=",".join(
                    [self.category_mapper.get_category(c) for c in article.categories]
                ),
                title=article.title,
                url=article.url,
                article_text_snippet=article.snippet,
                article_text_description=article.description,
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
            if not raw_article.get_article_text_description():
                logger.warning(f"Article with url: {article.url} has no description, skipping...")
                continue
            if not raw_article.provider_domain in include_domains:
                logger.warning(
                    f"Article with url: {raw_article.url} has provider domain {raw_article.provider_domain} which is not in the list of trusted news providers. This should not have reached postprocessing. skipping..."
                )
                # TODO - emit metric
                continue
            aggregated_articles.append(raw_article)
            article_idx += 1
        return aggregated_articles, min_start_time, max_end_time

    def get_candidates_for_topic(
        self,
        topic_id: str,
        topic: str,
        start_time: datetime,
        end_time: datetime,
        sorting: str,
        max_aggregator_results: int,
        fetched_articles_count: int,
        trusted_news_providers: list[TrustedNewsProviders],
    ) -> tuple[list[RawArticle], datetime, datetime]:
        candidates: list[the_news_api_com.Article] = []
        total_matches = 0
        page = self.start_page
        data_from_date, data_to_date = self._get_data_timeframe(start_time, end_time)
        topic = urllib.parse.quote_plus(topic)
        if len(trusted_news_providers) > self.max_include_domain_filter_count:
            raise ValueError(
                f"Cannot include more than {self.max_include_domain_filter_count} domains in the include_domains filter for aggregator {self.aggregator_id}. Requested include domains count {len(trusted_news_providers)}"
            )
        include_domains = ",".join(
            [provider.provider_domain for provider in trusted_news_providers]
        )
        logger.info(f"Include domains for aggregator {self.aggregator_id}: {include_domains}")
        logger.info(
            f"Retrieving a max of {fetched_articles_count} news articles results for search term: {topic}) and timeframe: {data_from_date} - {data_to_date}..."
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
            params = the_news_api_com.AllNewsRequest(  # type:ignore
                api_token=self.api_key,
                search=topic,
                search_fields=self.search_in,
                domains=include_domains,
                published_after=data_from_date,
                published_before=data_to_date,
                sort=self.sorting_api_param,
                page=page,
                language=NEWS_LANGUAGE,
            )
            # Send API request
            response = requests.get(
                self.search_url,
                headers=self.headers,
                params=params.dict(by_alias=False, exclude_none=True),
                timeout=5,
            )
            logger.info(f"Request sent URL: {response.request.url}...")
            if response.status_code == 200:
                news_answer_json = response.json()
                news_answer = the_news_api_com.AllNewsResponse.parse_obj(news_answer_json)

                if not news_answer.data:
                    logger.info("No more articles found in latest request, breaking...")
                    break
                total_matches = news_answer.meta.found
                logger.info(
                    f"Retrieved {len(news_answer.data)} articles in response for page {page}. Total matches {total_matches}..."
                )
                articles = news_answer.data
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
                # TODO - could parse ErrorResponse here
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
            start_time,
            end_time,
            sorting,
            max_aggregator_results,
            trusted_news_providers,
        )

    def preprocess_articles(
        self, articles: list[the_news_api_com.Article], unique_articles_db: set[str]
    ) -> list[the_news_api_com.Article]:
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
        self, article: the_news_api_com.Article, unique_articles_db: set[str]
    ) -> bool:
        # currently a unique article is defined by a unique url
        if article.url in unique_articles_db:
            logger.info(f"Article with url: {article.url} already exists, skipping...")
            return False
        unique_articles_db.add(article.url)
        return True
