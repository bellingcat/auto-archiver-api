
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime

from loguru import logger
from web.security import get_user_auth, get_token_or_user_auth
from sqlalchemy.orm import Session

from db import crud, schemas
from db.database import get_db_dependency

from worker import create_archive_task

url_router = APIRouter(prefix="/url", tags=["Single URL operations"])


@url_router.post("/archive", status_code=201, summary="Submit a single URL archive request, starts an archiving task.", response_model=schemas.Task, response_description="task_id for the archiving task, will match the archive id.")
def archive_url(archive: schemas.ArchiveCreate, email=Depends(get_token_or_user_auth)):
    archive.author_id = email
    url = archive.url
    logger.info(f"new {archive.public=} task for {email=} and {archive.group_id=}: {url}")
    if type(url) != str or len(url) <= 5:
        raise HTTPException(status_code=422, detail=f"Invalid URL received: {url}")
    logger.info("creating task")
    task = create_archive_task.delay(archive.model_dump_json())
    task_response = schemas.Task(id=task.id)
    return JSONResponse(task_response.model_dump(), status_code=201)


@url_router.get("/search", response_model=list[schemas.Archive], summary="Search for archive entries by URL.")
def search_by_url(
        url: str, skip: int = 0, limit: int = 25,
        archived_after: datetime = None, archived_before: datetime = None,
        db: Session = Depends(get_db_dependency),
        email=Depends(get_token_or_user_auth)):
    return crud.search_archives_by_url(db, url.strip(), email, skip=skip, limit=limit, archived_after=archived_after, archived_before=archived_before)


@url_router.get("/latest", response_model=list[schemas.Archive], summary="Fetch latest URL archives for the authenticated user.")
def latest(skip: int = 0, limit: int = 25, db: Session = Depends(get_db_dependency), email=Depends(get_user_auth)):
    return crud.search_archives_by_email(db, email, skip=skip, limit=limit)


@url_router.get("/{id}", response_model=schemas.Archive, summary="Fetch a single URL archive by the associated id.")
def lookup(id, db: Session = Depends(get_db_dependency), email=Depends(get_token_or_user_auth)):
    archive = crud.get_archive(db, id, email)
    if archive is None:
        raise HTTPException(status_code=404, detail="Archive not found")
    return archive


@url_router.delete("/{id}", response_model=schemas.TaskDelete, summary="Delete a single URL archive by id.")
def delete_task(id, db: Session = Depends(get_db_dependency), email=Depends(get_user_auth)):
    logger.info(f"deleting url archive task {id} request by {email}")
    return JSONResponse({
        "id": id,
        "deleted": crud.soft_delete_task(db, id, email)
    })
