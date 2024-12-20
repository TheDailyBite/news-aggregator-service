import typer
from news_aggregator_data_access_layer.constants import NewsAggregatorsEnum
from news_aggregator_data_access_layer.models.dynamodb import NewsAggregators, create_tables


def initialize_news_aggregators(news_aggs: list[str]) -> None:
    try:
        create_tables()
        print(f"News aggregators specified: {news_aggs}. Will convert to corresponding enum value.")
        news_aggs_enums: list[NewsAggregatorsEnum] = [
            NewsAggregatorsEnum.get_member_by_value(news_agg_str) for news_agg_str in news_aggs
        ]
        for news_agg in news_aggs_enums:
            print(f"Creating news aggregator id {news_agg.value}")
            news_aggregator = NewsAggregators(
                aggregator_id=news_agg,
                is_active=True,
            )
            news_aggregator.save()
    except Exception as e:
        print(
            f"Failed to create news aggregators {', '.join([news_agg for news_agg in news_aggs])} with error: {e}"
        )
        raise


if __name__ == "__main__":
    typer.run(initialize_news_aggregators)
