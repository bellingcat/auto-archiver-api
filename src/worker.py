
import os, traceback, yaml, datetime
from typing import List, Set

from celery import Celery
from celery.signals import task_failure
from auto_archiver import Config, ArchivingOrchestrator, Metadata
from auto_archiver.core import Media
from loguru import logger

from db import crud, schemas, models
from db.database import SessionLocal
from contextlib import contextmanager
import json

celery = Celery(__name__)
celery.conf.broker_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379")
celery.conf.result_backend = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379")
USER_GROUPS_FILENAME = os.environ.get("USER_GROUPS_FILENAME", "user-groups.yaml")


@contextmanager
def get_db():
    session = SessionLocal()
    try: yield session
    finally: session.close()


@celery.task(name="create_archive_task", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 5})
def create_archive_task(self, archive_json: str):
    archive = schemas.ArchiveCreate.parse_raw(archive_json)

    if (em := is_group_invalid_for_user(archive.public, archive.group_id, archive.author_id)): return {"error": em}

    url = archive.url
    logger.info(f"{url=} {archive=}")
    orchestrator = choose_orchestrator(archive.group_id, archive.author_id)
    result = orchestrator.feed_item(Metadata().set_url(url))

    try:
        insert_result_into_db(result, archive.tags, archive.public, archive.group_id, archive.author_id, self.request.id)
    except Exception as e:
        logger.error(e)
        logger.error(traceback.format_exc())
        return {"error": e}
    return result.to_json()


@celery.task(name="create_sheet_task", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 0})
def create_sheet_task(self, sheet_json: str):
    sheet = schemas.SubmitSheet.parse_raw(sheet_json)
    sheet.tags.add("gsheet")
    logger.info(f"SHEET START {sheet=}")

    if (em := is_group_invalid_for_user(sheet.public, sheet.group_id, sheet.author_id)): return {"error": em}

    config = Config()
    # TODO: use choose_orchestrator and overwrite the feeder
    config.parse(use_cli=False, yaml_config_filename="secrets/orchestration-sheet.yaml", overwrite_configs={"configurations": {"gsheet_feeder": {"sheet": sheet.sheet_name, "sheet_id": sheet.sheet_id, "header": sheet.header}}})
    orchestrator = ArchivingOrchestrator(config)

    stats = {"archived": 0, "failed": 0, "errors": []}
    for result in orchestrator.feed():
        try:
            insert_result_into_db(result, sheet.tags, sheet.public, sheet.group_id, sheet.author_id, models.generate_uuid())
            stats["archived"] += 1
        except Exception as e:
            logger.error(e)
            logger.error(traceback.format_exc())
            stats["failed"] += 1
            stats["errors"].append(e)

    logger.info(f"SHEET DONE {sheet=}")
    return {"success": True, "sheet": sheet.sheet_name, "sheet_id": sheet.sheet_id, "time": datetime.datetime.now().isoformat(), **stats}


@task_failure.connect(sender=create_sheet_task)
@task_failure.connect(sender=create_archive_task)
def task_failure_notifier(sender=None, **kwargs):
    logger.warning("😅 From task_failure_notifier ==> Task failed successfully! ")
    logger.error(kwargs['exception'])
    logger.error(kwargs['traceback'])
    logger.error("\n".join(traceback.format_list(traceback.extract_tb(kwargs['traceback']))))


def choose_orchestrator(group, email):
    global ORCHESTRATORS
    if group not in ORCHESTRATORS: group = get_user_first_group(email)
    assert group in ORCHESTRATORS, f"{group=} not in configurations"
    logger.info(f"CHOOSE Orchestrator for {group=}, {email=}")
    return ArchivingOrchestrator(ORCHESTRATORS.get(group))


def read_user_groups():
    # read yaml safely
    with open(USER_GROUPS_FILENAME) as inf:
        try:
            return yaml.safe_load(inf)
        except yaml.YAMLError as e:
            logger.error(f"could not open user groups filename {USER_GROUPS_FILENAME}: {e}")
            raise e


def get_user_first_group(email):
    user_groups_yaml = read_user_groups()
    groups = user_groups_yaml.get("users", {}).get(email, [])
    if groups != None and len(groups): return groups[0]
    return "default"


def load_orchestrators():
    global ORCHESTRATORS
    ORCHESTRATORS = {}
    """
    reads the orchestrators key in the config file to load different orchestrators for different groups
    """
    user_groups_yaml = read_user_groups()

    orchestrators_config = user_groups_yaml.get("orchestrators", {})
    assert len(orchestrators_config), f"No orchestrators key found in {USER_GROUPS_FILENAME}. please see the example file"
    assert "default" in orchestrators_config, "please include a 'default' orchestrator to be used when the user has no group"
    logger.debug(f"Found {len(orchestrators_config)} group orchestrators.")

    for group, config_filename in orchestrators_config.items():
        config = Config()
        config.parse(use_cli=False, yaml_config_filename=config_filename)
        ORCHESTRATORS[group] = config
    return ORCHESTRATORS


def is_group_invalid_for_user(public: bool, group_id: str, author_id: str):
    """
    ensures that, if a group is specified, the user belongs to it.
    if public is true the requirement is not needed
    returns an error message if invalid, or False if all is good.
    """
    if not public and group_id and len(group_id) > 0:
        # ensure group is valid for user
        with get_db() as session:
            if not crud.is_user_in_group(session, group_id, author_id):
                logger.error(em := f"User {author_id} is not part of {group_id}, no permission")
                return em
    return False


def insert_result_into_db(result: Metadata, tags: Set[str], public: bool, group_id: str, author_id: str, task_id: str) -> str:
    logger.info(f"INSERTING {public=} {group_id=} {author_id=} {tags=} into {task_id}")
    assert result, f"UNABLE TO archive: {result.get_url()}"
    with get_db() as session:
        # urls are created by get_all_urls
        # create author_id if needed
        crud.get_user(session, author_id)
        # create DB TAGs if needed
        db_tags = [crud.create_tag(session, tag) for tag in tags]
        # insert archive
        db_task = crud.create_task(session, task=schemas.ArchiveCreate(id=task_id, url=result.get_url(), result=json.loads(result.to_json()), public=public, author_id=author_id, group_id=group_id), tags=db_tags, urls=get_all_urls(result))
        logger.debug(f"Added {db_task.id=} to database on {db_task.created_at} ({db_task.author_id})")
        return db_task.id


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

def convert_if_media(media):
    if isinstance(media, Media): return media
    elif isinstance(media, dict):
        try: return Media.from_dict(media)
        except Exception as e:
            logger.debug(e)
    return False


# INIT
ORCHESTRATORS = {}
load_orchestrators()
