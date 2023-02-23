from celery.result import AsyncResult
from fastapi import Body, FastAPI, Form, Request, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic.json import pydantic_encoder
from dotenv import load_dotenv
import json
import sys, traceback
from loguru import logger
# import os, requests

# from google.oauth2.credentials import Credentials
# from google_auth_oauthlib.flow import Flow
# from google_auth_oauthlib.flow import InstalledAppFlow
# from oauthlib.oauth2 import WebApplicationClient
from typing import Optional

from fastapi import Depends
# from fastapi.security import OAuth2PasswordRequestForm
# from fastapi.security import OAuth2AuthorizationCodeBearer

from auth.db import User, create_db_and_tables
# from app.schemas import UserCreate, UserRead, UserUpdate
from auth.users import (
    SECRET_KEY,
    auth_backend,
    current_active_user,
    fastapi_users,
    google_oauth_client,
)

from worker import create_task, create_archive_task, celery

load_dotenv()

app = FastAPI() 


# Configuration
# GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", None)
# GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", None)
# GOOGLE_DISCOVERY_URL = ("https://accounts.google.com/.well-known/openid-configuration")
# GOOGLE_LOGIN_CALLBACK = os.environ.get("GOOGLE_LOGIN_CALLBACK", "http://localhost:5000/login/callback")
# SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(24))

# Authentication logic for OAUTH2
app.include_router(
    fastapi_users.get_oauth_router(google_oauth_client, auth_backend, SECRET_KEY),
    prefix="/auth/google",
    tags=["auth"],
)

@app.get("/authenticated-route")
async def authenticated_route(user: User = Depends(current_active_user)):
    return {"message": f"Hello {user.email}!"}

# protected version
@app.post("/tasks-auth", status_code=201)
def run_task(payload = Body(...), user: User = Depends(current_active_user)):
    logger.info(f"new task for user {user.email}: {payload['url']}")
    # task_type = payload["type"]
    # task = create_task.delay(int(task_type))
    task = create_archive_task.delay(payload["url"])
    return JSONResponse({"task_id": task.id})

@app.get("/tasks-auth/{task_id}")
def get_status(task_id, user: User = Depends(current_active_user)):
    logger.info(f"status check for user {user.email}")
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


@app.on_event("startup")
async def on_startup():
    # Not needed if you setup a migration system like Alembic
    await create_db_and_tables()

####
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("home.html", context={"request": request})


#TODO: deprecate
# @app.post("/tasks", status_code=201)
# def run_task(payload = Body(...)):
#     # task_type = payload["type"]
#     # task = create_task.delay(int(task_type))
#     task = create_archive_task.delay(payload["url"])
#     return JSONResponse({"task_id": task.id})

# @app.get("/tasks/{task_id}")
# def get_status(task_id):
#     task_result = AsyncResult(task_id, app=celery)
#     result = {
#         "task_id": task_id,
#         "task_status": task_result.status,
#         "task_result": task_result.result
#     }
#     try:
#         json_result = jsonable_encoder(result)
#         # json_result = jsonable_encoder(result, custom_encoder=pydantic_encoder) # causes error
#         return JSONResponse(json_result)
#     except Exception as e:
#         logger.error(e)
#         logger.error(traceback.format_exc())
#         return JSONResponse({
#             "task_id": task_id,
#             "task_status": "FAILURE",
#         })
