from datetime import datetime
from http import HTTPStatus
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.orm import Session

from app.shared import schemas
from app.shared.db.database import get_db_dependency
from app.shared.task_messaging import get_celery
from app.web.config import ALLOW_ANY_EMAIL
from app.web.db import crud
from app.web.db.user_state import UserState
from app.web.security import get_token_or_user_auth, get_user_state
from app.web.utils.misc import convert_priority_to_queue_dict


url_router = APIRouter(prefix="/url", tags=["Single URL operations"])

celery = get_celery()


@url_router.post(
    "/archive",
    status_code=HTTPStatus.CREATED,
    summary="Submit a single URL archive request, starts an archiving task.",
    response_description="task_id for the archiving task, will match the archive id.",
)
def archive_url(
    archive: schemas.ArchiveTrigger,
    email=Depends(get_token_or_user_auth),
    db: Session = Depends(get_db_dependency),
) -> schemas.Task:
    logger.info(
        f"new {archive.public=} task for {email=} and {archive.group_id=}: {archive.url}"
    )

    parsed_url = urlparse(archive.url)
    if not all([parsed_url.scheme, parsed_url.netloc]):
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail="Invalid URL received."
        )

    archive_create = schemas.ArchiveCreate(**archive.model_dump())
    if email != ALLOW_ANY_EMAIL:
        archive_create.author_id = email
        user = UserState(db, email)
        if archive.group_id and not user.in_group(archive.group_id):
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="User does not have access to this group.",
            )
        if not user.has_quota_max_monthly_urls(archive.group_id):
            raise HTTPException(
                status_code=HTTPStatus.TOO_MANY_REQUESTS,
                detail="User has reached their monthly URL quota.",
            )
        if not user.has_quota_max_monthly_mbs(archive.group_id):
            raise HTTPException(
                status_code=HTTPStatus.TOO_MANY_REQUESTS,
                detail="User has reached their monthly MB quota.",
            )
        group_queue = user.priority_group(archive_create.group_id)
    else:
        archive_create.author_id = archive.author_id or email
        group_queue = convert_priority_to_queue_dict("high")

    task = celery.signature(
        "create_archive_task", args=[archive_create.model_dump_json()]
    ).apply_async(**group_queue)
    task_response = schemas.Task(id=task.id)
    return JSONResponse(
        task_response.model_dump(), status_code=HTTPStatus.CREATED
    )


@url_router.get("/search", summary="Search for archive entries by URL.")
def search_by_url(
    url: str,
    skip: int = 0,
    limit: int = 25,
    archived_after: datetime = None,
    archived_before: datetime = None,
    db: Session = Depends(get_db_dependency),
    email: str = Depends(get_token_or_user_auth),
) -> list[schemas.ArchiveResult]:
    read_groups, read_public = False, False
    if email != ALLOW_ANY_EMAIL:
        user = UserState(db, email)
        if not user.read and not user.read_public:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="User does not have read access.",
            )
        read_groups = user.read
        read_public = user.read_public
    return crud.search_archives_by_url(
        db,
        url.strip(),
        email,
        read_groups,
        read_public,
        skip=skip,
        limit=limit,
        archived_after=archived_after,
        archived_before=archived_before,
    )


@url_router.delete("/{id}", summary="Delete a single URL archive by id.")
def delete_archive(
    id: str,
    user: UserState = Depends(get_user_state),
    db: Session = Depends(get_db_dependency),
) -> schemas.DeleteResponse:
    logger.info(f"deleting url archive task {id} request by {user.email}")
    return JSONResponse(
        {"id": id, "deleted": crud.soft_delete_archive(db, id, user.email)}
    )
