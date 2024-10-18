import asyncio
import json
import os
import shutil
from loguru import logger
from prometheus_client import Counter, Gauge
from sqlalchemy.orm import Session

from db import crud
from db.database import get_db
from worker import REDIS_EXCEPTIONS_CHANNEL, Rdis


# Custom metrics
EXCEPTION_COUNTER = Counter(
    "exceptions",
    "Number of times a certain exception has occurred.",
    labelnames=("types",)
)
WORKER_EXCEPTION = Counter(
    "worker_exceptions_total",
    "Number of times a certain exception has occurred on the worker.",
    labelnames=("exception", "task",)
)
DISK_UTILIZATION = Gauge(
    "disk_utilization",
    "Disk utilization in GB",
    labelnames=("type",)
)
DATABASE_METRICS = Gauge(
    "database_metrics",
    "Useful database metrics from queries",
    labelnames=("query", "user")
)


async def redis_subscribe_worker_exceptions():
    # Subscribe to Redis channel and increment the counter for each exception with info on the exception and task
    PubSubExceptions = Rdis.pubsub()
    PubSubExceptions.subscribe(REDIS_EXCEPTIONS_CHANNEL)
    while True:
        message = PubSubExceptions.get_message()
        if message and message["type"] == "message":
            data = json.loads(message["data"].decode("utf-8"))
            WORKER_EXCEPTION.labels(exception=data["exception"], task=data["task"]).inc()
        await asyncio.sleep(1)

async def measure_regular_metrics(sqlite_db_url:str, repeat_in_seconds:int):
    _total, used, free = shutil.disk_usage("/")
    DISK_UTILIZATION.labels(type="used").set(used / (2**30))
    DISK_UTILIZATION.labels(type="free").set(free / (2**30))
    try: 
        fs = os.stat(sqlite_db_url.replace("sqlite:///", ""))
        DISK_UTILIZATION.labels(type="database").set(fs.st_size / (2**30))
    except Exception as e: logger.error(e)

    with get_db as db:
        count_archives = crud.count_archives(db)
        count_archive_urls = crud.count_archive_urls(db)
        DATABASE_METRICS.labels(query="count_archives", user="-").set(count_archives)
        DATABASE_METRICS.labels(query="count_archive_urls", user="-").set(count_archive_urls)

        for user in crud.count_by_user_since(db, repeat_in_seconds):
            DATABASE_METRICS.labels(query="count_by_user", user=user.author_id).set(user.total)