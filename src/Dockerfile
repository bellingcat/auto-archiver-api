# FROM webrecorder/browsertrix-crawler:latest

# ENV RUNNING_IN_DOCKER=1
# ENV PYTHONUNBUFFERED 1
# ENV PYTHONDONTWRITEBYTECODE 1

# WORKDIR /app/aa-api

# RUN pip install --upgrade pip && \
# 	pip install pipenv && \
# 	add-apt-repository ppa:mozillateam/ppa && \
# 	apt-get update && \
# 	apt-get install -y gcc ffmpeg fonts-noto exiftool && \
# 	apt-get install -y --no-install-recommends firefox-esr && \
# 	ln -s /usr/bin/firefox-esr /usr/bin/firefox && \
# 	wget https://github.com/mozilla/geckodriver/releases/download/v0.33.0/geckodriver-v0.33.0-linux64.tar.gz && \
# 	tar -xvzf geckodriver* -C /usr/local/bin && \
# 	chmod +x /usr/local/bin/geckodriver && \
# 	rm geckodriver-v* 


# # COPY requirements.txt ./
# COPY Pipfile* ./
# # install from pipenv, with browsertrix-only requirements
# # RUN pip install -r requirements.txt
# RUN pipenv install && \
# 	pipenv install pywb uwsgi
	
# # doing this at the end helps during development, builds are quick
# COPY . . 

# ENTRYPOINT ["pipenv", "run"]
# # ENTRYPOINT ["python3", "-m", "auto_archiver"]

# # should be executed with 2 volumes (3 if local_storage is used)
# # docker run --rm -v $PWD/secrets:/app/secrets -v $PWD/local_archive:/app/local_archive aa pipenv run python3 -m auto_archiver --config secrets/orchestration.yaml


# FROM python:3.10
FROM ubuntu:22.04
# WORKDIR /app
WORKDIR /app

RUN apt update && \
	apt install -y curl wget

# Uncomment to try DinD but that leads to 'Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?' with no easy solution in sight
# RUN curl -fsSL https://get.docker.com -o get-docker.sh && \
# 	sh get-docker.sh

RUN apt install -y software-properties-common

RUN apt install -y gcc ffmpeg fonts-noto exiftool && \
	add-apt-repository ppa:mozillateam/ppa

RUN	apt install -y --no-install-recommends firefox-esr && \
	ln -s /usr/bin/firefox-esr /usr/bin/firefox && \
	wget https://github.com/mozilla/geckodriver/releases/download/v0.33.0/geckodriver-v0.33.0-linux64.tar.gz && \
	tar -xvzf geckodriver* -C /usr/local/bin && \
	chmod +x /usr/local/bin/geckodriver && \
	rm geckodriver-v*

COPY Pipfile* ./ 

RUN apt install -y python3.10 python3-pip && \
	pip install --upgrade pip && \ 
	pip install pipenv && \
	pipenv install
RUN apt install -y git
RUN echo 'from here 6'; pipenv install -e git+https://github.com/bellingcat/auto-archiver.git@wacz-docker-fix#egg=auto_archiver


COPY . .

ENTRYPOINT ["pipenv", "run"]



# # FROM bellingcat/auto-archiver:latest
# FROM aa
# # FROM python:3.10-slim
# # FROM	 ubuntu:22.04
# # set work directory, it's not /app since that overrides browsetrix

# # RUN curl -fsSL https://get.docker.com -o get-docker.sh && \
# # 	sh get-docker.sh

# # WORKDIR /app
# WORKDIR /app

# # set environment variables
# ENV PYTHONUNBUFFERED 1
# ENV PYTHONDONTWRITEBYTECODE 1

# # install dependencies
# COPY Pipfile* ./
# # RUN pip install --upgrade pip && \
# # 	apt-get update && \
# # 	pipenv install
# RUN pipenv install
# RUN pipenv install -e git+https://github.com/bellingcat/auto-archiver.git@wacz-docker-fix#egg=auto_archiver


# # copy src code over
# COPY . .

# ENTRYPOINT ["pipenv", "run"]
# # ENTRYPOINT ["/bin/sh", "-c"]