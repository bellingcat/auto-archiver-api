
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from core.config import VERSION, BREAKING_CHANGES
from core.logging import log_error
from db import crud, schemas
from db.database import get_db_dependency
from db.user_state import UserState
from web.security import get_user_auth, bearer_security, get_active_user_state

default_router = APIRouter()


@default_router.get("/")
async def home(request: Request):
    # TODO: maybe split into 2 routes: one non authenticated and one authenticated for the groups info only
    status = {"version": VERSION, "breakingChanges": BREAKING_CHANGES}
    try:
        email = await get_user_auth(await bearer_security(request))
        status["groups"] = crud.get_user_groups(email)
    except HTTPException: pass  # not authenticated is fine
    except Exception as e: log_error(e)
    return JSONResponse(status)


@default_router.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


@default_router.get("/user/active", summary="Check if the user is active and can use the tool.")
# TODO: reorder db dependencies to after auth
async def active(db: Session = Depends(get_db_dependency), email=Depends(get_user_auth)) -> schemas.ActiveUser:
    return {"active": crud.is_active_user(db, email)}


@default_router.get("/groups")
def get_user_groups(email=Depends(get_user_auth)) -> list[str]:
    return crud.get_user_groups(email)


@default_router.get("/permissions")
def get_user_groups(
        user: UserState = Depends(get_active_user_state),
) -> list[str]:
    return JSONResponse({
        "groups": user.user_groups_names,
        "allowedFrequencies": list(user.allowed_frequencies),
        "sheet_quota": user.sheet_quota,
        "max_monthly_urls": user.max_monthly_urls, #TODO
        "max_monthly_mbs": user.max_monthly_mbs, # TODO
        #TODO: should this return 
    })


@default_router.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.ico")
