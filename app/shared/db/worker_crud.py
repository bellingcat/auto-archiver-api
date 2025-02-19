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


def create_archive(db: Session, archive: schemas.ArchiveCreate, tags: list[models.Tag], urls: list[models.ArchiveUrl]) -> models.Archive:
    db_archive = models.Archive(id=archive.id, url=archive.url, result=archive.result, public=archive.public, author_id=archive.author_id, group_id=archive.group_id, sheet_id=archive.sheet_id, store_until=archive.store_until)
    db_archive.tags = tags
    db_archive.urls = urls
    db.add(db_archive)
    db.commit()
    db.refresh(db_archive)
    return db_archive


def store_archived_url(db: Session, archive: schemas.ArchiveCreate) -> models.Archive:
    # create and load user, tags, if needed
    create_or_get_user(db, archive.author_id)
    db_tags = [create_tag(db, tag) for tag in (archive.tags or [])]
    # insert everything
    db_archive = create_archive(db, archive=archive, tags=db_tags, urls=archive.urls)
    return db_archive
