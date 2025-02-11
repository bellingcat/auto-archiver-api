import os
from celery.result import AsyncResult
from fastapi import FastAPI, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from datetime import datetime
from sqlalchemy.orm import Session
from loguru import logger

from app.shared.log import log_error
from app.web.middleware import logging_middleware
from app.shared import schemas
from app.shared.task_messaging import get_celery

from app.web.db import crud
from app.web.security import get_user_auth, token_api_key_auth, get_token_or_user_auth
from app.web.config import VERSION, API_DESCRIPTION
from app.shared.db.database import get_db_dependency
from app.web.events import lifespan
from app.shared.settings import get_settings


from app.web.endpoints.default import default_router
from app.web.endpoints.url import url_router
from app.web.endpoints.sheet import sheet_router
from app.web.endpoints.task import task_router
from app.web.endpoints.interoperability import interoperability_router

celery = get_celery()

def app_factory(settings = get_settings()):
    app = FastAPI(
        title="Auto-Archiver API",
        description=API_DESCRIPTION,
        version=VERSION,
        contact={"name": "GitHub", "url": "https://github.com/bellingcat/auto-archiver-api"},
        lifespan=lifespan
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(logging_middleware)

    app.include_router(default_router)
    app.include_router(url_router)
    app.include_router(sheet_router)
    app.include_router(task_router)
    app.include_router(interoperability_router)

    # prometheus exposed in /metrics with authentication
    Instrumentator(should_group_status_codes=False, excluded_handlers=["/metrics", "/health", "/openapi.json", "/favicon.ico"]).instrument(app).expose(app, dependencies=[Depends(token_api_key_auth)])

    # TODO: recheck this for security, currently only needed for when local_storage is used
    local_dir = settings.SERVE_LOCAL_ARCHIVE
    if not os.path.isdir(local_dir) and os.path.isdir(local_dir.replace("/app", ".")):
        local_dir = local_dir.replace("/app", ".")
    if len(settings.SERVE_LOCAL_ARCHIVE) > 1 and os.path.isdir(local_dir):
        logger.warning(f"MOUNTing local archive {settings.SERVE_LOCAL_ARCHIVE}")
        app.mount(settings.SERVE_LOCAL_ARCHIVE, StaticFiles(directory=local_dir), name=settings.SERVE_LOCAL_ARCHIVE)



    # -----Submit URL and manipulate tasks. Bearer protected below


    @app.get("/tasks/search-url", response_model=list[schemas.Archive], deprecated=True)  # DEPRECATED
    def search_by_url(url: str, skip: int = 0, limit: int = 100, archived_after: datetime = None, archived_before: datetime = None, db: Session = Depends(get_db_dependency), email=Depends(get_token_or_user_auth)):
        return crud.search_archives_by_url(db, url.strip(), email, skip=skip, limit=limit, archived_after=archived_after, archived_before=archived_before)


    @app.get("/tasks/sync", response_model=list[schemas.Archive], deprecated=True)  # DEPRECATED
    def search(skip: int = 0, limit: int = 100, db: Session = Depends(get_db_dependency), email=Depends(get_user_auth)):
        return crud.search_archives_by_email(db, email, skip=skip, limit=limit)


    @app.post("/tasks", status_code=201, deprecated=True)  # DEPRECATED
    def archive_tasks(archive: schemas.ArchiveCreate, email=Depends(get_token_or_user_auth)):
        archive.author_id = email
        url = archive.url
        logger.info(f"new {archive.public=} task for {email=} and {archive.group_id=}: {url}")
        if type(url) != str or len(url) <= 5:
            raise HTTPException(status_code=422, detail=f"Invalid URL received: {url}")
        logger.info("creating task")

        task = celery.signature("create_archive_task", args=[archive.model_dump_json()]).delay()
        return JSONResponse({"id": task.id})


    @app.get("/archive/{task_id}", deprecated=True)  # DEPRECATED
    def lookup(task_id, db: Session = Depends(get_db_dependency), email=Depends(get_token_or_user_auth)):
        return crud.get_archive(db, task_id, email)


    @app.get("/tasks/{task_id}", deprecated=True)  # DEPRECATED
    def get_status(task_id, email=Depends(get_token_or_user_auth)):
        logger.info(f"status check for user {email} task {task_id}")
        task = AsyncResult(task_id, app=celery)
        try:
            if task.status == "FAILURE":
                # *FAILURE* The task raised an exception, or has exceeded the retry limit.
                # The :attr:`result` attribute then contains the exception raised by the task.
                # https://docs.celeryq.dev/en/stable/_modules/celery/result.html#AsyncResult
                raise task.result

            response = {
                "id": task_id,
                "status": task.status,
                "result": task.result
            }
            return JSONResponse(jsonable_encoder(response, exclude_unset=True))

        except Exception as e:
            log_error(e)
            return JSONResponse({
                "id": task_id,
                "status": "FAILURE",
                "result": {"error": str(e)}
            })


    @app.delete("/tasks/{task_id}", deprecated=True)  # DEPRECATED
    def delete_task(task_id, db: Session = Depends(get_db_dependency), email=Depends(get_user_auth)):
        logger.info(f"deleting task {task_id} request by {email}")
        return JSONResponse({
            "id": task_id,
            "deleted": crud.soft_delete_task(db, task_id, email)
        })

    # ----- Google Sheets Logic


    @app.post("/sheet", status_code=201, deprecated=True)  # DEPRECATED
    def archive_sheet(sheet: schemas.SubmitSheet, email=Depends(get_user_auth), db: Session = Depends(get_db_dependency)):
        logger.info(f"SHEET TASK for {sheet=}")
        sheet.author_id = email
        #NB: no longer working
        if not crud.is_user_in_group(email, sheet.group_id):
            raise HTTPException(status_code=403, detail="User does not have access to this group.")
        task = celery.signature("create_sheet_task", args=[sheet.model_dump_json()]).delay()
        return JSONResponse({"id": task.id})


    @app.post("/sheet_service", status_code=201, deprecated=True)  # DEPRECATED
    def archive_sheet_service(sheet: schemas.SubmitSheet, auth=Depends(token_api_key_auth)):
        logger.info(f"SHEET TASK for {sheet=}")
        sheet.author_id = sheet.author_id or "api-endpoint"
        
        task = celery.signature("create_sheet_task", args=[sheet.model_dump_json()]).delay()
        return JSONResponse({"id": task.id})

    # ----- endpoint to submit data archived elsewhere


    @app.post("/submit-archive", status_code=201, deprecated=True)  # DEPRECATED
    def submit_manual_archive(manual: schemas.SubmitManual, auth=Depends(token_api_key_auth)):
        raise HTTPException(status_code=410, detail="This endpoint is deprecated. Use /interop/submit-archive instead.")
        # result = Metadata.from_json(manual.result)
        # logger.info(f"MANUAL SUBMIT {result.get_url()} {manual.author_id}")
        # manual.tags.add("manual")
        # try:
        #     # archive_id = insert_result_into_db(result, manual.tags, manual.public, manual.group_id, manual.author_id, models.generate_uuid())
        # except sqlalchemy.exc.IntegrityError as e:
        #     log_error(e)
        #     raise HTTPException(status_code=422, detail=f"Cannot insert into DB due to integrity error")
        # return JSONResponse({"id": archive_id})

    return app