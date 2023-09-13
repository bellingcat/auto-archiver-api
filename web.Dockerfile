FROM python:3.11-slim as python-build

WORKDIR /app

COPY Pipfile* .

RUN apt update && \
    apt install -y g++ && \
    pip install pipenv && \
    pipenv requirements > requirements.txt && \
    python -m venv /opt/venv && \
    /opt/venv/bin/pip install -U pip wheel && \
    /opt/venv/bin/pip install -U -r requirements.txt

FROM python:3.11-slim as python-deploy

WORKDIR /app

COPY --from=python-build /opt/venv /opt/venv

COPY app /app
# COPY alembic.ini .

ENV VIRTUAL_ENV /opt/venv
ENV PATH /opt/venv/bin:$PATH

# CMD alembic upgrade head && uvicorn app.web:app --host ${HOST:-0.0.0.0} --port ${PORT:-8000} --log-level info --workers 4 --proxy-headers
CMD uvicorn web.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8000} --log-level info --workers 4 --proxy-headers