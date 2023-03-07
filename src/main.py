from celery.result import AsyncResult
from fastapi import Body, FastAPI, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import alembic.config
from dotenv import load_dotenv
import traceback, os
from loguru import logger

from worker import create_archive_task, celery

from db import crud, models, schemas
from db.database import engine, SessionLocal
from sqlalchemy.orm import Session
from security import get_bearer_auth, get_basic_auth

load_dotenv()

# Configuration
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "chrome-extension://ondkcheoicfckabcnkdgbepofpjmjcmb,chrome-extension://ojcimmjndnlmmlgnjaeojoebaceokpdp").split(",")
VERSION = "0.2.0"

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
def home(): return JSONResponse({"version": VERSION})

# Bearer protected below

@app.get("/tasks/search-url", response_model=list[schemas.Task])
def search(url:str, skip: int = 0, limit: int = 100, db: Session = Depends(get_db), email = Depends(get_bearer_auth)):
    return crud.search_tasks_by_url(db, url, skip=skip, limit=limit)

# @app.get("/tasks/search", response_model=list[schemas.Task])
# def search(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), email = Depends(get_bearer_auth)):
#     return crud.get_tasks(db, skip=skip, limit=limit)
    
@app.get("/tasks/sync", response_model=list[schemas.Task])
def search(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), email = Depends(get_bearer_auth)):
    return crud.search_tasks_by_email(db, email, skip=skip, limit=limit)

@app.post("/tasks", status_code=201)
def run_task(payload = Body(...), email = Depends(get_bearer_auth)):
    logger.info(f"new task for user {email}: {payload.get('url')}")
    task = create_archive_task.delay(url=payload.get('url'), email=email)
    return JSONResponse({"id": task.id})

@app.get("/tasks/{task_id}")
def get_status(task_id, email = Depends(get_bearer_auth)):
    logger.info(f"status check for user {email}")
    task_result = AsyncResult(task_id, app=celery)
    result = {
        "id": task_id,
        "status": task_result.status,
        "result": task_result.result
    }
    try:
        json_result = jsonable_encoder(result, exclude_unset=True)
        return JSONResponse(json_result)
    except Exception as e:
        logger.error(e)
        logger.error(traceback.format_exc())
        return JSONResponse({
            "id": task_id,
            "status": "FAILURE",
        })


@app.delete("/tasks/{task_id}")
def get_status(task_id, db: Session = Depends(get_db), email = Depends(get_bearer_auth)):
    logger.info(f"deleting task {task_id} request by {email}")
    return JSONResponse({
        "id": task_id,
        "deleted": crud.soft_delete_task(db, task_id, email)
    })

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
#     await create_db_and_tables()https://github.com/bellingcat/auto-archiver/tree/dockerize
    models.Base.metadata.create_all(bind=engine)
    alembic.config.main(argv=['--raiseerr', 'upgrade', 'head'])
