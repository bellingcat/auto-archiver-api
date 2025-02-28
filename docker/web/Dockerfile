# Stage 1: install dependencies
FROM python:3.10-slim AS build

WORKDIR /aa-api
# TODO: multistage build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry
COPY ../../pyproject.toml ../../poetry.lock ../../README.md ./
RUN poetry install --with web --no-interaction --no-ansi --no-cache

# Copy the application code and configurations
COPY ../../app/migrations/alembic.ini ./
COPY ../../app ./app/
COPY ../../user-groups.* ./app/

# Run the FastAPI app with Uvicorn
ENTRYPOINT ["poetry", "run"]
