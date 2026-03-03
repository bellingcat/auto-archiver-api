import asyncio
import datetime
import logging
from collections import defaultdict
from contextlib import asynccontextmanager

import alembic.config
from fastapi import FastAPI
from fastapi_mail import FastMail, MessageSchema, MessageType
from fastapi_utils.tasks import repeat_every

from app.shared import schemas
from app.shared.db import models
from app.shared.db.database import (
    get_db,
    get_db_async,
    make_engine,
    wal_checkpoint,
)
from app.shared.log import logger
from app.shared.settings import get_settings
from app.shared.task_messaging import get_celery
from app.shared.utils.sheets import get_sheet_access_error
from app.web.db import crud
from app.web.middleware import increase_exceptions_counter
from app.web.utils.metrics import (
    measure_regular_metrics,
    redis_subscribe_worker_exceptions,
)


celery = get_celery()

# Throttle cache: track when each sheet was last notified about missing
# permissions so users are not spammed on every cron cycle.
_sheet_no_access_notified: dict[str, datetime.datetime] = {}
_NOTIFY_COOLDOWN = datetime.timedelta(hours=24)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # see https://fastapi.tiangolo.com/advanced/events/#lifespan

    # STARTUP
    engine = make_engine(get_settings().DATABASE_PATH)
    models.Base.metadata.create_all(bind=engine)
    alembic.config.main(
        prog="alembic",
        argv=[
            "-c",
            "./app/migrations/alembic.ini",
            "--raiseerr",
            "upgrade",
            "head",
        ],
    )
    logging.getLogger("uvicorn.access").disabled = True  # loguru
    asyncio.create_task(
        redis_subscribe_worker_exceptions(
            get_settings().REDIS_EXCEPTIONS_CHANNEL
        )
    )
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

    if get_settings().CRON_DELETE_SCHEDULED_ARCHIVES:
        asyncio.create_task(notify_about_expired_archives())
    else:
        logger.warning("[CRON] Delete scheduled archives cronjob is disabled.")

    wal_checkpoint()

    yield  # separates startup from shutdown instructions

    # SHUTDOWN
    logger.info("shutting down")


# CRON JOBS
@repeat_every(
    seconds=get_settings().REPEAT_COUNT_METRICS_SECONDS,
    on_exception=increase_exceptions_counter,
)
async def repeat_measure_regular_metrics():
    await measure_regular_metrics(
        get_settings().DATABASE_PATH,
        get_settings().REPEAT_COUNT_METRICS_SECONDS,
    )


@repeat_every(
    seconds=60, wait_first=120, on_exception=increase_exceptions_counter
)
async def archive_hourly_sheets_cronjob():
    await archive_sheets_cronjob("hourly", 60, datetime.datetime.now().minute)


@repeat_every(
    seconds=3600, wait_first=120, on_exception=increase_exceptions_counter
)
async def archive_daily_sheets_cronjob():
    await archive_sheets_cronjob("daily", 24, datetime.datetime.now().hour)


async def archive_sheets_cronjob(
    frequency: str, interval: int, current_time_unit: int
):
    triggered_jobs = []
    no_access_sheets: dict[str, list[tuple]] = defaultdict(list)

    async with get_db_async() as db:
        sheets = await crud.get_sheets_by_id_hash(
            db, frequency, str(interval), current_time_unit
        )
        for s in sheets:
            # Check if service account has write access to the sheet
            group = await db.get(models.Group, s.group_id)
            if group and group.orchestrator_sheet:
                access_error = get_sheet_access_error(
                    group.orchestrator_sheet,
                    group.service_account_email,
                    s.id,
                )
                if access_error:
                    no_access_sheets[s.author_id].append(
                        (s, group.service_account_email or "")
                    )
                    logger.warning(
                        f"[CRON] Skipping sheet {s.id}: not shared with "
                        f"service account {group.service_account_email}"
                    )
                    continue

            group_queue = await crud.get_group_priority_async(db, s.group_id)
            task = celery.signature(
                "create_sheet_task",
                args=[
                    schemas.SubmitSheet(
                        sheet_id=s.id,
                        author_id=s.author_id,
                        group_id=s.group_id,
                    ).model_dump_json()
                ],
            ).apply_async(**group_queue)

            triggered_jobs.append({"sheet_id": s.id, "task_id": task.id})

    if no_access_sheets:
        await _notify_sheet_permission_issues(no_access_sheets)

    logger.debug(
        f"[CRON {frequency.upper()}:{current_time_unit}] Triggered {len(triggered_jobs)} sheet tasks: {triggered_jobs}"
    )


async def _notify_sheet_permission_issues(
    no_access_sheets: dict[str, list[tuple]],
):
    """
    Send email notifications to users whose sheets are not shared with the
    Auto Archiver service account. Throttled to at most one email per sheet
    per 24 hours to avoid spamming.
    """
    now = datetime.datetime.now()
    fastmail = FastMail(get_settings().mail_config)

    for email, sheet_infos in no_access_sheets.items():
        # Filter to sheets that haven't been notified recently
        sheets_to_notify = []
        for s, sa_email in sheet_infos:
            last = _sheet_no_access_notified.get(s.id)
            if not last or (now - last) >= _NOTIFY_COOLDOWN:
                sheets_to_notify.append((s, sa_email))
                _sheet_no_access_notified[s.id] = now

        if not sheets_to_notify:
            continue

        list_of_sheets = "\n".join(
            [
                f'<li><a href="https://docs.google.com/spreadsheets/d/{s.id}">'
                f"{s.name}</a> &mdash; share with <code>{sa_email}</code></li>"
                for s, sa_email in sheets_to_notify
            ]
        )
        message = MessageSchema(
            subject="Auto Archiver: Sheet Permission Issue",
            recipients=[email],
            body=f"""
            <html>
            <body>
                <p>Hi {email},</p>
                <p>The following sheets could not be archived because they have
                not been shared with the Auto Archiver service account with
                <strong>Editor</strong> permissions:</p>
                <ul>
                {list_of_sheets}
                </ul>
                <p>Please open each sheet, click <em>Share</em>, and add the
                service account email shown above as an <strong>Editor</strong>.
                The sheets will be archived automatically on the next scheduled
                run once access is granted.</p>
                <p>Best,<br>The Auto Archiver team</p>
            </body>
            </html>
            """,
            subtype=MessageType.html,
        )
        await fastmail.send_message(message)
        logger.debug(
            f"[CRON] Email sent to {email} about {len(sheets_to_notify)} "
            f"sheet(s) with permission issues."
        )


# TODO: on exception should logerror but also prometheus counter
DELETE_WINDOW = (
    get_settings().DELETE_SCHEDULED_ARCHIVES_CHECK_EVERY_N_DAYS * 24 * 60 * 60
)


@repeat_every(
    seconds=DELETE_WINDOW,
    wait_first=180,
    on_exception=increase_exceptions_counter,
)
async def notify_about_expired_archives():
    notify_from = datetime.datetime.now() + datetime.timedelta(
        days=get_settings().DELETE_SCHEDULED_ARCHIVES_CHECK_EVERY_N_DAYS
    )
    async with get_db_async() as db:
        scheduled_deletions = await crud.find_by_store_until(db, notify_from)

    user_archives = defaultdict(list)
    for archive in scheduled_deletions:
        user_archives[archive.author_id].append(archive)

    if user_archives:
        fastmail = FastMail(get_settings().mail_config)
        # notify users
        for email in user_archives:
            list_of_archives = "\n".join(
                [
                    f"{a.url}, {a.id}, {a.store_until.isoformat()}<br/>"
                    for a in user_archives[email]
                ]
            )
            # TODO: how can users download them in bulk?
            message = MessageSchema(
                subject="Auto Archiver: Archives Scheduled for Deletion",
                recipients=[email],
                body=f"""
                <html>
                <body>
                    <p>Hi {email},</p>
                    <p>Some of your archives will be deleted in the next {get_settings().DELETE_SCHEDULED_ARCHIVES_CHECK_EVERY_N_DAYS} days, as they are reaching their expiration date according to our retention policy for their groups.</p>
                    <p>If you want to preserve any, make sure to download them now.</p>
                    <p>Here is a CSV list of URLs:</p>
                    <code>
                    url,archive_id,time_of_deletion<br/>
                    {list_of_archives}
                    </code>
                    <p>Best,<br>The Auto Archiver team</p>
                </body>
                </html>
                """,
                subtype=MessageType.html,
            )
            await fastmail.send_message(message)
            logger.debug(
                f"[CRON] Email sent to {email} about {len(user_archives[email])} scheduled archives deletion."
            )

    # now schedule the deletion event
    asyncio.create_task(delete_expired_archives())


@repeat_every(
    max_repetitions=1,
    wait_first=10,
    seconds=0,
    on_exception=increase_exceptions_counter,
)
async def delete_expired_archives():
    async with get_db_async() as db:
        count_deleted = await crud.soft_delete_expired_archives(db)
        if count_deleted:
            logger.debug(f"[CRON] Deleted {count_deleted} archives.")


@repeat_every(
    seconds=86400, wait_first=150, on_exception=increase_exceptions_counter
)
async def delete_stale_sheets():
    STALE_DAYS = get_settings().DELETE_STALE_SHEETS_DAYS
    logger.debug(f"[CRON] Deleting stale sheets older than {STALE_DAYS} days.")
    async with get_db_async() as db:
        user_sheets = await crud.delete_stale_sheets(db, STALE_DAYS)

    if not user_sheets:
        return

    fastmail = FastMail(get_settings().mail_config)
    # notify users
    for email in user_sheets:
        list_of_sheets = "\n".join(
            [
                f'<li><a href="https://docs.google.com/spreadsheets/d/{s.id}">{s.name}</a></li>'
                for s in user_sheets[email]
            ]
        )
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
            subtype=MessageType.html,
        )
        await fastmail.send_message(message)
        logger.debug(
            f"[CRON] Email sent to {email} about stale sheets deletion."
        )


# @repeat_at
async def generate_users_export_csv():
    # TODO: implement a cronjob that regularly requested user data to a CSV file
    # see https://colab.research.google.com/drive/1QDbo3QXHPBdiTuANlA1AWVvN-rqxuCPa?authuser=0#scrollTo=4nPXeSdK8RBT
    pass
