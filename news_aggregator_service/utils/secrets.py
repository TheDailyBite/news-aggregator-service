import boto3

from news_aggregator_service.config import REGION_NAME


def get_secret(
    secret_name: str,
    client: boto3.client = boto3.client(
        service_name="secretsmanager",
        region_name=REGION_NAME,
    ),
) -> str:
    get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    return str(get_secret_value_response["SecretString"])
