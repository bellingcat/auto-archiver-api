from celery.result import AsyncResult
from fastapi import Body, FastAPI, Depends, Request, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi_utils.tasks import repeat_every
import alembic.config
from dotenv import load_dotenv
import traceback, os, logging
from loguru import logger
from datetime import datetime
import sqlalchemy
from prometheus_fastapi_instrumentator import Instrumentator

from worker import create_archive_task, create_sheet_task, celery, insert_result_into_db

from db import crud, models, schemas
from db.database import engine, SessionLocal
from sqlalchemy.orm import Session
from security import get_bearer_auth, get_basic_auth, get_server_auth, bearer_security, get_bearer_auth_token_or_jwt
from auto_archiver import Metadata

load_dotenv()

# Configuration
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "chrome-extension://ondkcheoicfckabcnkdgbepofpjmjcmb,chrome-extension://ojcimmjndnlmmlgnjaeojoebaceokpdp").split(",")
VERSION = "0.5.4"

# min-version refers to the version of auto-archiver-extension on the webstore
BREAKING_CHANGES = {"minVersion": "0.3.1", "message": "The latest update has breaking changes, please update the extension to the most recent version."}

app = FastAPI(title="Auto-Archiver API", version=VERSION, contact={"name":"Bellingcat", "url":"https://github.com/bellingcat/auto-archiver-api"}) 
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# prometheus exposed in /metrics with authentication
Instrumentator().instrument(app).expose(app, dependencies=[Depends(get_basic_auth)])

app.mount("/static", StaticFiles(directory="static"), name="static")

SERVE_LOCAL_ARCHIVE = os.environ.get("SERVE_LOCAL_ARCHIVE", "")
if len(SERVE_LOCAL_ARCHIVE) > 1 and os.path.isdir(SERVE_LOCAL_ARCHIVE):
    logger.info(f"mounting local archive {SERVE_LOCAL_ARCHIVE}")
    app.mount(SERVE_LOCAL_ARCHIVE, StaticFiles(directory=SERVE_LOCAL_ARCHIVE), name=SERVE_LOCAL_ARCHIVE)

def get_db():
    session = SessionLocal()
    try: yield session
    finally: session.close()

# logging configurations
logger.add("logs/api_logs.log", retention="30 days", rotation="3 days")
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    response = await call_next(request)
    logger.info(f"{request.client.host}:{request.client.port} {request.method} {request.url._url} - HTTP {response.status_code}")
    return response

@app.get("/")
async def home(request: Request): 
    status = {"version": VERSION, "breakingChanges": BREAKING_CHANGES}
    try:
        # if authenticated will load available groups
        email = await get_bearer_auth(await bearer_security(request))
        db: Session = next(get_db())
        status["groups"] = crud.get_user_groups(db, email)
    except HTTPException: pass
    except Exception as e: logger.error(e)
    return JSONResponse(status)


#-----Submit URL and manipulate tasks. Bearer protected below

@app.get("/groups", response_model=list[str])
def get_user_groups(db: Session = Depends(get_db), email = Depends(get_bearer_auth)):
    return crud.get_user_groups(db, email)

@app.get("/tasks/search-url", response_model=list[schemas.Archive])
def search_by_url(url:str, skip: int = 0, limit: int = 100, archived_after:datetime=None, archived_before:datetime=None, db: Session = Depends(get_db), email = Depends(get_bearer_auth_token_or_jwt)):
    return crud.search_tasks_by_url(db, url.strip(), email, skip=skip, limit=limit, archived_after=archived_after, archived_before=archived_before)
    
@app.get("/tasks/sync", response_model=list[schemas.Archive])
def search(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), email = Depends(get_bearer_auth)):
    return crud.search_tasks_by_email(db, email, skip=skip, limit=limit)

@app.post("/tasks", status_code=201)
def archive_tasks(archive:schemas.ArchiveCreate, email = Depends(get_bearer_auth)):
    archive.author_id = email
    url = archive.url
    logger.info(f"new {archive.public=} task for {email=} and {archive.group_id=}: {url}")
    if type(url)!=str or len(url)<=5:
        raise HTTPException(status_code=422, detail=f"Invalid URL received: {url}")
    logger.info("creating task")
    task = create_archive_task.delay(archive.json())
    return JSONResponse({"id": task.id})

@app.get("/archive/{task_id}")
def lookup(task_id, db: Session = Depends(get_db), email = Depends(get_bearer_auth)):
    return crud.get_task(db, task_id)

@app.get("/tasks/{task_id}")
def get_status(task_id, email = Depends(get_bearer_auth)):
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
        logger.error(e)
        logger.error(traceback.format_exc())
        return JSONResponse({
            "id": task_id,
            "status": "FAILURE",
            "result": {"error": str(e)}
        })

@app.delete("/tasks/{task_id}")
def delete_task(task_id, db: Session = Depends(get_db), email = Depends(get_bearer_auth)):
    logger.info(f"deleting task {task_id} request by {email}")
    return JSONResponse({
        "id": task_id,
        "deleted": crud.soft_delete_task(db, task_id, email)
    })

#----- Google Sheets Logic
@app.post("/sheet", status_code=201)
def archive_sheet(sheet:schemas.SubmitSheet, email = Depends(get_bearer_auth)):
    logger.info(f"SHEET TASK for {sheet=}")
    sheet.author_id = email
    if not sheet.sheet_name and not sheet.sheet_id:
        raise HTTPException(status_code=422, detail=f"sheet name or id is required")
    task = create_sheet_task.delay(sheet.json())
    return JSONResponse({"id": task.id})

@app.post("/sheet_service", status_code=201)
def archive_sheet_service(sheet:schemas.SubmitSheet, basic_auth = Depends(get_server_auth)):
    logger.info(f"SHEET TASK for {sheet=}")
    if not sheet.sheet_name and not sheet.sheet_id:
        raise HTTPException(status_code=422, detail=f"sheet name or id is required")
    task = create_sheet_task.delay(sheet.json())
    return JSONResponse({"id": task.id})

#----- endpoint to submit data archived elsewhere
@app.post("/submit-archive", status_code=201)
def submit_manual_archive(manual:schemas.SubmitManual, basic_auth = Depends(get_basic_auth)):
    result = Metadata.from_json(manual.result)
    logger.info(f"MANUAL SUBMIT {result.get_url()} {manual.author_id}")
    manual.tags.add("manual")
    try:
        archive_id = insert_result_into_db(result, manual.tags, manual.public, manual.group_id, manual.author_id, models.generate_uuid())
    except sqlalchemy.exc.IntegrityError as e:
        logger.error(e)
        raise HTTPException(status_code=422, detail=f"Cannot insert into DB due to integrity error")
    return JSONResponse({"id": archive_id})


# Basic protected logic to allow access to 1 static file
SF = os.environ.get("STATIC_FILE", "")
if len(SF) > 1 and os.path.isfile(SF):
    @app.get("/static-file")
    def static_file(basic_auth = Depends(get_basic_auth)):
        return FileResponse(SF, filename=os.path.basename(SF))


# on startup
@app.on_event("startup")
async def on_startup():
#     # Not needed if you setup a migration system like Alembic
#     await create_db_and_tables()
    models.Base.metadata.create_all(bind=engine)
    alembic.config.main(argv=['--raiseerr', 'upgrade', 'head'])
    # disabling uvicorn logger since we use loguru in logging_middleware
    logging.getLogger("uvicorn.access").disabled = True

@app.on_event("startup")
@repeat_every(seconds=60 * 60)  # 1 hour
async def on_startup():
    db: Session = next(get_db())
    crud.upsert_user_groups(db)
