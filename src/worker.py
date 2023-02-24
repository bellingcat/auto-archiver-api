
import os

from celery import Celery
from dataclasses import asdict
from auto_archiver import Config, ArchivingOrchestrator, Metadata
from loguru import logger

from db import crud, models, schemas
from db.database import engine, SessionLocal
from contextlib import contextmanager
import json

# models.Base.metadata.create_all(bind=engine)

celery = Celery(__name__)
celery.conf.broker_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379")
celery.conf.result_backend = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379")

@contextmanager
def get_db():
    session = SessionLocal()
    try: yield session
    finally: session.close()

config = Config()
config.parse(use_cli=False, yaml_config_filename="secrets/orchestration.yaml")
orchestrator = None

@celery.task(name="create_archive_task", bind=True)
def create_archive_task(self, url: str , user_email:str=""):
    global orchestrator
    if not orchestrator: orchestrator = ArchivingOrchestrator(config)
    result = orchestrator.feed_item(Metadata().set_url(url)).to_json()
    # result = orchestrator.feed_item(Metadata().set_url(url))
    with get_db() as session:
        db_task = crud.create_task(session, task=schemas.TaskCreate(id=self.request.id, url=url, author=user_email, result=json.loads(result)))
        logger.debug(f"Added {db_task.id=} to database on {db_task.created_at}")
    return result
