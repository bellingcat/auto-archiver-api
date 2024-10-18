import asyncio
import logging
import alembic.config
from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi_utils.tasks import repeat_every
from loguru import logger

from db import crud, models
from db.database import get_db, make_engine
from shared.settings import Settings
from utils.metrics import measure_regular_metrics, redis_subscribe_worker_exceptions

settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # see https://fastapi.tiangolo.com/advanced/events/#lifespan

    # STARTUP
    engine = make_engine(settings.DATABASE_PATH)
    models.Base.metadata.create_all(bind=engine)
    alembic.config.main(argv=['--raiseerr', 'upgrade', 'head'])
    # disabling uvicorn logger since we use loguru in logging_middleware
    logging.getLogger("uvicorn.access").disabled = True
    asyncio.create_task(redis_subscribe_worker_exceptions())
    asyncio.create_task(refresh_user_groups())
    asyncio.create_task(repeat_measure_regular_metrics())

    yield  # separates startup from shutdown instructions

    # SHUTDOWN
    logger.info("shutting down")


# CRON JOBS

@repeat_every(seconds=60 * 60)  # 1 hour
async def refresh_user_groups():
    with get_db() as db:
        crud.upsert_user_groups(db)


@repeat_every(seconds=settings.REPEAT_COUNT_METRICS_SECONDS)
async def repeat_measure_regular_metrics():
    measure_regular_metrics(settings.DATABASE_PATH, settings.REPEAT_COUNT_METRICS_SECONDS)
