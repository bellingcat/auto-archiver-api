from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Type

from cachetools import LRUCache, cached
from cachetools.keys import hashkey
from sqlalchemy import (
    Column,
    ColumnElement,
    ScalarResult,
    false,
    func,
    not_,
    or_,
    select,
    true,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, load_only

from app.shared.db import models
from app.shared.db.models import Archive, Group
from app.shared.log import logger
from app.shared.settings import get_settings
from app.shared.user_groups import UserGroups
from app.shared.utils.misc import fnv1a_hash_mod
from app.web.config import ALLOW_ANY_EMAIL
from app.web.utils.misc import convert_priority_to_queue_dict


DATABASE_QUERY_LIMIT = get_settings().DATABASE_QUERY_LIMIT


def get_limit(user_limit: int):
    return max(1, min(user_limit, DATABASE_QUERY_LIMIT))


# --------------- TASK = Archive


def base_query(db: Session):
    # NOTE: load_only is for optimization and not obfuscation, use
    # .with_entities() if needed
    return (
        db.query(models.Archive)
        .filter(not_(models.Archive.deleted))
        .options(
            load_only(
                models.Archive.id,
                models.Archive.created_at,
                models.Archive.url,
                models.Archive.result,
                models.Archive.store_until,
            )
        )
    )


def search_archives_by_url(
    db: Session,
    url: str,
    email: str,
    read_groups: bool | set[str],
    read_public: bool,
    skip: int = 0,
    limit: int = 100,
    archived_after: datetime = None,
    archived_before: datetime = None,
    absolute_search: bool = False,
) -> list[Type[Archive]]:
    # searches for partial URLs, if email is * no ownership
    # (or read/read_public) filtering happens
    query = base_query(db)
    if email != ALLOW_ANY_EMAIL:
        or_filters = [models.Archive.author_id == email]
        if read_public:
            or_filters.append(models.Archive.public.is_(true()))
        if read_groups is True:
            or_filters.append(models.Archive.group_id.isnot(None))
        else:
            or_filters.append(models.Archive.group_id.in_(read_groups))
        query = query.filter(or_(*or_filters))
    if absolute_search:
        query = query.filter(models.Archive.url == url)
    else:
        query = query.filter(models.Archive.url.like(f"%{url}%"))
    if archived_after:
        query = query.filter(models.Archive.created_at > archived_after)
    if archived_before:
        query = query.filter(models.Archive.created_at < archived_before)
    return (
        query.order_by(models.Archive.created_at.desc())
        .offset(skip)
        .limit(get_limit(limit))
        .all()
    )


def search_archives_by_email(
    db: Session, email: str, skip: int = 0, limit: int = 100
):
    return (
        base_query(db)
        .filter(models.Archive.author_id == email)
        .order_by(models.Archive.created_at.desc())
        .offset(skip)
        .limit(get_limit(limit))
        .all()
    )


def soft_delete_archive(db: Session, id: str, email: str) -> bool:
    # TODO: implement hard-delete with cronjob that deletes from S3
    db_archive = (
        db.query(models.Archive)
        .filter(
            models.Archive.id == id,
            models.Archive.author_id == email,
            models.Archive.deleted.is_(false()),
        )
        .first()
    )
    if db_archive:
        db_archive.deleted = True
        db.commit()
    return db_archive is not None


def count_archives(db: Session):
    return db.query(func.count(models.Archive.id)).scalar()


def count_archive_urls(db: Session):
    return db.query(func.count(models.ArchiveUrl.url)).scalar()


def count_users(db: Session):
    return db.query(func.count(models.User.email)).scalar()


def count_by_user_since(db: Session, seconds_delta: int = 15):
    time_threshold = datetime.now() - timedelta(seconds=seconds_delta)
    return (
        db.query(models.Archive.author_id, func.count().label("total"))
        .filter(models.Archive.created_at >= time_threshold)
        .group_by(models.Archive.author_id)
        .order_by(func.count().desc())
        .limit(500)
        .all()
    )


async def find_by_store_until(
    db: AsyncSession, store_until_is_before: datetime
) -> ScalarResult[Archive]:
    res = await db.execute(
        select(models.Archive).filter(
            models.Archive.deleted.is_(false()),
            models.Archive.store_until < store_until_is_before,
        )
    )
    return res.scalars()


async def soft_delete_expired_archives(db: AsyncSession) -> int:
    to_delete = await find_by_store_until(db, datetime.now())
    counter = 0
    for archive in to_delete:
        archive.deleted = True
        counter += 1
    await db.commit()
    return counter


# --------------- TAG


async def get_group_priority_async(db: AsyncSession, group_id: str) -> dict:
    db_group = await db.get(models.Group, group_id)
    priority = (
        db_group.permissions.get("priority", "low") if db_group else "low"
    )
    return convert_priority_to_queue_dict(priority)


@cached(cache=LRUCache(maxsize=128), key=lambda db, email: hashkey(email))
def get_user_group_names(
    db: Session, email: str
) -> list[Any] | list[ColumnElement[Any]]:
    """
    given an email retrieves the user groups from the DB and then the
    email-domain groups from a global variable, the email does not need to
    belong to an existing user.
    """
    # TODO: the read: [group1, group2] permissions don't currently work
    if not email or not len(email) or "@" not in email:
        return []

    # get user groups
    user_groups = (
        db.query(models.association_table_user_groups)
        .filter_by(user_id=email)
        .with_entities(Column("group_id"))
        .all()
    )
    user_level_groups_names = [g[0] for g in user_groups]

    # get domain groups
    domain = email.split("@")[1]
    domain_level_groups = (
        db.query(models.Group.id)
        .filter(models.Group.domains.contains(domain))
        .with_entities(Column("id"))
        .all()
    )
    domain_level_groups_names = [g[0] for g in domain_level_groups]

    return list(set(user_level_groups_names + domain_level_groups_names))


def get_user_groups_by_name(
    db: Session, groups: list[str]
) -> list[Type[Group]]:
    return db.query(models.Group).filter(models.Group.id.in_(groups)).all()


# --------------- INIT User-Groups


def upsert_group(
    db: Session,
    group_name: str,
    description: str,
    orchestrator: str,
    orchestrator_sheet: str,
    service_account_email: str,
    permissions: dict,
    domains: list,
) -> models.Group:
    db_group = (
        db.query(models.Group).filter(models.Group.id == group_name).first()
    )
    if db_group is None:
        db_group = models.Group(
            id=group_name,
            description=description,
            orchestrator=orchestrator,
            orchestrator_sheet=orchestrator_sheet,
            service_account_email=service_account_email,
            permissions=permissions,
            domains=domains,
        )
        db.add(db_group)
    else:
        db_group.description = description
        db_group.orchestrator = orchestrator
        db_group.orchestrator_sheet = orchestrator_sheet
        db_group.service_account_email = service_account_email
        db_group.permissions = permissions
        db_group.domains = domains
    db.commit()
    db.refresh(db_group)
    return db_group


def upsert_user(db: Session, email: str):
    email = email.lower()
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
    filename = get_settings().USER_GROUPS_FILENAME
    logger.debug(f"Updating user-groups configuration with file {filename}.")

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
        upsert_group(
            db,
            group_id,
            g.description,
            g.orchestrator,
            g.orchestrator_sheet,
            g.service_account_email,
            json.loads(g.permissions.model_dump_json()),
            list(group_domains.get(group_id, [])),
        )
    db_groups: dict[str, models.Group] = {
        g.id: g for g in db.query(models.Group).all()
    }

    # integrity checks
    for group_in_domains in group_domains:
        if group_in_domains not in db_groups:
            logger.warning(
                f"[CONFIG] Group '{group_in_domains}' does not exist in the database: domains setting will not work."
            )

    # reinsert users in their EXPLICITLY DEFINED groups
    # domain groups are check live, as there may be new users that are not
    # explicitly registered but belong to a domain
    for email, explicit_groups in ug.users.items():
        explicit_groups = explicit_groups or []
        logger.info(f"EXPLICIT {display_email_pii(email)} => {explicit_groups}")

        db_user = upsert_user(db, email)

        # connect users to groups
        for group_id in explicit_groups:
            if group_id not in db_groups:
                logger.warning(
                    f"[CONFIG] Group {group_id} does not exist in config file, skipping for email={display_email_pii(email)}."
                )
                continue
            db_groups[group_id].users.append(db_user)

    db.commit()
    count_user_groups = db.query(models.association_table_user_groups).count()
    count_groups = db.query(func.count(models.Group.id)).scalar()

    logger.success(
        f"[CONFIG] DONE: [users={count_users(db)}, groups={count_groups}, explicit user groups={count_user_groups}]."
    )


# --------------- SHEET
def create_sheet(
    db: Session,
    sheet_id: str,
    name: str,
    email: str,
    group_id: str,
    frequency: str,
):
    db_sheet = models.Sheet(
        id=sheet_id,
        name=name,
        author_id=email,
        group_id=group_id,
        frequency=frequency,
    )
    db.add(db_sheet)
    db.commit()
    db.refresh(db_sheet)
    return db_sheet


def get_user_sheet(db: Session, email: str, sheet_id: str) -> models.Sheet:
    return (
        db.query(models.Sheet)
        .filter(models.Sheet.author_id == email, models.Sheet.id == sheet_id)
        .first()
    )


def get_user_sheets(db: Session, email: str) -> list[models.Sheet]:
    return (
        db.query(models.Sheet)
        .filter(models.Sheet.author_id == email)
        .order_by(models.Sheet.last_url_archived_at.desc())
        .all()
    )


async def get_sheets_by_id_hash(
    db: AsyncSession, frequency: str, modulo: str, id_hash: int
) -> list[models.Sheet]:
    result = await db.execute(
        select(models.Sheet).filter(models.Sheet.frequency == frequency)
    )
    filtered = []
    for sheet in result.scalars():
        if fnv1a_hash_mod(sheet.id, int(modulo)) == id_hash:
            filtered.append(sheet)
    return filtered


async def delete_stale_sheets(db: AsyncSession, inactivity_days: int) -> dict:
    time_threshold = datetime.now() - timedelta(days=inactivity_days)
    result = await db.execute(
        select(models.Sheet).filter(
            models.Sheet.last_url_archived_at < time_threshold
        )
    )
    deleted = defaultdict(list)
    for sheet in result.scalars():
        await db.delete(sheet)
        deleted[sheet.author_id].append(sheet)
    await db.commit()
    return dict(deleted)


def delete_sheet(db: Session, sheet_id: str, email: str) -> bool:
    db_sheet = (
        db.query(models.Sheet)
        .filter(models.Sheet.id == sheet_id, models.Sheet.author_id == email)
        .first()
    )
    if db_sheet:
        db.delete(db_sheet)
        db.commit()
    return db_sheet is not None
