from functools import cache
from sqlalchemy.orm import Session, load_only
from sqlalchemy import Column, or_
from loguru import logger
from datetime import datetime

from security import ALLOW_ANY_EMAIL
from . import models, schemas
import yaml, os

DOMAIN_GROUPS = {}
DOMAIN_GROUPS_LOADED = False

# --------------- TASK = Archive


def get_task(db: Session, task_id: str, email: str):
    email = email.lower()
    query = base_query(db).filter(models.Archive.id == task_id)
    if email != ALLOW_ANY_EMAIL:
        groups = get_user_groups(db, email)
        query = query.filter(or_(models.Archive.public == True, models.Archive.author_id == email, models.Archive.group_id.in_(groups)))
    return query.first()


def search_tasks_by_url(db: Session, url: str, email: str, skip: int = 0, limit: int = 100, archived_after: datetime = None, archived_before: datetime = None, absolute_search: bool = False):
    # searches for partial URLs, if email is * no ownership filtering happens
    query = base_query(db)
    if email != ALLOW_ANY_EMAIL:
        email = email.lower()
        groups = get_user_groups(db, email)
        query = query.filter(or_(models.Archive.public == True, models.Archive.author_id == email, models.Archive.group_id.in_(groups)))
    if absolute_search:
        query = query.filter(models.Archive.url == url)
    else:
        query = query.filter(models.Archive.url.like(f'%{url}%'))
    if archived_after:
        query = query.filter(models.Archive.created_at >= archived_after)
    if archived_before:
        query = query.filter(models.Archive.created_at <= archived_before)
    return query.offset(skip).limit(limit).all()


def search_tasks_by_email(db: Session, email: str, skip: int = 0, limit: int = 100):
    email = email.lower()
    return base_query(db).filter(models.Archive.author.has(email=email)).offset(skip).limit(limit).all()


def create_task(db: Session, task: schemas.ArchiveCreate, tags: list[models.Tag], urls: list[models.ArchiveUrl]):
    db_task = models.Archive(id=task.id, url=task.url, result=task.result, public=task.public, author_id=task.author_id, group_id=task.group_id)
    db_task.tags = tags
    db_task.urls = urls
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


def soft_delete_task(db: Session, task_id: str, email: str) -> bool:
    # TODO: implement hard-delete with cronjob that deletes from S3
    db_task = db.query(models.Archive).filter(models.Archive.id == task_id, models.Archive.author_id == email, models.Archive.deleted == False).first()
    if db_task:
        db_task.deleted = True
        db.commit()
    return db_task is not None


def base_query(db: Session):
    # allow only some fields to be returned, for example author should remain hidden
    return db.query(models.Archive)\
        .options(load_only(models.Archive.id, models.Archive.created_at, models.Archive.url, models.Archive.result))\
        .filter(models.Archive.deleted == False)

# --------------- TAG


def create_tag(db: Session, tag: str):
    db_tag = db.query(models.Tag).filter(models.Tag.id == tag).first()
    if not db_tag:
        db_tag = models.Tag(id=tag)
        db.add(db_tag)
        db.commit()
        db.refresh(db_tag)
    return db_tag


def search_tags(db: Session, tag: str, skip: int = 0, limit: int = 100):
    return db.query(models.Tag).filter(models.Tag.url.like(f'%{tag}%')).offset(skip).limit(limit).all()


def is_user_in_group(db: Session, group_name: str, email: str) -> models.Group:
    return len(group_name) and len(email) and group_name in get_user_groups(db, email)


def get_user_groups(db: Session, email: str):
    email = email.lower()
    global DOMAIN_GROUPS, DOMAIN_GROUPS_LOADED
    if not DOMAIN_GROUPS_LOADED: upsert_user_groups(db)
    # given an email retrieves the user groups from the DB and then the email-domain groups from a global variable
    groups = db.query(models.association_table_user_groups).filter_by(user_id=email).with_entities(Column("group_id")).all()
    user_level_groups = [g[0] for g in groups]
    domain_level_groups = DOMAIN_GROUPS.get(email.split('@')[1], [])
    logger.success(f"EMAIL {email} has {user_level_groups=} and {domain_level_groups=}")
    return list(set(user_level_groups) | set(domain_level_groups))


# --------------- INIT User-Groups


def get_user(db: Session, author_id: str):
    if type(author_id)==str: author_id = author_id.lower()
    db_user = db.query(models.User).filter(models.User.email == author_id).first()
    if not db_user:
        db_user = models.User(email=author_id)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
    return db_user


@cache
def get_group(db: Session, group_name: str) -> models.Group:
    db_group = db.query(models.Group).filter(models.Group.id == group_name).first()
    if db_group is None:
        db_group = models.Group(id=group_name)
        db.add(db_group)
    return db_group


def upsert_user_groups(db: Session):
    global DOMAIN_GROUPS, DOMAIN_GROUPS_LOADED
    """
    reads the user_groups yaml file and inserts any new users, groups, 
    along with new participation of users in groups
    """
    logger.debug("Updating user-groups configuration.")
    filename = os.environ.get("USER_GROUPS_FILENAME", "user-groups.yaml")

    # read yaml safely
    with open(filename) as inf:
        try:
            user_groups_yaml = yaml.safe_load(inf)
        except yaml.YAMLError as e:
            logger.error(f"could not open user groups filename {filename}: {e}")
            raise e
    # updating domain->groups access
    DOMAIN_GROUPS = user_groups_yaml.get("domains", {})

    # upserting in DB
    user_groups = user_groups_yaml.get("users", {})
    logger.debug(f"Found {len(user_groups)} users.")
    db.query(models.association_table_user_groups).delete()

    for user_email, groups in user_groups.items():
        user_email = user_email.lower()
        assert '@' in user_email, f'Invalid user email {user_email}'
        logger.info(f"email='{user_email[0:3]}...{user_email[-8:]}', {groups=}")
        db_user = db.query(models.User).filter(models.User.email == user_email).first()
        if db_user is None:
            db_user = models.User(email=user_email)
            db.add(db_user)
        if not groups: continue  # avoid hanging in for x in None:
        for group in groups:
            db_group = get_group(db, group)
            db_group.users.append(db_user)

    db.commit()
    count_user_groups = db.query(models.association_table_user_groups).count()
    logger.success(f"Completed refresh, now: {count_user_groups} user-groups relationships.")
    DOMAIN_GROUPS_LOADED = True
