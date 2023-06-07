#* Variables
SHELL := /usr/bin/env bash
PYTHON := python
PYTHONPATH := `pwd`

#* Docker variables
IMAGE := news-aggregator-service
VERSION := latest
VERSION_LAMBDA_X86_64 := latest-lambda-x86_64
VERSION_LAMBDA_ARM64 := latest-lambda-arm64

#* Poetry
.PHONY: poetry-download
poetry-download:
	curl -sSL https://install.python-poetry.org | $(PYTHON) -

.PHONY: poetry-remove
poetry-remove:
	curl -sSL https://install.python-poetry.org | $(PYTHON) - --uninstall

#* Installation
.PHONY: install
install:
	poetry lock -n && poetry export --without-hashes > requirements.txt
	poetry install -n
	-poetry run mypy --install-types --non-interactive ./

.PHONY: pre-commit-install
pre-commit-install:
	poetry run pre-commit install

#* Formatters
.PHONY: codestyle
codestyle:
	poetry run pyupgrade --exit-zero-even-if-changed --py39-plus **/*.py
	poetry run isort --settings-path pyproject.toml ./
	poetry run black --config pyproject.toml ./

.PHONY: formatting
formatting: codestyle

#* Linting
.PHONY: test
test:
	PYTHONPATH=$(PYTHONPATH) poetry run pytest -c pyproject.toml --cov-report=html --cov=news_aggregator_service tests/
	poetry run coverage-badge -o assets/images/coverage.svg -f

.PHONY: check-codestyle
check-codestyle:
	poetry run isort --diff --check-only --settings-path pyproject.toml ./
	poetry run black --diff --check --config pyproject.toml ./
	poetry run darglint --verbosity 2 news_aggregator_service tests

.PHONY: mypy
mypy:
	poetry run mypy --config-file pyproject.toml ./

.PHONY: check-safety
check-safety:
	poetry check
	poetry run safety check --full-report --ignore=51457 # ignoring CVE-2022-42969 for py <= 1.11.0 which is installed via pytest. No upgrade available.
	poetry run bandit -ll --recursive news_aggregator_service tests

.PHONY: lint
lint: test check-codestyle mypy check-safety

.PHONY: update-dev-deps
update-dev-deps:
	poetry add -D bandit@latest darglint@latest "isort[colors]@latest" mypy@latest pre-commit@latest pydocstyle@latest pylint@latest pytest@latest pyupgrade@latest safety@latest coverage@latest coverage-badge@latest pytest-html@latest pytest-cov@latest
	poetry add -D --allow-prereleases black@latest

#* Docker
# Example: make docker-build VERSION=latest
# Example: make docker-build IMAGE=some_name VERSION=0.1.0
.PHONY: docker-build
docker-build:
	@echo Building docker $(IMAGE):$(VERSION) ...
	docker build \
		--ssh default=${SSH_AUTH_SOCK} \
		-t $(IMAGE):$(VERSION) . \
		-f ./docker/Dockerfile --no-cache

# Example: make docker-remove VERSION=latest
# Example: make docker-remove IMAGE=some_name VERSION=0.1.0
.PHONY: docker-remove
docker-remove:
	@echo Removing docker $(IMAGE):$(VERSION) ...
	docker rmi -f $(IMAGE):$(VERSION)

#* Docker
# Example: make docker-build-lambda-x86-64 VERSION=latest
# Example: make docker-build-lambda-x86-64 IMAGE=some_name VERSION=0.1.0
.PHONY: docker-build-lambda-x86-64
docker-build-lambda-x86-64:
	@echo Building docker $(IMAGE):$(VERSION_LAMBDA_X86_64) ...
	docker build \
		--ssh default=${SSH_AUTH_SOCK} \
		-t $(IMAGE):$(VERSION_LAMBDA_X86_64) . \
		-f ./docker/Dockerfile-Lambda-x86_64 --no-cache

# Example: make docker-remove-lambda-x86-64 VERSION=latest
# Example: make docker-remove-lambda-x86-64 IMAGE=some_name VERSION=0.1.0
.PHONY: docker-remove-lambda-x86-64
docker-remove-lambda-x86-64:
	@echo Removing docker $(IMAGE):$(VERSION_LAMBDA_X86_64) ...
	docker rmi -f $(IMAGE):$(VERSION_LAMBDA_X86_64)

#* Docker
# Example: make docker-build-lambda-arm64 VERSION=latest
# Example: make docker-build-lambda-arm64 IMAGE=some_name VERSION=0.1.0
.PHONY: docker-build-lambda-arm64
docker-build-lambda-arm64:
	@echo Building docker $(IMAGE):$(VERSION_LAMBDA_ARM64) ...
	docker build \
		--ssh default=${SSH_AUTH_SOCK} \
		-t $(IMAGE):$(VERSION_LAMBDA_ARM64) . \
		-f ./docker/Dockerfile-Lambda-lambda-arm64 --no-cache

# Example: make docker-remove-lambda-arm64 VERSION=latest
# Example: make docker-remove-lambda-arm64 IMAGE=some_name VERSION=0.1.0
.PHONY: docker-remove-lambda-arm64
docker-remove-lambda-arm64:
	@echo Removing docker $(IMAGE):$(VERSION_LAMBDA_ARM64) ...
	docker rmi -f $(IMAGE):$(VERSION_LAMBDA_ARM64)

#* Cleaning
.PHONY: pycache-remove
pycache-remove:
	find . | grep -E "(__pycache__|\.pyc|\.pyo$$)" | xargs rm -rf

.PHONY: dsstore-remove
dsstore-remove:
	find . | grep -E ".DS_Store" | xargs rm -rf

.PHONY: mypycache-remove
mypycache-remove:
	find . | grep -E ".mypy_cache" | xargs rm -rf

.PHONY: ipynbcheckpoints-remove
ipynbcheckpoints-remove:
	find . | grep -E ".ipynb_checkpoints" | xargs rm -rf

.PHONY: pytestcache-remove
pytestcache-remove:
	find . | grep -E ".pytest_cache" | xargs rm -rf

.PHONY: build-remove
build-remove:
	rm -rf build/

.PHONY: cleanup
cleanup: pycache-remove dsstore-remove mypycache-remove ipynbcheckpoints-remove pytestcache-remove
