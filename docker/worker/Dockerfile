# From python:3.10
FROM bellingcat/auto-archiver:v1.2.5
# NOTE: remove dot from v.1, this release was badly named

# set work directory
WORKDIR /aa-api

# Switch to root for privileged operations (base image runs as UID 1000)
USER root

RUN curl -fsSL https://get.docker.com -o get-docker.sh && \
    sh get-docker.sh && \
    usermod -aG docker ubuntu
# set environment variables
ENV LANG=C.UTF-8 \
	PYTHONUNBUFFERED=1 \
	PYTHONDONTWRITEBYTECODE=1 \
	POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1

# install dependencies
RUN apt update -y && \
	apt install -y python3-venv python3-tk python3-dev && \
	python3 -m venv ./poetry-venv && \
    ./poetry-venv/bin/python -m pip install --upgrade pip && \
    ./poetry-venv/bin/python -m pip install "poetry>=2.0.0,<3.0.0"
COPY ../../pyproject.toml ../../poetry.lock ./
RUN ./poetry-venv/bin/poetry install --without dev --no-root --no-cache

# install dependencies

# copy source code and .env files over
COPY ../../app ./app/
COPY ../../user-groups.* ./app/

# Pre-create directories and fix ownership for non-root user (UID 1000)
# - /crawls: named volume for Browsertrix WACZ crawl data
# - /aa-api: WORKDIR, auto-archiver creates TemporaryDirectory(dir="./") here
# - /aa-api/logs, /aa-api/database, /aa-api/secrets: bind-mounted at runtime
# - seleniumbase drivers dir: chromedriver downloaded at runtime
RUN mkdir -p /crawls /aa-api/logs /aa-api/database /aa-api/secrets && \
    chown -R 1000:1000 /crawls /aa-api && \
    chown -R 1000:1000 /app/.venv/lib/python3.12/site-packages/seleniumbase/drivers

# Switch back to non-root user
USER 1000

ENTRYPOINT ["./poetry-venv/bin/poetry", "run"]
