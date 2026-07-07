from http import HTTPStatus
from typing import Dict

from cachetools import TTLCache
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from app.shared.schemas import ActiveUser, UsageResponse
from app.shared.user_groups import GroupInfo
from app.web.config import BREAKING_CHANGES, VERSION
from app.web.db.user_state import UserState
from app.web.security import get_user_state
from app.web.utils.cache import cached_endpoint


router = APIRouter()

# Response caches for hot, rarely-changing endpoints. User-scoped caches are
# keyed by the authenticated user's email so responses are never shared across
# users. TTLs are short enough that stale data self-corrects quickly.
HOME_CACHE = TTLCache(maxsize=1, ttl=300)
USER_PERMISSIONS_CACHE = TTLCache(maxsize=1024, ttl=300)
USER_USAGE_CACHE = TTLCache(maxsize=1024, ttl=60)


@router.get("/")
@cached_endpoint(HOME_CACHE, key=lambda: "home")
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
@cached_endpoint(USER_PERMISSIONS_CACHE, key=lambda user: user.email)
def get_user_permissions(
    user: UserState = Depends(get_user_state),
) -> Dict[str, GroupInfo]:
    return user.permissions


@router.get(
    "/user/usage",
    summary="Get the user's monthly URLs/MBs usage along with the total active sheets, breakdown by group.",
)
@cached_endpoint(USER_USAGE_CACHE, key=lambda user: user.email)
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
