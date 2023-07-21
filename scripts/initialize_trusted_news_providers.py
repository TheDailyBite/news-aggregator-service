import json
from collections.abc import Mapping

import typer
from botocore.client import ClientError
from news_aggregator_data_access_layer.models.dynamodb import TrustedNewsProviders, create_tables
from pynamodb.exceptions import PutError

DATA_DIR = "data"
TRUSTED_NEWS_PROVIDERS_DATA_DIR = f"{DATA_DIR}/trusted_news_providers"


def initialize_trusted_news_providers(language: str) -> None:
    try:
        create_tables()
        if len(language) != 2:
            raise ValueError(f"Language must be 2 characters. Got {language}")
        print(f"Creating trusted news providers for language: {language}")
        data = load_data(language)
        current_tnps = TrustedNewsProviders.query(language)
        current_active_trusted_news_providers = []
        current_inactive_trusted_news_providers = []
        for tnp in current_tnps:
            if tnp.is_active:
                current_active_trusted_news_providers.append(tnp.provider_domain)
            else:
                current_inactive_trusted_news_providers.append(tnp.provider_domain)
        new_trusted_news_providers = 0
        reactivated_trusted_news_providers = 0
        existing_active_trusted_news_provider = 0
        trusted_news_providers_to_deactivate = 0
        # will hold every active domain at the end of this loop
        updated_active_trusted_news_providers = []
        for provider in data:
            updated_active_trusted_news_providers.append(provider["domain"])
            # If the provider already exists and is active, skip
            if provider["domain"] in current_active_trusted_news_providers:
                print(
                    f"Trusted news provider with name: {provider['provider_name']} and domain: {provider['domain']} already exists. Skipping"
                )
                existing_active_trusted_news_provider += 0
                continue
            # If the provider already exists and is inactive, set to Active
            if provider["domain"] in current_inactive_trusted_news_providers:
                print(
                    f"Trusted news provider with name: {provider['provider_name']} and domain: {provider['domain']} already exists but is inactive. Reactivating."
                )
                trusted_news_provider = TrustedNewsProviders(language, provider["domain"])
                trusted_news_provider.update(
                    actions=[
                        TrustedNewsProviders.is_active.set(True),
                    ]
                )
                reactivated_trusted_news_providers += 1
                continue
            # if the provider doesn't exist yet, create it
            print(
                f"Creating a new trusted news provider with name: {provider['provider_name']} and domain: {provider['domain']}"
            )
            trusted_news_provider = TrustedNewsProviders(
                language=language.lower(),
                provider_domain=provider["domain"],
                provider_name=provider["provider_name"],
                country=provider["country"],
                is_active=True,
            )
            trusted_news_provider.save(
                condition=TrustedNewsProviders.language.does_not_exist()
                & TrustedNewsProviders.provider_domain.does_not_exist()
            )
            new_trusted_news_providers += 1
        # Deactivate any trusted news providers that are no longer in the data file
        provider_to_deactivate = set(current_active_trusted_news_providers) - set(
            updated_active_trusted_news_providers
        )
        if len(provider_to_deactivate) == 0:
            print("No trusted news providers to deactivate.")
        for provider in provider_to_deactivate:
            print(f"Deactivating trusted news provider with domain: {provider}")
            trusted_news_provider = TrustedNewsProviders(language, provider)
            trusted_news_provider.update(
                actions=[
                    TrustedNewsProviders.is_active.set(False),
                ]
            )
            trusted_news_providers_to_deactivate += 1
        print(
            f"New trusted news providers: {new_trusted_news_providers}; Reactivated trusted news providers: {reactivated_trusted_news_providers}; Existing active trusted news providers: {existing_active_trusted_news_provider}; Trusted news providers to deactivate: {trusted_news_providers_to_deactivate}"
        )
    except Exception as e:
        print(f"Failed to Trusted news provider for language {language} with error: {e}")
        raise


def load_data(language: str) -> list[Mapping[str, str]]:
    language_trusted_news_providers_jsonl_file = (
        f"{TRUSTED_NEWS_PROVIDERS_DATA_DIR}/{language}.jsonl"
    )
    data = []
    with open(language_trusted_news_providers_jsonl_file) as jsonl_file:
        for line in jsonl_file:
            # Strip leading and trailing whitespace from the line
            line = line.strip()
            # Check if the line is empty or starts with a comment character
            if not line or line.startswith("//") or line.startswith("#"):
                continue
            data.append(json.loads(line))
    return data


if __name__ == "__main__":
    typer.run(initialize_trusted_news_providers)
