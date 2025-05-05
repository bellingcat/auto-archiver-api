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
# sed is unfortunately needed to fix a bug comming from vk-url-scraper that comes from brotli and the fact bk-ul-scraper can no longer be published to pypi
RUN sed -i 's/platform_python_implementation >= \\"CPython\\"/platform_python_implementation == \\"CPython\\"/g' poetry.lock && \
    poetry install --with web --no-interaction --no-ansi --no-cache

# Copy the application code and configurations
COPY ../../app ./app/
COPY ../../user-groups.* ./app/

# Run the FastAPI app with Uvicorn
ENTRYPOINT ["poetry", "run"]
