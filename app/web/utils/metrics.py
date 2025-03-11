import asyncio
import json
import os
import shutil

from prometheus_client import Counter, Gauge

from app.shared.db.database import get_db
from app.shared.log import log_error
from app.shared.task_messaging import get_redis
from app.web.db import crud


# Custom metrics
EXCEPTION_COUNTER = Counter(
    "exceptions",
    "Number of times a certain exception has occurred.",
    labelnames=["type", "location"],
)
WORKER_EXCEPTION = Counter(
    "worker_exceptions_total",
    "Number of times a certain exception has occurred on the worker.",
    labelnames=["type", "exception", "task", "traceback"],
)
DISK_UTILIZATION = Gauge(
    "disk_utilization", "Disk utilization in GB", labelnames=["type"]
)
DATABASE_METRICS = Gauge(
    "database_metrics",
    "Database metric readings at a certain point in time",
    labelnames=["query"],
)
DATABASE_METRICS_COUNTER = Counter(
    "database_metrics_counter",
    "Database metrics that increase over time",
    labelnames=["query", "user"],
)


async def redis_subscribe_worker_exceptions(redis_exceptions_channel: str):
    # Subscribe to Redis channel and increment the counter for each exception with info on the exception and task
    Redis = get_redis()
    PubSubExceptions = Redis.pubsub()
    PubSubExceptions.subscribe(redis_exceptions_channel)
    while True:
        message = PubSubExceptions.get_message()
        if message and message["type"] == "message":
            data = json.loads(message["data"].decode("utf-8"))
            WORKER_EXCEPTION.labels(
                type=data["type"],
                exception=data["exception"],
                task=data["task"],
                traceback=data["traceback"],
            ).inc()
        await asyncio.sleep(1)


async def measure_regular_metrics(sqlite_db_url: str, repeat_in_seconds: int):
    _total, used, free = shutil.disk_usage("/")
    DISK_UTILIZATION.labels(type="used").set(used / (2**30))
    DISK_UTILIZATION.labels(type="free").set(free / (2**30))
    try:
        fs = os.stat(sqlite_db_url.replace("sqlite:///", ""))
        DISK_UTILIZATION.labels(type="database").set(fs.st_size / (2**30))
    except Exception as e:
        log_error(e)

    with get_db() as db:
        DATABASE_METRICS.labels(query="count_archives").set(
            crud.count_archives(db)
        )
        DATABASE_METRICS.labels(query="count_archive_urls").set(
            crud.count_archive_urls(db)
        )
        DATABASE_METRICS.labels(query="count_users").set(crud.count_users(db))

        for user in crud.count_by_user_since(db, repeat_in_seconds):
            DATABASE_METRICS_COUNTER.labels(
                query="count_by_user", user=user.author_id
            ).inc(user.total)
