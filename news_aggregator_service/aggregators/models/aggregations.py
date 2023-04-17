from typing import Optional

from pydantic import BaseModel


class AggregationResults(BaseModel):
    articles_aggregated_count: int
    category: str
    query: str
    freshness: str
    store_prefix: Optional[str]
    sorting: str

    class Config:
        allow_population_by_field_name = True
