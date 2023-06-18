from typing import Union

import logging
import sys
from collections.abc import Mapping
from datetime import datetime, timezone

import boto3

from news_aggregator_service.config import (
    DEFAULT_LOGGER_NAME,
    DEFAULT_NAMESPACE,
    LOCAL_TESTING,
    REGION_NAME,
)

loggers: Mapping[str, logging.Logger] = {}


def setup_logger(name: str = DEFAULT_LOGGER_NAME) -> logging.Logger:
    global loggers

    if loggers.get(name):
        return loggers[name]
    else:
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        loggers[name] = logger  # type: ignore
        return logger


def publish_metric_data(
    name: str,
    value: Union[int, float],
    dimensions: Mapping[str, str] = {},
    unit: str = "Count",
    namespace: str = DEFAULT_NAMESPACE,
) -> None:
    """
    Publishes a metric to CloudWatch
    """
    default_dimensions = {"Metric Type": "Custom"}
    metric_dimensions = {**default_dimensions, **dimensions}
    if LOCAL_TESTING:
        logger = setup_logger(__name__)
        logger.info(f"Metric: {name} - {value} - {metric_dimensions}")
        return
    cloudwatch_client = boto3.client("cloudwatch", region_name=REGION_NAME)
    try:
        cloudwatch_client.put_metric_data(
            Namespace=namespace,
            MetricData=[
                {
                    "MetricName": name,
                    "Dimensions": [
                        {"Name": key, "Value": value} for key, value in metric_dimensions.items()
                    ],
                    "Timestamp": datetime.now(timezone.utc),
                    "Value": value,
                    "Unit": unit,
                },
            ],
        )
    except Exception as e:
        raise Exception(f"Failed to publish metric data: {e}")


def publish_count_metric(
    name: str,
    value: Union[int, float] = 1,
    dimensions: Mapping[str, str] = {},
    namespace: str = DEFAULT_NAMESPACE,
) -> None:
    """
    Publishes a count metric to CloudWatch
    """
    publish_metric_data(
        name=name,
        value=value,
        dimensions={"Type": "count", **dimensions},
        unit="Count",
        namespace=namespace,
    )
