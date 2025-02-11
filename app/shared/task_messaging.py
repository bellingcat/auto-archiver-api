
from functools import lru_cache
from celery import Celery
import redis

from app.shared.settings import get_settings

@lru_cache
def get_celery(name:str="") -> Celery:
    return Celery(
        name,
        broker_url=get_settings().CELERY_BROKER_URL,
        result_backend=get_settings().CELERY_BROKER_URL,
    )


def get_redis() -> redis.Redis:
    from loguru import logger
    logger.debug(get_settings().CELERY_BROKER_URL)
    return redis.Redis.from_url(get_settings().CELERY_BROKER_URL)
