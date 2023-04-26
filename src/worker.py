
import os, re, traceback, yaml

from celery import Celery, states
from celery.exceptions import Ignore
from celery.signals import task_failure
from auto_archiver import Config, ArchivingOrchestrator, Metadata
# from auto_archiver.enrichers import ScreenshotEnricher
from loguru import logger

from db import crud, schemas, models
from db.database import engine, SessionLocal
from contextlib import contextmanager
import json

celery = Celery(__name__)
celery.conf.broker_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379")
celery.conf.result_backend = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379")
USER_GROUPS_FILENAME=os.environ.get("USER_GROUPS_FILENAME", "user-groups.yaml")


@contextmanager
def get_db():
    session = SessionLocal()
    try: yield session
    finally: session.close()

@celery.task(name="create_archive_task", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 5}) 
def create_archive_task(self, archive_json: str):
    
    archive = schemas.ArchiveCreate.parse_raw(archive_json)
    if not archive.public and archive.group_id and len(archive.group_id) > 0:
        # ensure group is valid for user
        with get_db() as session:
            db_group = crud.get_group_for_user(session, archive.group_id, archive.author_id)
            if not db_group:
                logger.error(em := f"User {archive.author_id} is not part of {archive.group_id}, no permission")
                return {"error": em}

    url = archive.url
    logger.info(f"{url=}")
    logger.info(f"{archive=}")
    orchestrator = choose_orchestrator(archive.group_id, archive.author_id)
    result = orchestrator.feed_item(Metadata().set_url(url))
    if not result:
        logger.error(f"UNABLE TO archive: {url}")
        return {"error": "unable to archive"}

    result_json = result.to_json()
    with get_db() as session:
        # create DB URLs
        db_urls = [models.ArchiveUrl(url=url, key=m.get("id", f"media_{i}")) for i, m in enumerate(result.media) for url in m.urls]
        # create DB TAGs if needed
        db_tags = [crud.create_tag(session, tag) for tag in archive.tags]
        # insert archive
        db_task = crud.create_task(session, task=schemas.ArchiveCreate(id=self.request.id, url=url, result=json.loads(result_json), public=archive.public, author_id=archive.author_id, group_id=archive.group_id), tags=db_tags, urls=db_urls)
        logger.debug(f"Added {db_task.id=} to database on {db_task.created_at}")
    return result_json

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
    if len(groups): return groups[0]
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


## INIT

ORCHESTRATORS = {}
load_orchestrators()