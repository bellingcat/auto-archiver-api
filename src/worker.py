
import os, re

from celery import Celery
from auto_archiver import Config, ArchivingOrchestrator, Metadata
# from auto_archiver.enrichers import ScreenshotEnricher
from loguru import logger

from db import crud, schemas
from db.database import engine, SessionLocal
from contextlib import contextmanager
import json

celery = Celery(__name__)
celery.conf.broker_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379")
celery.conf.result_backend = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379")

@contextmanager
def get_db():
    session = SessionLocal()
    try: yield session
    finally: session.close()

config_default = Config()
config_default.parse(use_cli=False, yaml_config_filename=os.environ.get("ORCHESTRATION_CONFIG_DEFAULT", "secrets/orchestration.yaml"))

config_bcat = None
if (config_bcat_file := os.environ.get("ORCHESTRATION_CONFIG_BELLINGCAT")):
    config_bcat = Config()
    config_bcat.parse(use_cli=False, yaml_config_filename=config_bcat_file)

orchestrators = {"bellingcat": None, "default": None}

@celery.task(name="create_archive_task", bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 5})
def create_archive_task(self, url: str, email:str=""):
    orchestrator = choose_orchestrator(email)
    result = orchestrator.feed_item(Metadata().set_url(url)).to_json()
    with get_db() as session:
        db_task = crud.create_task(session, task=schemas.TaskCreate(id=self.request.id, url=url, author=email, result=json.loads(result)))
        logger.debug(f"Added {db_task.id=} to database on {db_task.created_at}")
    return result


def choose_orchestrator(email):
    global orchestrators, config_bcat
    if re.match(r'^[\w.]+@bellingcat\.com$', email) and config_bcat:
        logger.debug("Using bellingcat config for orchestration")
        if not orchestrators["bellingcat"]:
            orchestrators["bellingcat"] = ArchivingOrchestrator(config_bcat)
        return orchestrators["bellingcat"]
    logger.debug("Using default config for orchestration")
    if not orchestrators["default"]: 
        orchestrators["default"] = ArchivingOrchestrator(config_default)
    return orchestrators["default"]