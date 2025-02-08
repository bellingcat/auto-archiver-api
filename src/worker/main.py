
import traceback, datetime
from typing import List

from celery.signals import task_failure
from auto_archiver import Config, ArchivingOrchestrator, Metadata
from auto_archiver.core import Media
from loguru import logger

from db import crud, schemas, models
from db.database import get_db
from shared.task_messaging import get_celery, get_redis
from shared.settings import get_settings
import json
from sqlalchemy import exc
from core.logging import log_error


settings = get_settings()

celery = get_celery("worker")
Redis = get_redis()

USER_GROUPS_FILENAME = settings.USER_GROUPS_FILENAME

# TODO: after release, as it requires updating past entries with sheet_id where tag is used, drop tags


@celery.task(name="create_archive_task", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 0})
def create_archive_task(self, archive_json: str):
    logger.info(archive_json)
    archive = schemas.ArchiveCreate.model_validate_json(archive_json)

    # call auto-archiver
    orchestrator = load_orchestrator(archive.group_id)
    result = orchestrator.feed_item(Metadata().set_url(archive.url))
    assert result, f"UNABLE TO archive: {archive.url}"

    # prepare and insert in DB
    archive.id = self.request.id
    archive.urls = get_all_urls(result)
    archive.result = json.loads(result.to_json())
    insert_result_into_db(archive)

    return archive.result


@celery.task(name="create_sheet_task", bind=True)
def create_sheet_task(self, sheet_json: str):
    sheet = schemas.SubmitSheet.model_validate_json(sheet_json)
    logger.info(f"SHEET START {sheet=}")

    orchestrator = load_orchestrator(sheet.group_id, True, {"configurations": {"gsheet_feeder": {"sheet_id": sheet.sheet_id}}})

    stats = {"archived": 0, "failed": 0, "errors": []}
    for result in orchestrator.feed():
        try:
            assert result, f"UNABLE TO archive: {result.get_url()}"
            archive = schemas.ArchiveCreate(
                author_id=sheet.author_id,
                url=result.get_url(),
                group_id=sheet.group_id,
                tags=sheet.tags,
                id=models.generate_uuid(),
                result=json.loads(result.to_json()),
                sheet_id=sheet.sheet_id,
                urls=get_all_urls(result)
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

    if stats["archived"] > 0:
        with get_db() as session:
            crud.update_sheet_last_url_archived_at(session, sheet.sheet_id)

    logger.info(f"SHEET DONE {sheet=}")
    # TODO: is this used anywhere? maybe drop it
    return schemas.CelerySheetTask(success=True, sheet_id=sheet.sheet_id, time=datetime.datetime.now().isoformat(), stats=stats).model_dump()


def load_orchestrator(group_id: str, orchestrator_for_sheet: bool = False, overwrite_configs: dict = {}) -> ArchivingOrchestrator:
    with get_db() as session:
        group = crud.get_group(session, group_id)
        if orchestrator_for_sheet:
            orchestrator_fn = group.orchestrator_sheet
        else:
            orchestrator_fn = crud.get_group(session, group_id).orchestrator
        assert orchestrator_fn, f"no orchestrator found for {group_id}"

    config = Config()
    config.parse(use_cli=False, yaml_config_filename=orchestrator_fn, overwrite_configs=overwrite_configs)
    return ArchivingOrchestrator(config)


def insert_result_into_db(archive: schemas.ArchiveCreate) -> str:
    with get_db() as session:
        db_task = crud.insert_result_into_db(session, archive)
        logger.debug(f"[ARCHIVE STORED] {db_task.author_id} {db_task.url}")
        return db_task.id


# TODO: this should live within the auto-archiver
def get_all_urls(result: Metadata) -> List[models.ArchiveUrl]:
    db_urls = []
    for m in result.media:
        for i, url in enumerate(m.urls): db_urls.append(models.ArchiveUrl(url=url, key=m.get("id", f"media_{i}")))
        for k, prop in m.properties.items():
            if prop_converted := convert_if_media(prop):
                for i, url in enumerate(prop_converted.urls): db_urls.append(models.ArchiveUrl(url=url, key=prop_converted.get("id", f"{k}_{i}")))
            if isinstance(prop, list):
                for i, prop_media in enumerate(prop):
                    if prop_media := convert_if_media(prop_media):
                        for j, url in enumerate(prop_media.urls):
                            db_urls.append(models.ArchiveUrl(url=url, key=prop_media.get("id", f"{k}{prop_media.key}_{i}.{j}")))
    return db_urls


# TODO: this should live within the auto-archiver??
def convert_if_media(media):
    if isinstance(media, Media): return media
    elif isinstance(media, dict):
        try: return Media.from_dict(media)
        except Exception as e:
            logger.debug(f"error parsing {media} : {e}")
    return False


def redis_publish_exception(exception, task_name, traceback: str = ""):
    REDIS_EXCEPTIONS_CHANNEL = settings.REDIS_EXCEPTIONS_CHANNEL
    try:
        exception_data = {"task": task_name, "type": exception.__class__.__name__, "exception": exception, "traceback": traceback}
        Redis.publish(REDIS_EXCEPTIONS_CHANNEL, json.dumps(exception_data, default=str))
    except Exception as e:
        log_error(e, f"[CRITICAL] Could not publish to {REDIS_EXCEPTIONS_CHANNEL}")


@task_failure.connect(sender=create_sheet_task)
@task_failure.connect(sender=create_archive_task)
def task_failure_notifier(sender, **kwargs):
    # automatically capture exceptions in the worker tasks
    logger.warning(f"⚠️  worker task failed: {sender.name}")
    traceback_msg = "\n".join(traceback.format_list(traceback.extract_tb(kwargs['traceback'])))
    log_error(kwargs['exception'], traceback_msg, f"task_failure: {sender.name}")
    redis_publish_exception(kwargs['exception'], sender.name, traceback_msg)
