from functools import lru_cache

from celery import Celery

import redis
from app.shared.settings import get_settings


@lru_cache
def get_celery(name: str = "") -> Celery:
    return Celery(
        name,
        broker_url=get_settings().celery_broker_url,
        result_backend=get_settings().celery_broker_url,
        broker_connection_retry_on_startup=True,
        broker_transport_options={
            "queue_order_strategy": "priority",
            "visibility_timeout": 43200,  # 12 hours - must be > longest task time_limit
        },
        result_expires=86400,  # expire task results after 24 hours to prevent Redis memory buildup
        worker_cancel_long_running_tasks_on_connection_loss=True,
    )


def get_redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().celery_broker_url)
