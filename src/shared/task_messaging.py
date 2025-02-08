
from functools import lru_cache
from celery import Celery
import redis

from shared.settings import get_settings

@lru_cache
def get_celery(name:str="") -> Celery:
    return Celery(
        name,
        broker_url=get_settings().CELERY_BROKER_URL,
        result_backend=get_settings().CELERY_RESULT_BACKEND,
    )


def get_redis() -> redis.Redis:
    return redis.Redis.from_url(get_settings().CELERY_BROKER_URL)
