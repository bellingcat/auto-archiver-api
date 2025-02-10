# From python:3.10
FROM bellingcat/auto-archiver

# set work directory
WORKDIR /aa-api

RUN curl -fsSL https://get.docker.com -o get-docker.sh && \
    sh get-docker.sh
# set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# install dependencies
RUN pip install --upgrade pip && \
	apt-get update 
COPY ./Pipfile* ./
RUN pipenv install

# copy source code and .env files over
COPY alembic.ini ./
COPY .env* ./app/
COPY ./secrets/ ./secrets/
COPY ./app/ ./app/

ENTRYPOINT ["pipenv", "run"]