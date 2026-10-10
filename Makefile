.PHONY: setup ingest test lint schema

setup:
	uv sync

ingest:
	uv run hwsets ingest data/raw

test:
	uv run pytest

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run mypy

schema:
	uv run python -m hwsets.schema
