
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from loguru import logger

from core.config import ALLOW_ANY_EMAIL
from web.security import get_token_or_user_auth
from db import schemas
from worker import create_sheet_task

sheet_router = APIRouter(prefix="/sheet", tags=["Google Spreadsheet operations"])


@sheet_router.post("/archive", status_code=201, summary="Submit a Google Sheet archive request, starts a sheet archiving task.", response_model=schemas.Task, response_description="task_id for the archiving task.")
def archive_sheet(sheet:schemas.SubmitSheet, email = Depends(get_token_or_user_auth)):
    logger.info(f"SHEET TASK for {sheet=}")
    if email == ALLOW_ANY_EMAIL:
        email = sheet.author_id or "api-endpoint"
    sheet.author_id = email
    if not sheet.sheet_name and not sheet.sheet_id:
        raise HTTPException(status_code=422, detail=f"sheet name or id is required")
    task = create_sheet_task.delay(sheet.model_dump_json())
    return JSONResponse({"id": task.id}, status_code=201)