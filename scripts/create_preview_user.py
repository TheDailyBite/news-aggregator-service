import typer
from news_aggregator_data_access_layer.models.dynamodb import (
    PreviewUsers,
    create_tables,
    get_uuid4_attribute,
)


def create_preview_user(name: str) -> None:
    if not name:
        raise ValueError("name must be specified")
    create_tables()
    user_id = get_uuid4_attribute()
    print(f"Creating preview user with id {user_id} and name {name}...")
    preview_user = PreviewUsers(user_id=user_id, name=name)
    preview_user.save()


if __name__ == "__main__":
    typer.run(create_preview_user)
