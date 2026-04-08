# Multi-stage: runtime (default) + test (target: test)
FROM python:3.12-slim AS base

WORKDIR /app

# lingua may need a compiler for some platforms; E2EE needs libolm + cmake to build/link python-olm
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    pkg-config \
    libffi-dev \
    libolm-dev \
    && rm -rf /var/lib/apt/lists/*

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/tmp/poetry-cache

RUN pip install --no-cache-dir "poetry>=1.8,<3"

COPY pyproject.toml poetry.lock README.md ./

# --- Main dependencies only (bot runtime)
FROM base AS deps-main
RUN poetry install --only main --extras e2ee --no-root && rm -rf "$POETRY_CACHE_DIR"

# --- Main + dev (pytest) for CI image
FROM base AS deps-dev
RUN poetry install --with dev --extras e2ee --no-root && rm -rf "$POETRY_CACHE_DIR"

# --- Test image (default `docker build --target test`)
FROM deps-dev AS test
COPY languagebridge/ ./languagebridge/
COPY tests/ ./tests/
RUN poetry install --with dev --extras e2ee && rm -rf "$POETRY_CACHE_DIR"
CMD ["poetry", "run", "pytest", "tests/", "-v", "--tb=short"]

# --- Production image (default `docker build`)
FROM deps-main AS runtime
COPY languagebridge/ ./languagebridge/
RUN poetry install --only main --extras e2ee && rm -rf "$POETRY_CACHE_DIR"

RUN useradd -m appuser && chown -R appuser /app
USER appuser

VOLUME ["/app/config", "/app/data"]

CMD ["poetry", "run", "languagebridge"]
