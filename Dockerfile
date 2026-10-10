# syntax=docker/dockerfile:1
# hwsets: review UI + extractor in one image (Tesseract/ocrmypdf for image-only pages).
#
#   docker build -t hwsets .
#   docker compose up            # serves http://localhost:8000, mounts ./data
#
# At startup, if the demo PDFs are present under data/raw (mounted), scripts/demo.py
# ingests + extracts them (idempotent, token cache reused); otherwise the server just serves
# whatever is already in data/results. Set HWSETS_DEMO=0 to skip the preload step.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr ocrmypdf ghostscript \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /uvx /usr/local/bin/

WORKDIR /app

# Dependencies first (cached layer), then the project itself.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

COPY scripts/demo.py ./scripts/demo.py
COPY data/gold ./data/gold
COPY data/splits.json data/survey.md ./data/
COPY data/survey ./data/survey

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin app \
    && mkdir -p data/raw data/tokens data/pages data/results data/corrections \
    && chown -R app:app /app/data

ENV PATH="/app/.venv/bin:${PATH}" \
    HWSETS_DATA=/app/data \
    HWSETS_DEMO=1

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/api/docs/list', timeout=4).status != 200)"]

CMD ["sh", "-c", "if [ \"$HWSETS_DEMO\" != 0 ] && [ -n \"$(find data/raw -maxdepth 3 -iname '*.pdf' -print -quit 2>/dev/null)\" ]; then python scripts/demo.py --data data || echo 'demo preload failed; serving existing results'; fi; exec uvicorn hwsets.api.server:app --host 0.0.0.0 --port 8000"]
