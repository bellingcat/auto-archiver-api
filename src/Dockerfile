# From python:3.10
FROM bellingcat/auto-archiver

# set work directory
WORKDIR /app

RUN curl -fsSL https://get.docker.com -o get-docker.sh && \
    sh get-docker.sh
# set environment variables
ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1

# install dependencies
RUN pip install --upgrade pip && \
	apt-get update 
COPY Pipfile* ./
RUN pipenv install

# copy src code over
COPY . .

ENTRYPOINT ["pipenv", "run"]