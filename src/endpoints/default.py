
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from loguru import logger
from sqlalchemy.orm import Session

from core.config import VERSION, BREAKING_CHANGES
from db import crud
from db.database import get_db
from security import get_user_auth, bearer_security


default_router = APIRouter()


@default_router.get("/")
async def home(request: Request):
    # TODO: maybe split into 2 routes: one non authenticated and one authenticated for the groups info only
    status = {"version": VERSION, "breakingChanges": BREAKING_CHANGES}
    try:
        email = await get_user_auth(await bearer_security(request))
        db: Session = next(get_db())
        status["groups"] = crud.get_user_groups(db, email)
    except HTTPException: pass  # not authenticated is fine
    except Exception as e: logger.error(e)
    return JSONResponse(status)


@default_router.get("/health")
async def health(request: Request):
    return JSONResponse({"status": "ok"})

@default_router.get("/groups", response_model=list[str])
def get_user_groups(db: Session = Depends(get_db), email=Depends(get_user_auth)):
    return crud.get_user_groups(db, email)


@default_router.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.ico")
