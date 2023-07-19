# news-aggregator-service

<div align="center">

[![Build status](https://github.com/TheDailyBite/news-aggregator-service/workflows/build/badge.svg?branch=main&event=push)](https://github.com/TheDailyBite/news-aggregator-service/actions?query=workflow%3Abuild)
[![Python Version](https://img.shields.io/pypi/pyversions/news-aggregator-service.svg)](https://pypi.org/project/news-aggregator-service/)
[![Dependencies Status](https://img.shields.io/badge/dependencies-up%20to%20date-brightgreen.svg)](https://github.com/TheDailyBite/news-aggregator-service/pulls?utf8=%E2%9C%93&q=is%3Apr%20author%3Aapp%2Fdependabot)

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Security: bandit](https://img.shields.io/badge/security-bandit-green.svg)](https://github.com/PyCQA/bandit)
[![Pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/TheDailyBite/news-aggregator-service/blob/main/.pre-commit-config.yaml)
[![Semantic Versions](https://img.shields.io/badge/%20%20%F0%9F%93%A6%F0%9F%9A%80-semantic--versions-e10079.svg)](https://github.com/TheDailyBite/news-aggregator-service/releases)
[![License](https://img.shields.io/github/license/TheDailyBite/news-aggregator-service)](https://github.com/TheDailyBite/news-aggregator-service/blob/main/LICENSE)
![Coverage Report](assets/images/coverage.svg)

A cool news aggregator service.

</div>

## Very first steps

### Initialize your code

1. Initialize `git` inside your repo:

```bash
cd news-aggregator-service && git init
```

2. If you don't have `Poetry` installed run:

```bash
make poetry-download
```

3. Initialize poetry and install `pre-commit` hooks:

```bash
make install
make pre-commit-install
```

4. Run the codestyle:

```bash
make codestyle
```

5. Upload initial code to GitHub:

```bash
git add .
git commit -m ":tada: Initial commit"
git branch -M main
git remote add origin https://github.com/TheDailyBite/news-aggregator-service.git
git push -u origin main
```

#### Running /scripts
- Note that you must have the `news_aggregator_service` installed (via `make install`) and then run `poetry shell`.
- This will ensure you have access to all the packages needed to run the scripts.

### Initialize system  in new environment
1. See [Running /scripts](running-/scripts). Navigate to the scripts folder: `cd scripts`
2. Make sure to have credentials available for AWS exported as environment variables. Short-term creds can be retrieved from AWS SSO.
3. `python initialize_news_aggregators.py`. Make sure to only include the desired news aggregators.
4. `python create_news_topic.py` with all the news topics you wish to create. This will request a few parameters.

### Sourced Article Review
1. See [Running /scripts](running-/scripts). Navigate to the scripts folder: `cd scripts`
2. Make sure to have credentials available for AWS exported as environment variables. Short-term creds can be retrieved from AWS SSO.
3. Run `python review_pending_articles.py`
4. The CLI should guide you through the process of reviewing articles. Be careful! You can't undo your actions.


### Fresh Start News Topic Publishing
This assume the news topic does not exist. This is a completely new news topic you wish to introduce to the system.
If you simply want to re-source an existing news topic, see the section below.
1. [Create a News Topic](#create-a-news-topic)
2. We need to force news aggregation to occur from the past until today. Triggering aggregation scheduler will trigger aggregation scheduling to happen from the oldest supported day until today. This can be done from the AWS console for the lambda as this is time triggered (sending any test event).
3. After each aggregation is actually processed, sourcing scheduling can be triggered. This can be done from the AWS console for the lambda as this is time triggered (sending any test event). This will source all the articles that were aggregated.
4. [Sourced Article Review](#sourced-article-review)

### Re-source News Topic Publishing
This assume the news topic already exists. This is a news topic you wish to re-source, that is re-publish all the articles that were previously sourced for the news topic. This is more complicated and you need to be careful.
1. We need to set `last_publishing_date`, `bing_aggregation_last_end_time`, and `news_api_org_aggregation_last_end_time` (NOTE - add more if more aggregators are introduced) to `None`. This can be done by running the script (`/scripts`) TODO
2. For the given news topic, we'd need to delete all the articles that were previously sourced. This can be done by running the script (`/scripts`) TODO. TODO maybe also delete PublishedArticles?

### Initialize a News Aggregator
1. Navigate to the scripts folder: `cd scripts`
2. Make sure to have credentials available for AWS exported as environment variables. Short-term creds can be retrieved from AWS SSO.
3. Run `python create_news_topic.py` with the appropriate arguments. You can run `python initialize_news_aggregators.py --help` to see the arguments. (example: `python initialize_news_aggregators.py "newsapi.org" "bingnews"`)
4. The CLI should guide you through the process of initializing a news aggregator.

### Create a News Topic
1. Navigate to the scripts folder: `cd scripts`
2. Make sure to have credentials available for AWS exported as environment variables. Short-term creds can be retrieved from AWS SSO.
3. Run `python create_news_topic.py` with the appropriate arguments. You can run `python create_news_topic.py --help` to see the arguments. (example: `python create_news_topic.py --daily-publishing-limit 10 "Generative AI" 25`)
4. The CLI should guide you through the process of creating a news topic.

### Local Testing
The entirety of the aggregation service can be tested local by using the docker-compose file found in the `docker/` sub-directory.

Requirements:
1. Docker Engine needs to be installed. This now typically include docker compose as well.
2. Create a file called `secret-envs.env` within the `docker/` sub-directory. This needs to include all the required environment variables that are secret. This file is included in the `.gitignore` so it will not be pushed to git. For example this may include an api key that is used by the service `BING_NEWS_API_KEY="some_bing_news_api_key"`

Running Service locally:
1. Once the requirements are completed, navigate to the `docker/` sub-directory. From here run `docker compose up` to spin up the containers.
2. You can open the s3 local ui by visiting `localhost:9001` (this requires you to login; you can find the credentials in the `docker-compose.yml` file but they are probably `accesskey` and `secretkey`) and the dynamodb ui at `localhost:8001`.
3. If it is the first time runnign the s3 local ui or you cleared the data, you'll need to create the required s3 buckets. Do so in the UI. The buckets are currently: `news-aggregator-candidate-articles-dev` and `news-aggregator-sourced-articles-dev` (there may be more since I may forget to update this README from time to time).
4. Start a bash session in the `news_aggregator_service` container by executing `docker exec -it <container_id_of_container> bash`. To get the container id you simply can run `docker container ls`.
5. Once in the container start `python`. Then run `exec(open("app.py").read())`. 
6. Create news aggregators and a news topic by running the following:
```python
create_news_aggregators()
topic="Generative AI"
max_aggregator_results=25
event = {
    "topic": topic,
    "max_aggregator_results": max_aggregator_results,
}
response = create_news_topic(event, None)
topic_id = response["body"]["topic_id"]
print(f"Topic ID: {topic_id}")
```
7. Once you have the news topic you wish to aggregate, you can run `aggregate_news_topic(event, None)`. This will aggregate the news for the supplied news topic (by `topic_id`) and timeframe specified (feel free to adjust these values)
```python
data_start = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
data_end = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
event = {
  "Records": [
    {
      "body": {
        "topic_id": topic_id,
        "aggregator_id": NewsAggregatorsEnum.THE_NEWS_API_COM.value, # NewsAggregatorsEnum.NEWS_API_ORG.value
        "aggregation_data_start_dt": data_start,
        "aggregation_data_end_dt": data_end,
      }
    }
  ]
}
aggregate_news_topic(json.dumps(event), None)
```
8. See in the s3 local ui that the news has been aggregated and stored in the `news-aggregator-candidate-articles-dev` bucket. The aggregation run will show all prefixes where data was stored in s3 in the `aggregated_articles_ref` attribute.
- NOTE - the s3 local ui uses a volume to persist the data. If you wish to clear the data, simply delete the `docker/s3-data` directory and restart the containers.
9. Sourcing Articles for a given topic/date
```python
topics_to_source = [
  ("e0b14571-ae03-4deb-8c51-ac559e253811", [datetime(2023, 7, 1, tzinfo=timezone.utc), datetime(2023, 7, 2, tzinfo=timezone.utc)]),
  ("39548f61-c0f0-4f71-8488-d35eaca4fe2f", [datetime(2023, 7, 10, tzinfo=timezone.utc), datetime(2023, 7, 11, tzinfo=timezone.utc), datetime(2023, 7, 12, tzinfo=timezone.utc)]),  
]
for topic_id, dates in topics_to_source:
  for date in dates:
    event = {
      "Records": [
        {
          "body": {
            "topic_id": topic_id,
            "sourcing_date": date.isoformat(),
            "daily_sourcing_frequency": "1"
          }
        }
      ]
    }
    response = source_news_topic(json.dumps(event), None)


topics_to_source = [
  ("df55f9a9-7cfa-46ca-88d1-a367d565f1b1", [datetime(2023, 7, 15, tzinfo=timezone.utc), datetime(2023, 7, 16, tzinfo=timezone.utc), datetime(2023, 7, 17, tzinfo=timezone.utc)]),  
]
for topic_id, dates in topics_to_source:
  for date in dates:
    event = {
      "Records": [
        {
          "body": {
            "topic_id": topic_id,
            "sourcing_date": date.isoformat(),
            "daily_sourcing_frequency": "1"
          }
        }
      ]
    }
    response = source_news_topic(json.dumps(event), None)    
```
10. See in the s3 local ui that the news has been aggregated and stored in the `news-aggregator-sourced-articles-dev` bucket for the specified topic_id and publishing_date. See also in dynamodb in the `sourced-articles-dev` table.
- NOTE - the s3 local ui uses a volume to persist the data. If you wish to clear the data, simply delete the `docker/s3-data` directory and restart the containers.


Testing an aggregator locally:
1. Start a bash session in the `news_aggregator_service` container by executing `docker exec -it <container_id_of_container> bash`. To get the container id you simply can run `docker container ls`.
2. Make sure the `API KEY` for the aggregator is set appropriately. For example for the bing aggregator make sure the `BING_NEWS_API_KEY` env var is set.
3. Once in the container start `python`. Set the api key environment variable by doing:
```python
import os
os.environ["BING_NEWS_API_KEY"] = "<value>"
```
Then run the following to test getting articles for a topic:
```python
# bing
from datetime import datetime, timedelta, timezone
from news_aggregator_service.aggregators.news_aggregators import BingAggregator
from news_aggregator_service.constants import (
    DATE_SORTING,
    POPULARITY_SORTING,
    RELEVANCE_SORTING,
)
bing = BingAggregator()
topic_id = "9910f34e-c25e-4667-8471-296f7bc60f62"
topic = "Generative AI"
end_time = datetime.now(timezone.utc)
start_time = end_time - timedelta(days=1)
sorting = RELEVANCE_SORTING
max_aggregator_results = 20
fetched_articles_count = 100
trusted_news_providers = []
aggregated_articles, pub_start_time, pub_end_time = bing.get_candidates_for_topic(topic_id, topic, start_time, end_time, sorting, max_aggregator_results, fetched_articles_count, trusted_news_providers)
# news api org
from datetime import datetime, timedelta, timezone
from news_aggregator_service.aggregators.news_aggregators import NewsApiOrgAggregator
from news_aggregator_service.constants import (
    DATE_SORTING,
    POPULARITY_SORTING,
    RELEVANCE_SORTING,
)
newsapiorg = NewsApiOrgAggregator()
topic_id = "9910f34e-c25e-4667-8471-296f7bc60f62"
topic = "Generative AI"
end_time = datetime.now(timezone.utc) - timedelta(days=2)
start_time = end_time - timedelta(days=1)
sorting = RELEVANCE_SORTING
max_aggregator_results = 20
fetched_articles_count = 100
trusted_news_providers = []
aggregated_articles, pub_start_time, pub_end_time = newsapiorg.get_candidates_for_topic(topic_id, topic, start_time, end_time, sorting, max_aggregator_results, fetched_articles_count, trusted_news_providers)
```

### Set up bots

- Set up [Dependabot](https://docs.github.com/en/github/administering-a-repository/enabling-and-disabling-version-updates#enabling-github-dependabot-version-updates) to ensure you have the latest dependencies.
- Set up [Stale bot](https://github.com/apps/stale) for automatic issue closing.

### Poetry

Want to know more about Poetry? Check [its documentation](https://python-poetry.org/docs/).

<details>
<summary>Details about Poetry</summary>
<p>

Poetry's [commands](https://python-poetry.org/docs/cli/#commands) are very intuitive and easy to learn, like:

- `poetry add numpy@latest`
- `poetry run pytest`
- `poetry publish --build`

etc
</p>
</details>

### Building and releasing your package

Building a new version of the application contains steps:

- Bump the version of your package `poetry version <version>`. You can pass the new version explicitly, or a rule such as `major`, `minor`, or `patch`. For more details, refer to the [Semantic Versions](https://semver.org/) standard.
- Make a commit to `GitHub`.
- Create a `GitHub release`.
- And... publish 🙂 `poetry publish --build`

## 🎯 What's next

Well, that's up to you 💪🏻. I can only recommend the packages and articles that helped me.

- [`Typer`](https://github.com/tiangolo/typer) is great for creating CLI applications.
- [`Rich`](https://github.com/willmcgugan/rich) makes it easy to add beautiful formatting in the terminal.
- [`Pydantic`](https://github.com/samuelcolvin/pydantic/) – data validation and settings management using Python type hinting.
- [`Loguru`](https://github.com/Delgan/loguru) makes logging (stupidly) simple.
- [`tqdm`](https://github.com/tqdm/tqdm) – fast, extensible progress bar for Python and CLI.
- [`IceCream`](https://github.com/gruns/icecream) is a little library for sweet and creamy debugging.
- [`orjson`](https://github.com/ijl/orjson) – ultra fast JSON parsing library.
- [`Returns`](https://github.com/dry-python/returns) makes you function's output meaningful, typed, and safe!
- [`Hydra`](https://github.com/facebookresearch/hydra) is a framework for elegantly configuring complex applications.
- [`FastAPI`](https://github.com/tiangolo/fastapi) is a type-driven asynchronous web framework.

Articles:

- [Open Source Guides](https://opensource.guide/).
- [A handy guide to financial support for open source](https://github.com/nayafia/lemonade-stand)
- [GitHub Actions Documentation](https://help.github.com/en/actions).
- Maybe you would like to add [gitmoji](https://gitmoji.carloscuesta.me/) to commit names. This is really funny. 😄

## 🚀 Features

### Development features

- Supports for `Python 3.8` and higher.
- [`Poetry`](https://python-poetry.org/) as the dependencies manager. See configuration in [`pyproject.toml`](https://github.com/TheDailyBite/news-aggregator-service/blob/main/pyproject.toml) and [`setup.cfg`](https://github.com/TheDailyBite/news-aggregator-service/blob/main/setup.cfg).
- Automatic codestyle with [`black`](https://github.com/psf/black), [`isort`](https://github.com/timothycrosley/isort) and [`pyupgrade`](https://github.com/asottile/pyupgrade).
- Ready-to-use [`pre-commit`](https://pre-commit.com/) hooks with code-formatting.
- Type checks with [`mypy`](https://mypy.readthedocs.io); docstring checks with [`darglint`](https://github.com/terrencepreilly/darglint); security checks with [`safety`](https://github.com/pyupio/safety) and [`bandit`](https://github.com/PyCQA/bandit)
- Testing with [`pytest`](https://docs.pytest.org/en/latest/).
- Ready-to-use [`.editorconfig`](https://github.com/TheDailyBite/news-aggregator-service/blob/main/.editorconfig), [`.dockerignore`](https://github.com/TheDailyBite/news-aggregator-service/blob/main/.dockerignore), and [`.gitignore`](https://github.com/TheDailyBite/news-aggregator-service/blob/main/.gitignore). You don't have to worry about those things.

### Deployment features

- `GitHub` integration: issue and pr templates.
- `Github Actions` with predefined [build workflow](https://github.com/TheDailyBite/news-aggregator-service/blob/main/.github/workflows/build.yml) as the default CI/CD.
- Everything is already set up for security checks, codestyle checks, code formatting, testing, linting, docker builds, etc with [`Makefile`](https://github.com/TheDailyBite/news-aggregator-service/blob/main/Makefile#L89). More details in [makefile-usage](#makefile-usage).
- [Dockerfile](https://github.com/TheDailyBite/news-aggregator-service/blob/main/docker/Dockerfile) for your package.
- Always up-to-date dependencies with [`@dependabot`](https://dependabot.com/). You will only [enable it](https://docs.github.com/en/github/administering-a-repository/enabling-and-disabling-version-updates#enabling-github-dependabot-version-updates).
- Automatic drafts of new releases with [`Release Drafter`](https://github.com/marketplace/actions/release-drafter). You may see the list of labels in [`release-drafter.yml`](https://github.com/TheDailyBite/news-aggregator-service/blob/main/.github/release-drafter.yml). Works perfectly with [Semantic Versions](https://semver.org/) specification.

### Open source community features

- Ready-to-use [Pull Requests templates](https://github.com/TheDailyBite/news-aggregator-service/blob/main/.github/PULL_REQUEST_TEMPLATE.md) and several [Issue templates](https://github.com/TheDailyBite/news-aggregator-service/tree/main/.github/ISSUE_TEMPLATE).
- Files such as: `LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and `SECURITY.md` are generated automatically.
- [`Stale bot`](https://github.com/apps/stale) that closes abandoned issues after a period of inactivity. (You will only [need to setup free plan](https://github.com/marketplace/stale)). Configuration is [here](https://github.com/TheDailyBite/news-aggregator-service/blob/main/.github/.stale.yml).
- [Semantic Versions](https://semver.org/) specification with [`Release Drafter`](https://github.com/marketplace/actions/release-drafter).

## Installation

```bash
pip install -U news-aggregator-service
```

or install with `Poetry`

```bash
poetry add news-aggregator-service
```



### Makefile usage

[`Makefile`](https://github.com/TheDailyBite/news-aggregator-service/blob/main/Makefile) contains a lot of functions for faster development.

<details>
<summary>1. Download and remove Poetry</summary>
<p>

To download and install Poetry run:

```bash
make poetry-download
```

To uninstall

```bash
make poetry-remove
```

</p>
</details>

<details>
<summary>2. Install all dependencies and pre-commit hooks</summary>
<p>

Install requirements:

```bash
make install
```

Pre-commit hooks coulb be installed after `git init` via

```bash
make pre-commit-install
```

</p>
</details>

<details>
<summary>3. Codestyle</summary>
<p>

Automatic formatting uses `pyupgrade`, `isort` and `black`.

```bash
make codestyle

# or use synonym
make formatting
```

Codestyle checks only, without rewriting files:

```bash
make check-codestyle
```

> Note: `check-codestyle` uses `isort`, `black` and `darglint` library

Update all dev libraries to the latest version using one comand

```bash
make update-dev-deps
```

<details>
<summary>4. Code security</summary>
<p>

```bash
make check-safety
```

This command launches `Poetry` integrity checks as well as identifies security issues with `Safety` and `Bandit`.

```bash
make check-safety
```

</p>
</details>

</p>
</details>

<details>
<summary>5. Type checks</summary>
<p>

Run `mypy` static type checker

```bash
make mypy
```

</p>
</details>

<details>
<summary>6. Tests with coverage badges</summary>
<p>

Run `pytest`

```bash
make test
```

</p>
</details>

<details>
<summary>7. All linters</summary>
<p>

Of course there is a command to ~~rule~~ run all linters in one:

```bash
make lint
```

the same as:

```bash
make test && make check-codestyle && make mypy && make check-safety
```

</p>
</details>

<details>
<summary>8. Docker</summary>
<p>

```bash
make docker-build
```

which is equivalent to:

```bash
make docker-build VERSION=latest
```

Remove docker image with

```bash
make docker-remove
```

More information [about docker](https://github.com/TheDailyBite/news-aggregator-service/tree/main/docker).

</p>
</details>

<details>
<summary>9. Cleanup</summary>
<p>
Delete pycache files

```bash
make pycache-remove
```

Remove package build

```bash
make build-remove
```

Delete .DS_STORE files

```bash
make dsstore-remove
```

Remove .mypycache

```bash
make mypycache-remove
```

Or to remove all above run:

```bash
make cleanup
```

</p>
</details>

## 📈 Releases

You can see the list of available releases on the [GitHub Releases](https://github.com/TheDailyBite/news-aggregator-service/releases) page.

We follow [Semantic Versions](https://semver.org/) specification.

We use [`Release Drafter`](https://github.com/marketplace/actions/release-drafter). As pull requests are merged, a draft release is kept up-to-date listing the changes, ready to publish when you’re ready. With the categories option, you can categorize pull requests in release notes using labels.

### List of labels and corresponding titles

|               **Label**               |  **Title in Releases**  |
| :-----------------------------------: | :---------------------: |
|       `enhancement`, `feature`        |       🚀 Features       |
| `bug`, `refactoring`, `bugfix`, `fix` | 🔧 Fixes & Refactoring  |
|       `build`, `ci`, `testing`        | 📦 Build System & CI/CD |
|              `breaking`               |   💥 Breaking Changes   |
|            `documentation`            |    📝 Documentation     |
|            `dependencies`             | ⬆️ Dependencies updates |

You can update it in [`release-drafter.yml`](https://github.com/TheDailyBite/news-aggregator-service/blob/main/.github/release-drafter.yml).

GitHub creates the `bug`, `enhancement`, and `documentation` labels for you. Dependabot creates the `dependencies` label. Create the remaining labels on the Issues tab of your GitHub repository, when you need them.

## 🛡 License

[![License](https://img.shields.io/github/license/TheDailyBite/news-aggregator-service)](https://github.com/TheDailyBite/news-aggregator-service/blob/main/LICENSE)

This project is licensed under the terms of the `MIT` license. See [LICENSE](https://github.com/TheDailyBite/news-aggregator-service/blob/main/LICENSE) for more details.

## 📃 Citation

```bibtex
@misc{news-aggregator-service,
  author = {TheDailyBite},
  title = {A cool news aggregator service.},
  year = {2023},
  publisher = {GitHub},
  journal = {GitHub repository},
  howpublished = {\url{https://github.com/TheDailyBite/news-aggregator-service}}
}
```

## Credits [![🚀 Your next Python package needs a bleeding-edge project structure.](https://img.shields.io/badge/python--package--template-%F0%9F%9A%80-brightgreen)](https://github.com/TezRomacH/python-package-template)

This project was generated with [`python-package-template`](https://github.com/TezRomacH/python-package-template)
