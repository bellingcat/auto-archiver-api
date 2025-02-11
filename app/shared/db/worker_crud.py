from sqlalchemy.orm import Session
from datetime import datetime

from app.shared.db import models
from app.shared import schemas

# TODO: isolate database operations away from worker and into WEB
# ONLY WORKER
def update_sheet_last_url_archived_at(db: Session, sheet_id: str):
    db_sheet = db.query(models.Sheet).filter(models.Sheet.id == sheet_id).first()
    if db_sheet:
        db_sheet.last_url_archived_at = datetime.now()
        db.commit()
        return True
    return False


# ONLY WORKER and INTEROP

def get_group(db: Session, group_name: str) -> models.Group:
    return db.query(models.Group).filter(models.Group.id == group_name).first()

def create_or_get_user(db: Session, author_id: str) -> models.User:
    if type(author_id) == str: author_id = author_id.lower()
    db_user = db.query(models.User).filter(models.User.email == author_id).first()
    if not db_user:
        db_user = models.User(email=author_id)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
    return db_user


def create_tag(db: Session, tag: str) -> models.Tag:
    db_tag = db.query(models.Tag).filter(models.Tag.id == tag).first()
    if not db_tag:
        db_tag = models.Tag(id=tag)
        db.add(db_tag)
        db.commit()
        db.refresh(db_tag)
    return db_tag


def create_task(db: Session, task: schemas.ArchiveCreate, tags: list[models.Tag], urls: list[models.ArchiveUrl]) -> models.Archive:
	# TODO: rename task to archive
    db_task = models.Archive(id=task.id, url=task.url, result=task.result, public=task.public, author_id=task.author_id, group_id=task.group_id, sheet_id=task.sheet_id, store_until=task.store_until)
    db_task.tags = tags
    db_task.urls = urls
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


def store_archived_url(db: Session, archive: schemas.ArchiveCreate) -> models.Archive:
    # create and load user, tags, if needed
    create_or_get_user(db, archive.author_id)
    db_tags = [create_tag(db, tag) for tag in archive.tags]
    # insert everything
    db_task = create_task(db, task=archive, tags=db_tags, urls=archive.urls)
    return db_task
