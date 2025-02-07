import asyncio
import datetime
import logging
import alembic.config
from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi_utils.tasks import repeat_every
from loguru import logger
from sqlalchemy import text

from db import crud, models, schemas
from db.database import get_db, get_db_async, make_engine, wal_checkpoint
from shared.settings import get_settings
from utils.metrics import measure_regular_metrics, redis_subscribe_worker_exceptions
from worker.main import create_sheet_task
from fastapi_mail import FastMail, MessageSchema, MessageType


@asynccontextmanager
async def lifespan(app: FastAPI):
    # see https://fastapi.tiangolo.com/advanced/events/#lifespan

    # STARTUP
    engine = make_engine(get_settings().DATABASE_PATH)
    models.Base.metadata.create_all(bind=engine)
    alembic.config.main(argv=['--raiseerr', 'upgrade', 'head'])
    logging.getLogger("uvicorn.access").disabled = True  # loguru
    asyncio.create_task(redis_subscribe_worker_exceptions(get_settings().REDIS_EXCEPTIONS_CHANNEL, get_settings().CELERY_BROKER_URL))
    asyncio.create_task(repeat_measure_regular_metrics())
    with get_db() as db:
        crud.upsert_user_groups(db)

    # setup archive cronjobs
    if get_settings().CRON_ARCHIVE_SHEETS:
        asyncio.create_task(archive_hourly_sheets_cronjob())
        asyncio.create_task(archive_daily_sheets_cronjob())
    else:
        logger.warning("[CRON] Sheet archive cronjobs are disabled.")

    if get_settings().CRON_DELETE_STALE_SHEETS:
        asyncio.create_task(delete_stale_sheets())
    else:
        logger.warning("[CRON] Delete stale sheets cronjob is disabled.")

    wal_checkpoint()

    yield  # separates startup from shutdown instructions

    # SHUTDOWN
    logger.info("shutting down")


# CRON JOBS
@repeat_every(seconds=get_settings().REPEAT_COUNT_METRICS_SECONDS, on_exception=logger.error)
async def repeat_measure_regular_metrics():
    await measure_regular_metrics(get_settings().DATABASE_PATH, get_settings().REPEAT_COUNT_METRICS_SECONDS)


@repeat_every(seconds=60, wait_first=120, on_exception=logger.error)
async def archive_hourly_sheets_cronjob():
    await archive_sheets_cronjob("hourly", 60, datetime.datetime.now().minute)


@repeat_every(seconds=3600, wait_first=120, on_exception=logger.error)
async def archive_daily_sheets_cronjob():
    await archive_sheets_cronjob("daily", 24, datetime.datetime.now().hour)


async def archive_sheets_cronjob(frequency: str, interval: int, current_time_unit: int):
    triggered_jobs = []

    async with get_db_async() as db:
        sheets = await crud.get_sheets_by_id_hash(db, frequency, interval, current_time_unit)
        for s in sheets:
            task = create_sheet_task.apply_async(args=[schemas.SubmitSheet(sheet_id=s.id, author_id=s.author_id, group=s.group_id).model_dump_json()])
            triggered_jobs.append({"sheet_id": s.id, "task_id": task.id})
    logger.info(f"[CRON {frequency.upper()}:{current_time_unit}] Triggered {len(triggered_jobs)} sheet tasks: {triggered_jobs}")


@repeat_every(seconds=86400, wait_first=150, on_exception=logger.error)
async def delete_stale_sheets():
    STALE_DAYS = get_settings().DELETE_STALE_SHEETS_DAYS
    logger.info(f"[CRON] Deleting stale sheets older than {STALE_DAYS} days.")
    async with get_db_async() as db:
        user_sheets = await crud.delete_stale_sheets(db, STALE_DAYS)

    if not user_sheets: return

    fastmail = FastMail(get_settings().MAIL_CONFIG)
    # notify users
    for email in user_sheets:
        list_of_sheets = "\n".join([f'<li><a href="https://docs.google.com/spreadsheets/d/{s.id}">{s.name}</a></li>' for s in user_sheets[email]])
        message = MessageSchema(
            subject="Auto Archiver: Stale Sheets Removed",
            recipients=[email],
            body=f"""
            <html>
            <body>
                <p>Hi {email},</p>
                <p>Your stale sheets have been removed from our system as no new URL was archived in the past {STALE_DAYS} days:</p>
                <ul>
                {list_of_sheets}
                </ul>
                <p>You can always re-add them at https://auto-archiver.bellingcat.com/.</p>
                <p>Best,<br>The Auto Archiver team</p>
            </body>
            </html>
            """,
            subtype=MessageType.html
        )
        await fastmail.send_message(message)
        logger.info(f"[CRON] Email sent to {email} about stale sheets deletion.")

