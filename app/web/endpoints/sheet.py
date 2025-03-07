from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import exc
from sqlalchemy.orm import Session

from app.shared import schemas
from app.shared.db.database import get_db_dependency
from app.shared.db.models import Sheet
from app.shared.task_messaging import get_celery
from app.web.db import crud
from app.web.db.user_state import UserState
from app.web.security import get_user_state


sheet_router = APIRouter(
    prefix="/sheet", tags=["Google Spreadsheet operations"]
)

celery = get_celery()


@sheet_router.post(
    "/create",
    status_code=HTTPStatus.CREATED,
    summary="Store a new Google Sheet for regular archiving.",
)
def create_sheet(
    sheet: schemas.SheetAdd,
    user: UserState = Depends(get_user_state),
    db: Session = Depends(get_db_dependency),
) -> schemas.SheetResponse:
    if not user.in_group(sheet.group_id):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="User does not have access to this group.",
        )

    if not user.has_quota_monthly_sheets(sheet.group_id):
        raise HTTPException(
            status_code=HTTPStatus.TOO_MANY_REQUESTS,
            detail="User has reached their sheet quota for this group.",
        )

    if not user.is_sheet_frequency_allowed(sheet.group_id, sheet.frequency):
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail="Invalid frequency selected for this group.",
        )

    try:
        return crud.create_sheet(
            db,
            sheet.id,
            sheet.name,
            user.email,
            sheet.group_id,
            sheet.frequency,
        )
    except exc.IntegrityError as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Sheet with this ID is already being archived.",
        ) from e


@sheet_router.get(
    "/mine",
    status_code=HTTPStatus.OK,
    summary="Get the authenticated user's Google Sheets.",
)
def get_user_sheets(
    user: UserState = Depends(get_user_state),
    db: Session = Depends(get_db_dependency),
) -> list[Sheet]:
    return crud.get_user_sheets(db, user.email)


@sheet_router.delete("/{sheet_id}", summary="Delete a Google Sheet by ID.")
def delete_sheet(
    sheet_id: str,
    user: UserState = Depends(get_user_state),
    db: Session = Depends(get_db_dependency),
) -> JSONResponse:
    return JSONResponse(
        {"id": sheet_id, "deleted": crud.delete_sheet(db, sheet_id, user.email)}
    )


@sheet_router.post(
    "/{sheet_id}/archive",
    status_code=HTTPStatus.CREATED,
    summary="Trigger an archiving task for a GSheet you own.",
    response_description="task_id for the archiving task.",
)
def archive_user_sheet(
    sheet_id: str,
    user: UserState = Depends(get_user_state),
    db: Session = Depends(get_db_dependency),
) -> JSONResponse:
    sheet = crud.get_user_sheet(db, user.email, sheet_id=sheet_id)
    if not sheet:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="No access to this sheet."
        )

    if not user.in_group(sheet.group_id):
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="User does not have access to this group.",
        )

    if not user.can_manually_trigger(sheet.group_id):
        raise HTTPException(
            status_code=HTTPStatus.TOO_MANY_REQUESTS,
            detail="User cannot manually trigger sheet archiving in this group.",
        )

    group_queue = user.priority_group(sheet.group_id)
    task = celery.signature(
        "create_sheet_task",
        args=[
            schemas.SubmitSheet(
                sheet_id=sheet_id, author_id=user.email, group_id=sheet.group_id
            ).model_dump_json()
        ],
    ).apply_async(**group_queue)

    return JSONResponse({"id": task.id}, status_code=HTTPStatus.CREATED)
