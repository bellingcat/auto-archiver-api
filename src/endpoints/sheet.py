
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from sqlalchemy import exc
from sqlalchemy.orm import Session

from db.user_state import UserState
from web.security import token_api_key_auth, get_user_state
from db import schemas, crud
from db.database import get_db_dependency
from worker.main import create_sheet_task

sheet_router = APIRouter(prefix="/sheet", tags=["Google Spreadsheet operations"])


@sheet_router.post("/create", status_code=201, summary="Store a new Google Sheet for regular archiving.")
def create_sheet(
    sheet: schemas.SheetAdd,
    user: UserState = Depends(get_user_state),
    db: Session = Depends(get_db_dependency),
) -> schemas.SheetResponse:

    if not user.in_group(sheet.group_id):
        raise HTTPException(status_code=403, detail="User does not have access to this group.")

    if not user.has_quota_monthly_sheets(sheet.group_id):
        raise HTTPException(status_code=429, detail="User has reached their sheet quota for this group.")

    if not user.is_sheet_frequency_allowed(sheet.group_id, sheet.frequency):
        raise HTTPException(status_code=422, detail="Invalid frequency selected for this group.")

    try:
        return crud.create_sheet(db, sheet.id, sheet.name, user.email, sheet.group_id, sheet.frequency)
    except exc.IntegrityError as e:
        raise HTTPException(status_code=400, detail="Sheet with this ID is already being archived.") from e


@sheet_router.get("/mine", status_code=200, summary="Get the authenticated user's Google Sheets.")
def get_user_sheets(
    user: UserState = Depends(get_user_state),
    db: Session = Depends(get_db_dependency)
) -> list[schemas.SheetResponse]:
    return crud.get_user_sheets(db, user.email)


@sheet_router.delete("/{id}", summary="Delete a Google Sheet by ID.")
def delete_sheet(
    id: str,
    user: UserState = Depends(get_user_state),
    db: Session = Depends(get_db_dependency),
) -> schemas.TaskDelete:
    return JSONResponse({
        "id": id,
        "deleted": crud.delete_sheet(db, id, user.email)
    })


@sheet_router.post("/{id}/archive", status_code=201, summary="Trigger an archiving task for a GSheet you own.", response_description="task_id for the archiving task.")
def archive_user_sheet(
    id: str,
    user: UserState = Depends(get_user_state),
    db: Session = Depends(get_db_dependency),
) -> schemas.Task:

    sheet = crud.get_user_sheet(db, user.email, sheet_id=id)
    if not sheet:
        raise HTTPException(status_code=403, detail="No access to this sheet.")

    if not user.in_group(sheet.group_id):
        raise HTTPException(status_code=403, detail="User does not have access to this group.")

    if not user.can_manually_trigger(sheet.group_id):
        raise HTTPException(status_code=429, detail="User cannot manually trigger sheet archiving in this group.")

    task = create_sheet_task.delay(schemas.SubmitSheet(sheet_id=id, author_id=user.email, group=sheet.group_id).model_dump_json())

    return JSONResponse({"id": task.id}, status_code=201)


@sheet_router.post("/archive", status_code=201, summary="Trigger an archiving task for any GSheet with an API token.", response_description="task_id for the archiving task.")
def archive_sheet(
    sheet: schemas.SubmitSheet,
    auth=Depends(token_api_key_auth)
) -> schemas.Task:
    sheet.author_id = sheet.author_id or "api-endpoint"
    if not sheet.sheet_id:
        raise HTTPException(status_code=422, detail=f"sheet id is required")
    task = create_sheet_task.delay(sheet.model_dump_json())
    return JSONResponse({"id": task.id}, status_code=201)
