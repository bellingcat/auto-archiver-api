# From python:3.10
FROM bellingcat/auto-archiver:v0.13.4

# set work directory
WORKDIR /aa-api

RUN curl -fsSL https://get.docker.com -o get-docker.sh && \
    sh get-docker.sh
# set environment variables
ENV LANG=C.UTF-8 \
	PYTHONUNBUFFERED=1 \
	PYTHONDONTWRITEBYTECODE=1 \
	POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1

# install dependencies
RUN apt update -y && \
	apt install -y python3-venv && \
	python3 -m venv ./poetry-venv && \
    ./poetry-venv/bin/python -m pip install --upgrade pip && \
    ./poetry-venv/bin/python -m pip install "poetry>=2.0.0,<3.0.0"
COPY pyproject.toml poetry.lock ./
RUN ./poetry-venv/bin/poetry install --without dev --no-root --no-cache

# install dependencies

# copy source code and .env files over
COPY alembic.ini ./
COPY ./app/ ./app/
COPY user-groups.* ./app/

ENTRYPOINT ["./poetry-venv/bin/poetry", "run"]