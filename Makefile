.PHONY: setup ingest extract eval serve test lint schema check demo docker

HOST ?= 0.0.0.0
PORT ?= 8000

setup:
	uv sync

ingest:
	uv run hwsets ingest data/raw

# make extract            -> every dev + gold book (never the hold-out)
# make extract DOC=<id>   -> one book
extract:
ifdef DOC
	uv run hwsets extract $(DOC)
else
	uv run hwsets extract --split dev
	uv run hwsets extract --split gold
endif

eval:
	uv run hwsets eval

serve:
	uv run uvicorn hwsets.api.server:app --host $(HOST) --port $(PORT)

test:
	uv run pytest

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run mypy

schema:
	uv run python -m hwsets.schema

check: lint test

# Preload the three demo books into data/results, then serve the review UI.
demo:
	uv run python scripts/demo.py
	$(MAKE) serve

docker:
	docker build -t hwsets .
