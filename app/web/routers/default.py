from http import HTTPStatus
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from app.shared.schemas import ActiveUser, UsageResponse
from app.shared.user_groups import GroupInfo
from app.web.config import BREAKING_CHANGES, VERSION
from app.web.db.user_state import UserState
from app.web.security import get_user_state


router = APIRouter()


@router.get("/")
async def home() -> JSONResponse:
    return JSONResponse(
        {"version": VERSION, "breakingChanges": BREAKING_CHANGES}
    )


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@router.get(
    "/user/active", summary="Check if the user is active and can use the tool."
)
async def active(
    user: UserState = Depends(get_user_state),
) -> ActiveUser:
    return ActiveUser(active=user.active)


@router.get(
    "/user/permissions",
    summary="Get the user's global 'all' permissions and the permissions for each group they belong to.",
)
def get_user_permissions(
    user: UserState = Depends(get_user_state),
) -> Dict[str, GroupInfo]:
    return user.permissions


@router.get(
    "/user/usage",
    summary="Get the user's monthly URLs/MBs usage along with the total active sheets, breakdown by group.",
)
def get_user_usage(
    user: UserState = Depends(get_user_state),
) -> UsageResponse:
    if not user.active:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="User is not active."
        )
    return user.usage()


@router.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse("app/web/static/favicon.ico")
