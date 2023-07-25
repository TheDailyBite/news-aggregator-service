import json
import time
from collections.abc import Mapping

import typer
from news_aggregator_data_access_layer.models.dynamodb import PreviewUsers, create_tables

DATA_DIR = "data"
PREVIEW_USERS_DATA_DIR = f"{DATA_DIR}/preview_users"
PREVIEW_USERS_DATA_FILE = f"{PREVIEW_USERS_DATA_DIR}/users.jsonl"


def initialize_preview_users() -> None:
    try:
        create_tables()
        data = load_data()
        current_users = [u for u in PreviewUsers.scan()]
        print(f"Deleting {len(current_users)} current preview users to make the process easy")
        unique_users = {item["user_id"] for item in data}
        assert len(unique_users) == len(data), "User IDs must be unique"
        for user in current_users:
            user.delete()
        time.sleep(2)
        users_created = len(data)
        for item in data:
            preview_user = PreviewUsers(
                user_id=item["user_id"],
                name=item["name"],
            )
            preview_user.save()
        print(f"Created {users_created} preview users")
    except Exception as e:
        print(f"Failed to initialize preview users with error: {e}")
        raise


def load_data() -> list[Mapping[str, str]]:
    data = []
    with open(PREVIEW_USERS_DATA_FILE) as jsonl_file:
        for line in jsonl_file:
            # Strip leading and trailing whitespace from the line
            line = line.strip()
            # Check if the line is empty or starts with a comment character
            if not line or line.startswith("//") or line.startswith("#"):
                continue
            data.append(json.loads(line))
    return data


if __name__ == "__main__":
    typer.run(initialize_preview_users)
