# pull official base image 3.9
# FROM python:3.9.5-slim-buster
From python:3.10

# set work directory
WORKDIR /usr/src/app

# set environment variables
ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1

# install dependencies
RUN pip install --upgrade pip && \
	apt-get update && \
	apt-get install -y gcc ffmpeg fonts-noto firefox-esr exiftool && \
	wget https://github.com/mozilla/geckodriver/releases/download/v0.32.0/geckodriver-v0.32.0-linux64.tar.gz && \
	tar -xvzf geckodriver* -C /usr/local/bin && \
	chmod +x /usr/local/bin/geckodriver && \
	rm geckodriver-v* 
COPY ./requirements.txt .
RUN pip install -r requirements.txt

# copy src code over
COPY . .
