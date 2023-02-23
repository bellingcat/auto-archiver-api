import os
import time

from celery import Celery
from dataclasses import asdict
from auto_archiver import Config, ArchivingOrchestrator, Metadata


celery = Celery(__name__)
celery.conf.broker_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379")
celery.conf.result_backend = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379")

@celery.task(name="create_task")
def create_task(task_type):
    print("DEV MODE")
    time.sleep(int(task_type) * 10)
    return True


# from configs.v2config import ConfigV2
# from auto_archiver import ArchivingOrchestrator
config = Config()
config.parse(use_cli=False, yaml_config_filename="orchestration.yaml")
orchestrator = None

@celery.task(name="create_archive_task")
def create_archive_task(url: str , user_email:str=""):
    global orchestrator
    if not orchestrator: orchestrator = ArchivingOrchestrator(config)
    return orchestrator.feed_item(Metadata().set_url(url)).to_json()
    #TODO: associate user with url (?)
