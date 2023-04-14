class AggregationResults:
    def __init__(
        self,
        articles_aggregated_count: int,
        category: str,
        query: str,
        freshness: str,
        sorting: str,
        prefix: str,
    ):
        self.articles_aggregated_count = articles_aggregated_count
        self.category = category
        self.query = query
        self.freshness = freshness
        self.store_prefix = prefix
        self.sorting = sorting
