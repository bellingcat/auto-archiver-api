from celery.result import AsyncResult
from fastapi import Body, FastAPI, Request, HTTPException, status, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
# from fastapi.templating import Jinja2Templates
# from pydantic.json import pydantic_encoder
from dotenv import load_dotenv
import traceback, os, requests, re
from loguru import logger

from worker import create_archive_task, celery

from db import crud, models, schemas
from db.database import engine, SessionLocal
from sqlalchemy.orm import Session

# models.Base.metadata.create_all(bind=engine)

load_dotenv()

# Configuration
GOOGLE_CHROME_APP_ID = os.environ.get("GOOGLE_CHROME_APP_ID")
assert len(GOOGLE_CHROME_APP_ID)>10, "GOOGLE_CHROME_APP_ID env variable not set"
ALLOWED_EMAILS = set(os.environ.get("ALLOWED_EMAILS", "").split(","))
assert len(GOOGLE_CHROME_APP_ID)>=1, "at least one ALLOWED_EMAILS is required from the env variable"
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "chrome-extension://ondkcheoicfckabcnkdgbepofpjmjcmb,chrome-extension://ojcimmjndnlmmlgnjaeojoebaceokpdp").split(",")
VERSION = "0.1.5"

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

    
@app.get("/tasks/search-url", response_model=list[schemas.Task])
def search(access_token:str, url:str, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    validate_user_get_email(access_token)
    return crud.search_tasks_by_url(db, url, skip=skip, limit=limit)
    
@app.get("/tasks/search", response_model=list[schemas.Task])
def search(access_token:str, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    validate_user_get_email(access_token)
    return crud.get_tasks(db, skip=skip, limit=limit)
    
@app.get("/tasks/sync", response_model=list[schemas.Task])
def search(access_token:str, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    email = validate_user_get_email(access_token)
    return crud.search_tasks_by_email(db, email, skip=skip, limit=limit)

@app.post("/tasks", status_code=201)
def run_task(payload = Body(...)):
    email = validate_user_get_email(payload.get("access_token"))
    logger.info(f"new task for user {email}: {payload.get('url')}")
    task = create_archive_task.delay(url=payload.get('url'), email=email)
    return JSONResponse({"id": task.id})

@app.get("/tasks/{task_id}")
def get_status(task_id, access_token:str):
    email = validate_user_get_email(access_token)
    logger.info(f"status check for user {email}")
    task_result = AsyncResult(task_id, app=celery)
    result = {
        "id": task_id,
        "status": task_result.status,
        "result": task_result.result
    }
    try:
        json_result = jsonable_encoder(result, exclude_unset=True)
        # json_result = jsonable_encoder(result, custom_encoder={"pydantic_encoder": pydantic_encoder}) # causes error
        return JSONResponse(json_result)
    except Exception as e:
        logger.error(e)
        logger.error(traceback.format_exc())
        return JSONResponse({
            "id": task_id,
            "status": "FAILURE",
        })


@app.delete("/tasks/{task_id}")
def get_status(task_id, access_token:str, db: Session = Depends(get_db)):
    email = validate_user_get_email(access_token)
    logger.info(f"deleting task {task_id} request by {email}")
    return JSONResponse({
        "id": task_id,
        "deleted": crud.delete_task(db, task_id, email)
    })


@app.get("/")
def home():
    return JSONResponse({"status": "good", "version": VERSION})

@app.on_event("startup")
async def on_startup():
#     # Not needed if you setup a migration system like Alembic
#     await create_db_and_tables()https://github.com/bellingcat/auto-archiver/tree/dockerize
    models.Base.metadata.create_all(bind=engine)

#### helper methods
def authenticate_user(access_token):
    # https://cloud.google.com/docs/authentication/token-types#access
    if type(access_token)!=str or len(access_token)<10: return False, "invalid access_token"
    r = requests.get("https://oauth2.googleapis.com/tokeninfo", {"access_token":access_token})
    if r.status_code!=200: return False, "error occurred"
    try:
        j = r.json()
        if j.get("azp") != GOOGLE_CHROME_APP_ID and j.get("aud")!=GOOGLE_CHROME_APP_ID: 
            return False, f"token does not belong to correct APP_ID"
        # if j.get("email") not in ALLOWED_EMAILS: 
        if not custom_is_email_allowed(j.get("email"), any_bellingcat_email=True):
            return False, f"email '{j.get('email')}' not allowed"
        if j.get("email_verified") != "true": 
            return False, f"email '{j.get('email')}' not verified"
        if int(j.get("expires_in", -1)) <= 0:
            return False, "Token expired"
        return True, j.get('email')
    except Exception as e:
        logger.warning(f"EXCEPTION occurred: {e}")
        return False, f"EXCEPTION occurred"

def custom_is_email_allowed(email, any_bellingcat_email=False):
    return email in ALLOWED_EMAILS or (any_bellingcat_email and re.match(r'^[\w.]+@bellingcat\.com$', email))

def validate_user_get_email(access_token):
    valid_user, info = authenticate_user(access_token)
    if valid_user != True:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=info
        )
    return info