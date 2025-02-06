
from typing import Dict
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from core.config import VERSION, BREAKING_CHANGES
from core.logging import log_error
from db import crud
from db.schemas import ActiveUser, UsageResponse
from db.database import get_db_dependency
from db.user_state import UserState
from web.security import get_user_auth, bearer_security, get_user_state
from shared.user_groups import GroupPermissions

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
async def active(
    user: UserState = Depends(get_user_state),
) -> ActiveUser:
    return {"active": user.active}


@default_router.get("/user/permissions", summary="Get the user's global 'all' permissions and the permissions for each group they belong to.")
def get_user_permissions(
    user: UserState = Depends(get_user_state),
) -> Dict[str, GroupPermissions]:
    return user.permissions

@default_router.get("/user/usage", summary="Get the user's monthly URLs/MBs usage along with the total active sheets, breakdown by group.")
def get_user_usage(
    user: UserState = Depends(get_user_state),
) -> UsageResponse:
    if not user.active:
        raise HTTPException(status_code=403, detail="User is not active.")
    return user.usage()
    


@default_router.get('/favicon.ico', include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse("static/favicon.ico")
