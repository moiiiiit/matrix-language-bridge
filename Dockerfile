FROM python:3.12-slim

WORKDIR /app

# Install build deps for lingua-py (it compiles a Rust extension)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev && rm -rf /var/lib/apt/lists/*

ENV POETRY_VERSION=1.8.5 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/tmp/poetry-cache

RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

COPY pyproject.toml poetry.lock* ./
RUN poetry install --only main --no-root && rm -rf "$POETRY_CACHE_DIR"

COPY languagebridge/ ./languagebridge/
RUN poetry install --only main && rm -rf "$POETRY_CACHE_DIR"

# Non-root user
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Config and data as volumes
VOLUME ["/app/config", "/app/data"]

CMD ["poetry", "run", "languagebridge"]
