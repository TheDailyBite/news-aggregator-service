from typing import Optional

from pydantic import BaseModel


class AggregationResults(BaseModel):
    articles_aggregated_count: int
    topic: str
    requested_category: str
    data_start_time: str
    data_end_time: str
    # comma separated list of paths to the aggregated articles
    store_paths: Optional[str] = ""
    sorting: str

    class Config:
        allow_population_by_field_name = True
