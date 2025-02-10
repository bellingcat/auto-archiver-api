# TODO: temporary file for this code, maybe other code belongs here, maybe not. do decide


import datetime
from sqlalchemy.orm import Session

from app.shared.db import crud


def get_store_archive_until(db: Session, group_id: str) -> datetime.datetime:
    group = crud.get_group(db, group_id)
    max_lifespan = group.permissions.get("max_archive_lifespan_months", -1)
    if max_lifespan == -1: return None

    return datetime.datetime.now() + datetime.timedelta(days=30 * max_lifespan)
