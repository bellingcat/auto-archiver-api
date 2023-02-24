from celery.result import AsyncResult
from fastapi import Body, FastAPI, Request, HTTPException, status, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
# from pydantic.json import pydantic_encoder
from dotenv import load_dotenv
import traceback, os, requests
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


app = FastAPI() 
app.mount("/static", StaticFiles(directory="static"), name="static")

def get_db():
    session = SessionLocal()
    try: yield session
    finally: session.close()

    
@app.get("/tasks/search", response_model=list[schemas.Task])
def search(access_token:str, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    validate_user_get_email(access_token)
    return crud.get_tasks(db, skip=skip, limit=limit)

@app.post("/tasks", status_code=201)
def run_task(payload = Body(...)):
    email = validate_user_get_email(payload["access_token"])
    logger.info(f"new task for user {email}: {payload['url']}")
    task = create_archive_task.delay(payload["url"])
    return JSONResponse({"task_id": task.id})

@app.get("/tasks/{task_id}")
def get_status(task_id, access_token:str):
    email = validate_user_get_email(access_token)
    logger.info(f"status check for user {email}")
    task_result = AsyncResult(task_id, app=celery)
    result = {
        "task_id": task_id,
        "task_status": task_result.status,
        "task_result": task_result.result
    }
    try:
        json_result = jsonable_encoder(result)
        # json_result = jsonable_encoder(result, custom_encoder=pydantic_encoder) # causes error
        return JSONResponse(json_result)
    except Exception as e:
        logger.error(e)
        logger.error(traceback.format_exc())
        return JSONResponse({
            "task_id": task_id,
            "task_status": "FAILURE",
        })





@app.get("/")
def home():
    return JSONResponse({"message": "Hello"})

@app.on_event("startup")
async def on_startup():
#     # Not needed if you setup a migration system like Alembic
#     await create_db_and_tables()
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
        if j.get("email") not in ALLOWED_EMAILS: 
            return False, f"email '{j.get('email')}' not in ALLOWED"
        if j.get("email_verified") != "true": 
            return False, f"email '{j.get('email')}' not verified"
        if int(j.get("expires_in", -1)) <= 0:
            return False, "Token expired"
        return True, j.get('email')
    except Exception as e:
        logger.warning(f"EXCEPTION occurred: {e}")
        return False, f"EXCEPTION occurred"

def validate_user_get_email(access_token):
    valid_user, info = authenticate_user(access_token)
    if valid_user != True:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=info
        )
    return info