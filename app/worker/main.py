import datetime
import json
import traceback

from auto_archiver.core.orchestrator import ArchivingOrchestrator
from celery.signals import task_failure
from sqlalchemy import exc

from app.shared import business_logic, constants, schemas
from app.shared.db import models, worker_crud
from app.shared.db.database import get_db
from app.shared.log import log_error
from app.shared.settings import get_settings
from app.shared.task_messaging import get_celery, get_redis
from app.shared.utils.misc import get_all_urls
from app.shared.utils.sheets import get_sheet_access_error
from app.worker.worker_log import logger, setup_celery_logger


# Time limits for tasks (in seconds)
# soft_time_limit raises SoftTimeLimitExceeded inside the task so it can clean up
# time_limit hard-kills the task if soft limit didn't work
SINGLE_URL_SOFT_TIME_LIMIT = 30 * 60  # 30 minutes
SINGLE_URL_HARD_TIME_LIMIT = 35 * 60  # 35 minutes
SHEET_SOFT_TIME_LIMIT = 6 * 60 * 60  # 6 hours
SHEET_HARD_TIME_LIMIT = 6.5 * 60 * 60  # 6.5 hours

settings = get_settings()

celery = get_celery("worker")
Redis = get_redis()

USER_GROUPS_FILENAME = settings.USER_GROUPS_FILENAME

setup_celery_logger(celery)
AA_LOGGER_ID = None


# TODO: after release, as it requires updating past entries with sheet_id where tag
#  is used, drop tags
@celery.task(
    name="create_archive_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 1},
    soft_time_limit=SINGLE_URL_SOFT_TIME_LIMIT,
    time_limit=SINGLE_URL_HARD_TIME_LIMIT,
    acks_late=True,
    reject_on_worker_lost=True,
)
def create_archive_task(self, archive_json: str):
    global AA_LOGGER_ID
    archive = schemas.ArchiveCreate.model_validate_json(archive_json)

    # call auto-archiver
    args = get_orchestrator_args(archive.group_id, False, [archive.url])
    result = None
    orchestrator = None
    try:
        orchestrator = ArchivingOrchestrator()
        orchestrator.logger_id = AA_LOGGER_ID  # ensure single logger
        orchestrator.setup(args)
        AA_LOGGER_ID = orchestrator.logger_id
        for orch_res in orchestrator.feed():
            result = orch_res
    except SystemExit as e:
        log_error(e, "create_archive_task: SystemExit from AA")
    except Exception as e:
        log_error(e, "create_archive_task")
        raise e
    finally:
        cleanup_orchestrator(orchestrator)
    assert result, f"UNABLE TO archive: {archive.url}"

    # prepare and insert in DB
    archive.store_until = get_store_until(archive.group_id)
    archive.id = self.request.id
    archive.urls = get_all_urls(result)
    archive.result = json.loads(result.to_json())
    insert_result_into_db(archive)

    return archive.result


@celery.task(
    name="create_sheet_task",
    bind=True,
    soft_time_limit=SHEET_SOFT_TIME_LIMIT,
    time_limit=SHEET_HARD_TIME_LIMIT,
    acks_late=True,
    reject_on_worker_lost=True,
)
def create_sheet_task(self, sheet_json: str):
    global AA_LOGGER_ID
    sheet = schemas.SubmitSheet.model_validate_json(sheet_json)
    queue_name = (create_sheet_task.request.delivery_info or {}).get(
        "routing_key", "unknown"
    )
    logger.info(f"[queue={queue_name}] SHEET START {sheet=}")

    # Early check: does the service account have write access to the sheet?
    with get_db() as session:
        group = worker_crud.get_group(session, sheet.group_id)
        if group and group.orchestrator_sheet:
            access_error = get_sheet_access_error(
                group.orchestrator_sheet,
                group.service_account_email,
                sheet.sheet_id,
            )
            if access_error:
                logger.warning(
                    f"SHEET SKIPPED {sheet.sheet_id}: {access_error}"
                )
                return schemas.CelerySheetTask(
                    success=False,
                    sheet_id=sheet.sheet_id,
                    time=datetime.datetime.now().isoformat(),
                    stats={
                        "archived": 0,
                        "failed": 0,
                        "errors": [access_error],
                    },
                ).model_dump()

    args = get_orchestrator_args(
        sheet.group_id, True, [constants.SHEET_ID, sheet.sheet_id]
    )
    orchestrator = ArchivingOrchestrator()
    orchestrator.logger_id = AA_LOGGER_ID  # ensure single logger
    orchestrator.setup(args)
    AA_LOGGER_ID = orchestrator.logger_id

    stats = {"archived": 0, "failed": 0, "errors": []}
    try:
        for result in orchestrator.feed():
            try:
                assert result, f"ERROR archiving URL for sheet {sheet.sheet_id}"
                archive = schemas.ArchiveCreate(
                    author_id=sheet.author_id,
                    url=result.get_url(),
                    group_id=sheet.group_id,
                    tags=sheet.tags,
                    id=models.generate_uuid(),
                    result=json.loads(result.to_json()),
                    sheet_id=sheet.sheet_id,
                    urls=get_all_urls(result),
                    store_until=get_store_until(sheet.group_id),
                )
                insert_result_into_db(archive)
                stats["archived"] += 1
            except exc.IntegrityError as e:
                logger.warning(f"cached result detected: {e}")
            except Exception as e:
                log_error(e, extra=f"{self.name}: {sheet_json}")
                redis_publish_exception(e, self.name, traceback.format_exc())
                stats["failed"] += 1
                stats["errors"].append(str(e))

    except SystemExit as e:
        log_error(e, "create_sheet_task: SystemExit from AA")
    finally:
        cleanup_orchestrator(orchestrator)

    if stats["archived"] > 0:
        with get_db() as session:
            worker_crud.update_sheet_last_url_archived_at(
                session, sheet.sheet_id
            )

    logger.info(f"SHEET DONE {sheet=}")
    # TODO: is this used anywhere? maybe drop it
    return schemas.CelerySheetTask(
        success=True,
        sheet_id=sheet.sheet_id,
        time=datetime.datetime.now().isoformat(),
        stats=stats,
    ).model_dump()


def cleanup_orchestrator(orchestrator):
    """
    Clean up orchestrator resources to prevent leaks between tasks.
    """
    if orchestrator is None:
        return
    try:
        if hasattr(orchestrator, "extractors"):
            orchestrator.cleanup()
    except Exception as e:
        logger.warning(f"Error cleaning up orchestrator: {e}")


def get_orchestrator_args(
    group_id: str, orchestrator_for_sheet: bool, cli_args: list = None
) -> list:
    cli_args.append("--logging.enabled=false")

    aa_configs = []
    with get_db() as session:
        group = worker_crud.get_group(session, group_id)
        if orchestrator_for_sheet:
            orchestrator_fn = group.orchestrator_sheet
        else:
            orchestrator_fn = worker_crud.get_group(
                session, group_id
            ).orchestrator
        assert orchestrator_fn, f"no orchestrator found for {group_id}"
    aa_configs.extend(["--config", orchestrator_fn])
    aa_configs.extend(cli_args)
    return aa_configs


def insert_result_into_db(archive: schemas.ArchiveCreate) -> str:
    with get_db() as session:
        db_archive = worker_crud.store_archived_url(session, archive)
        logger.debug(
            f"[ARCHIVE STORED] {db_archive.author_id} {db_archive.url}"
        )
        return db_archive.id


def get_store_until(group_id: str) -> datetime.datetime:
    with get_db() as session:
        return business_logic.get_store_archive_until(session, group_id)


def redis_publish_exception(exception, task_name, trace_back: str = ""):
    REDIS_EXCEPTIONS_CHANNEL = settings.REDIS_EXCEPTIONS_CHANNEL
    try:
        exception_data = {
            "task": task_name,
            "type": exception.__class__.__name__,
            "exception": exception,
            "traceback": trace_back,
        }
        Redis.publish(
            REDIS_EXCEPTIONS_CHANNEL, json.dumps(exception_data, default=str)
        )
    except Exception as e:
        log_error(
            e, f"[CRITICAL] Could not publish to {REDIS_EXCEPTIONS_CHANNEL}"
        )


@task_failure.connect(sender=create_sheet_task)
@task_failure.connect(sender=create_archive_task)
def task_failure_notifier(sender, **kwargs):
    # automatically capture exceptions in the worker tasks
    logger.warning(f"⚠️  worker task failed: {sender.name}")
    traceback_msg = "\n".join(
        traceback.format_list(traceback.extract_tb(kwargs["traceback"]))
    )
    log_error(
        kwargs["exception"], traceback_msg, f"task_failure: {sender.name}"
    )
    redis_publish_exception(kwargs["exception"], sender.name, traceback_msg)
