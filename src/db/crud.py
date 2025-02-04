from collections import defaultdict
from functools import lru_cache
from sqlalchemy.orm import Session, load_only
from sqlalchemy import Column, or_, func
from loguru import logger
from datetime import datetime, timedelta

from core.config import ALLOW_ANY_EMAIL
from db.database import get_db
from shared.settings import get_settings
from shared.user_groups import UserGroups
from . import models, schemas
import yaml

DATABASE_QUERY_LIMIT = get_settings().DATABASE_QUERY_LIMIT

# --------------- TASK = Archive


def get_limit(user_limit: int):
    return max(1, min(user_limit, DATABASE_QUERY_LIMIT))


def get_archive(db: Session, id: str, email: str):
    email = email.lower()
    query = base_query(db).filter(models.Archive.id == id)
    if email != ALLOW_ANY_EMAIL:
        groups = get_user_groups(email)
        query = query.filter(or_(models.Archive.public == True, models.Archive.author_id == email, models.Archive.group_id.in_(groups)))
    return query.first()


def search_archives_by_url(db: Session, url: str, email: str, skip: int = 0, limit: int = 100, archived_after: datetime = None, archived_before: datetime = None, absolute_search: bool = False):
    # searches for partial URLs, if email is * no ownership filtering happens
    query = base_query(db)
    if email != ALLOW_ANY_EMAIL:
        email = email.lower()
        groups = get_user_groups(email)
        query = query.filter(or_(models.Archive.public == True, models.Archive.author_id == email, models.Archive.group_id.in_(groups)))
    if absolute_search:
        query = query.filter(models.Archive.url == url)
    else:
        query = query.filter(models.Archive.url.like(f'%{url}%'))
    if archived_after:
        query = query.filter(models.Archive.created_at > archived_after)
    if archived_before:
        query = query.filter(models.Archive.created_at < archived_before)
    return query.order_by(models.Archive.created_at.desc()).offset(skip).limit(get_limit(limit)).all()


def search_archives_by_email(db: Session, email: str, skip: int = 0, limit: int = 100):
    email = email.lower()
    return base_query(db).filter(models.Archive.author_id == email).order_by(models.Archive.created_at.desc()).offset(skip).limit(get_limit(limit)).all()


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


def count_archives(db: Session):
    return db.query(func.count(models.Archive.id)).scalar()


def count_archive_urls(db: Session):
    return db.query(func.count(models.ArchiveUrl.url)).scalar()


def count_users(db: Session):
    return db.query(func.count(models.User.email)).scalar()


def count_by_user_since(db: Session, seconds_delta: int = 15):
    time_threshold = datetime.now() - timedelta(seconds=seconds_delta)
    return db.query(models.Archive.author_id, func.count().label('total'))\
        .filter(models.Archive.created_at >= time_threshold)\
        .group_by(models.Archive.author_id)\
        .order_by(func.count().desc())\
        .limit(500).all()


def base_query(db: Session):
    # NOTE: load_only is for optimization and not obfuscation, use .with_entities() if needed
    return db.query(models.Archive)\
        .filter(models.Archive.deleted == False)\
        .options(load_only(models.Archive.id, models.Archive.created_at, models.Archive.url, models.Archive.result))

# --------------- TAG


def create_tag(db: Session, tag: str):
    db_tag = db.query(models.Tag).filter(models.Tag.id == tag).first()
    if not db_tag:
        db_tag = models.Tag(id=tag)
        db.add(db_tag)
        db.commit()
        db.refresh(db_tag)
    return db_tag


def is_user_in_group(db: Session, email: str, group_name: str) -> models.Group:
    if email == ALLOW_ANY_EMAIL: return True
    return len(group_name) and len(email) and group_name in get_user_groups(email)


@lru_cache
def get_user_groups(email: str) -> list[str]:
    """
    given an email retrieves the user groups from the DB and then the email-domain groups from a global variable, the email does not need to belong to an existing user. 
    """
    if not email or not len(email) or "@" not in email: return []
    email = email.lower()

    with get_db() as db:
        # get user groups
        user_groups = db.query(models.association_table_user_groups).filter_by(user_id=email).with_entities(Column("group_id")).all()
        user_level_groups_names = [g[0] for g in user_groups]

        # get domain groups
        domain = email.split('@')[1]
        domain_level_groups = db.query(models.Group.id).filter(models.Group.domains.contains(domain)).with_entities(Column("id")).all()
        domain_level_groups_names = [g[0] for g in domain_level_groups]

        return list(set(user_level_groups_names + domain_level_groups_names))


# --------------- INIT User-Groups

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


def upsert_group(db: Session, group_name: str, description: str, orchestrator: str, orchestrator_sheet: str, permissions: dict, domains: list) -> models.Group:
    db_group = db.query(models.Group).filter(models.Group.id == group_name).first()
    if db_group is None:
        db_group = models.Group(id=group_name, description=description, orchestrator=orchestrator, orchestrator_sheet=orchestrator_sheet, permissions=permissions, domains=domains)
        db.add(db_group)
    else:
        db_group.description = description
        db_group.orchestrator = orchestrator
        db_group.orchestrator_sheet = orchestrator_sheet
        db_group.permissions = permissions
        db_group.domains = domains
    db.commit()
    db.refresh(db_group)
    return db_group


def upsert_user(db: Session, email: str):
    db_user = db.query(models.User).filter(models.User.email == email).first()
    if db_user is None:
        db_user = models.User(email=email)
        db.add(db_user)
        db.commit()
    return db_user


def upsert_user_groups(db: Session):
    def display_email_pii(email: str):
        return f"'{email[0:3]}...@{email.split('@')[1]}'"
    """
    reads the user_groups yaml file and inserts any new users, groups, 
    along with new participation of users in groups
    """
    logger.debug("Updating user-groups configuration.")
    filename = get_settings().USER_GROUPS_FILENAME

    ug = UserGroups(filename)

    # delete all user-groups relationships
    db.query(models.association_table_user_groups).delete()

    # create a map of group_id -> domains and another of domain -> groups
    group_domains = defaultdict(set)
    domain_groups = defaultdict(list)
    for domain, explicit_groups in ug.domains.items():
        domain_groups[domain] = list(set(explicit_groups))
        for group in explicit_groups:
            group_domains[group].add(domain)
    import json
    # upsert groups and save a map of groupid -> dbobject
    for group_id, g in ug.groups.items():
        upsert_group(db, group_id, g.description, g.orchestrator, g.orchestrator_sheet, json.loads(g.permissions.model_dump_json()), list(group_domains.get(group_id, [])))
    db_groups: dict[str, models.Group] = {g.id: g for g in db.query(models.Group).all()}

    # integrity checks
    for group_in_domains in group_domains:
        if group_in_domains not in db_groups:
            logger.warning(f"[CONFIG] Group '{group_in_domains}' does not exist in the database: domains setting will not work.")

    # reinsert users in their EXPLICITLY DEFINED groups
    # domain groups are check live, as there may be new users that are not explicitly registered but belong to a domain
    for email, explicit_groups in ug.users.items():
        explicit_groups = explicit_groups or []
        logger.info(f"EXPLICIT {display_email_pii(email)} => {explicit_groups}")

        db_user = upsert_user(db, email)

        # connect users to groups
        for group_id in explicit_groups:
            if group_id not in db_groups:
                logger.warning(f"[CONFIG] Group {group_id} does not exist in config file, skipping for email={display_email_pii(email)}.")
                continue
            db_groups[group_id].users.append(db_user)

    db.commit()
    count_user_groups = db.query(models.association_table_user_groups).count()
    count_groups = db.query(func.count(models.Group.id)).scalar()

    logger.success(f"[CONFIG] DONE: [users={count_users(db)}, groups={count_groups}, explicit user groups={count_user_groups}].")


# --------------- SHEET
def create_sheet(db: Session, sheet_id: str, sheet_name: str, email: str, group_id: str, frequency: str):
    db_sheet = models.Sheet(id=sheet_id, name=sheet_name, author_id=email, group_id=group_id, frequency=frequency)
    db.add(db_sheet)
    db.commit()
    db.refresh(db_sheet)
    return db_sheet


def get_user_sheet(db: Session, email: str, sheet_id: str) -> models.Sheet:
    return db.query(models.Sheet).filter(models.Sheet.author_id == email, models.Sheet.id == sheet_id).first()


def get_user_sheets(db: Session, email: str) -> list[models.Sheet]:
    return db.query(models.Sheet).filter(models.Sheet.author_id == email).order_by(models.Sheet.last_archived_at.desc()).all()


def delete_sheet(db: Session, sheet_id: str, email: str) -> bool:
    db_sheet = db.query(models.Sheet).filter(models.Sheet.id == sheet_id, models.Sheet.author_id == email).first()
    if db_sheet:
        db.delete(db_sheet)
        db.commit()
    return db_sheet is not None