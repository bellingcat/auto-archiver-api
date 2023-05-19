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

from worker import create_archive_task, create_sheet_task, celery

from db import crud, models, schemas
from db.database import engine, SessionLocal
from sqlalchemy.orm import Session
from security import get_bearer_auth, get_basic_auth, bearer_security, get_bearer_auth_public

load_dotenv()

# Configuration
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "chrome-extension://ondkcheoicfckabcnkdgbepofpjmjcmb,chrome-extension://ojcimmjndnlmmlgnjaeojoebaceokpdp").split(",")
VERSION = "0.4.0"
# min-version refers to the version of auto-archiver-extension on the webstore
BREAKING_CHANGES = {"minVersion": "0.3.0", "message": "The latest update has breaking changes, please update the extension to the most recent version."}

app = FastAPI() 
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")

def get_db():
    session = SessionLocal()
    try: yield session
    finally: session.close()
    

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

# logging configurations
logger.add("logs/api_logs.log", retention="30 days", rotation="3 days")
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    response = await call_next(request)
    logger.info(f"{request.client.host}:{request.client.port} {request.method} {request.url._url} - HTTP {response.status_code}")
    return response


# Bearer protected below

@app.get("/groups", response_model=list[str])
def get_user_groups(db: Session = Depends(get_db), email = Depends(get_bearer_auth)):
    return crud.get_user_groups(db, email)

@app.get("/tasks/search-url", response_model=list[schemas.Archive])
def search(url:str, skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _email = Depends(get_bearer_auth)):
    return crud.search_tasks_by_url(db, url, skip=skip, limit=limit)

# @app.get("/tasks/search", response_model=list[schemas.Task])
# def search(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), email = Depends(get_bearer_auth)):
#     return crud.get_tasks(db, skip=skip, limit=limit)
    
@app.get("/tasks/sync", response_model=list[schemas.Archive])
def search(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), email = Depends(get_bearer_auth)):
    return crud.search_tasks_by_email(db, email, skip=skip, limit=limit)

@app.post("/tasks", status_code=201)
def run_task(archive:schemas.ArchiveCreate, email = Depends(get_bearer_auth)):
    archive.author_id = email
    url = archive.url
    logger.warning(archive)
    logger.info(f"new {archive.public=} task for {email=} and {archive.group_id=}: {url}")
    if type(url)!=str or len(url)<=5:
        raise HTTPException(status_code=422, detail=f"Invalid URL received: {url}")
    logger.info("creating task")
    task = create_archive_task.delay(archive.json())
    return JSONResponse({"id": task.id})

# @app.post("/tasks", status_code=201)
# def run_task(payload = Body(...), email = Depends(get_bearer_auth)):
#     url = payload.get('url')
#     public = payload.get('public', True)
#     group = payload.get('group', None)
#     logger.info(f"new {public=} task for {email=} and {group=}: {url}")
#     if type(url)!=str or len(url)<=5:
#         raise HTTPException(status_code=422, detail=f"Invalid URL received: {url}")
#     task = create_archive_task.delay(url=payload.get('url'), email=email, public=public, group=group)
#     return JSONResponse({"id": task.id})

@app.get("/tasks/{task_id}")
def get_status(task_id, email = Depends(get_bearer_auth)):
    logger.info(f"status check for user {email}")
    task_result = AsyncResult(task_id, app=celery)
    logger.info(task_result)
    result = {
        "id": task_id,
        "status": task_result.status,
        "result": task_result.result
    }
    try:
        if task_result.result and "error" in task_result.result:
            result["status"] = "FAILURE"
    except Exception as e: logger.error(traceback.format_exc())
    try:
        json_result = jsonable_encoder(result, exclude_unset=True)
        return JSONResponse(json_result)
    except Exception as e:
        logger.error(e)
        logger.error(traceback.format_exc())
        return JSONResponse({
            "id": task_id,
            "status": "FAILURE",
            "result": {"error": e}
        })


@app.delete("/tasks/{task_id}")
def get_status(task_id, db: Session = Depends(get_db), email = Depends(get_bearer_auth_public)):
    logger.info(f"deleting task {task_id} request by {email}")
    return JSONResponse({
        "id": task_id,
        "deleted": crud.soft_delete_task(db, task_id, email)
    })

@app.post("/sheet", status_code=201)
def run_task(sheet:schemas.SubmitSheet, email = Depends(get_bearer_auth)):
    logger.info(f"LAUNCHING SHEET TASK for {email=}")
    if not sheet.sheet_name and not sheet.sheet_id:
        raise HTTPException(status_code=422, detail=f"sheet name or id is required")
    task = create_sheet_task.delay(sheet.json())
    return JSONResponse({"id": task.id})

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
    USER_GROUPS_FILENAME=os.environ.get("USER_GROUPS_FILENAME", "user-groups.yaml")
    crud.upsert_user_groups(db, USER_GROUPS_FILENAME)