from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import exc
from sqlalchemy.orm import Session

from app.shared.db import models
from app.shared.db.database import get_db_dependency
from app.shared.schemas import (
    DeleteResponse,
    SheetAdd,
    SheetResponse,
    SubmitSheet,
)
from app.shared.task_messaging import get_celery
from app.shared.utils.sheets import get_sheet_access_error
from app.web.config import ALLOW_ANY_EMAIL
from app.web.db import crud
from app.web.db.user_state import UserState
from app.web.security import get_token_or_user_auth, get_user_state
from app.web.utils.misc import convert_priority_to_queue_dict


router = APIRouter(prefix="/sheet", tags=["Google Spreadsheet operations"])

celery = get_celery()


@router.post(
    "/create",
    status_code=HTTPStatus.CREATED,
    summary="Store a new Google Sheet for regular archiving.",
)
def create_sheet(
    sheet: SheetAdd,
    user: UserState = Depends(get_user_state),
    db: Session = Depends(get_db_dependency),
) -> SheetResponse:
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

    # Check if the service account has write access to the Google Sheet
    group = (
        db.query(models.Group).filter(models.Group.id == sheet.group_id).first()
    )
    if group:
        access_error = get_sheet_access_error(
            group.orchestrator_sheet,
            group.service_account_email,
            sheet.id,
        )
        if access_error:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail=access_error,
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


@router.get(
    "/mine",
    status_code=HTTPStatus.OK,
    summary="Get the authenticated user's Google Sheets.",
)
def get_user_sheets(
    user: UserState = Depends(get_user_state),
    db: Session = Depends(get_db_dependency),
) -> list[SheetResponse]:
    return crud.get_user_sheets(db, user.email)


@router.delete("/{sheet_id}", summary="Delete a Google Sheet by ID.")
def delete_sheet(
    sheet_id: str,
    user: UserState = Depends(get_user_state),
    db: Session = Depends(get_db_dependency),
) -> DeleteResponse:
    return DeleteResponse(
        id=sheet_id, deleted=crud.delete_sheet(db, sheet_id, user.email)
    )


@router.post(
    "/{sheet_id}/archive",
    status_code=HTTPStatus.CREATED,
    summary="Trigger an archiving task for a GSheet you own, or any sheet with the API token.",
    response_description="task_id for the archiving task.",
)
def archive_user_sheet(
    sheet_id: str,
    email: str = Depends(get_token_or_user_auth),
    db: Session = Depends(get_db_dependency),
) -> JSONResponse:
    is_api_token = email == ALLOW_ANY_EMAIL

    if is_api_token:
        # API token can trigger any sheet
        sheet = crud.get_sheet_by_id(db, sheet_id)
        if not sheet:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND, detail="Sheet not found."
            )
        group_queue = convert_priority_to_queue_dict("high")
        author_id = sheet.author_id
    else:
        user = UserState(db, email)
        sheet = crud.get_user_sheet(db, user.email, sheet_id=sheet_id)
        if not sheet:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="No access to this sheet.",
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
        author_id = user.email

    # Check if the service account has write access to the Google Sheet
    group = (
        db.query(models.Group).filter(models.Group.id == sheet.group_id).first()
    )
    if group:
        access_error = get_sheet_access_error(
            group.orchestrator_sheet,
            group.service_account_email,
            sheet_id,
        )
        if access_error:
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail=access_error,
            )

    task = celery.signature(
        "create_sheet_task",
        args=[
            SubmitSheet(
                sheet_id=sheet_id, author_id=author_id, group_id=sheet.group_id
            ).model_dump_json()
        ],
    ).apply_async(**group_queue)

    return JSONResponse({"id": task.id}, status_code=HTTPStatus.CREATED)
