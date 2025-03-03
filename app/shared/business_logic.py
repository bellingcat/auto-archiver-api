import datetime

from sqlalchemy.orm import Session

from app.shared.db import worker_crud


# TODO: temporary file for this code, maybe other code belongs here, maybe not. do
#  decide

def get_store_archive_until(db: Session, group_id: str) -> datetime.datetime:
    group = worker_crud.get_group(db, group_id)
    assert group, f"Group {group_id} not found."
    assert group.permissions and isinstance(group.permissions, dict), (
        f"Group {group_id} has no permissions."
    )

    max_lifespan = group.permissions.get("max_archive_lifespan_months", -1)
    if max_lifespan == -1:
        return None

    return datetime.datetime.now() + datetime.timedelta(days=30 * max_lifespan)


def get_store_archive_until_or_never(
        db: Session, group_id: str
) -> datetime.datetime:
    try:
        return get_store_archive_until(db, group_id)
    except AssertionError:
        return None
