import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
import sqlalchemy
from auto_archiver.core import Metadata
from sqlalchemy.orm import Session

from app.shared.aa_utils import get_all_urls
from app.web.config import ALLOW_ANY_EMAIL
from app.shared import business_logic, schemas
from app.shared.db import worker_crud
from app.shared.db.database import get_db_dependency
from app.web.security import token_api_key_auth
from app.shared.db import models
from app.shared.log import log_error


interoperability_router = APIRouter(prefix="/interop", tags=["Interoperability endpoints."])


# ----- endpoint to submit data archived elsewhere
@interoperability_router.post("/submit-archive", status_code=201, summary="Submit a manual archive entry, for data that was archived elsewhere.")
def submit_manual_archive(
    manual: schemas.SubmitManualArchive,
    auth=Depends(token_api_key_auth),
    db: Session = Depends(get_db_dependency)
):
    try:
        result: Metadata = Metadata.from_json(manual.result)
    except json.JSONDecodeError as e:
        log_error(e)
        raise HTTPException(status_code=422, detail="Invalid JSON in result field.")
    manual.author_id = manual.author_id or ALLOW_ANY_EMAIL
    manual.tags.add("manual")

    try:
        store_until=business_logic.get_store_archive_until(db, manual.group_id)
    except AssertionError as e:
        log_error(e)
        raise HTTPException(status_code=422, detail=str(e))

    try:
        archive = schemas.ArchiveCreate(
            author_id=manual.author_id,
            url=result.get_url(),
            public=manual.public,
            group_id=manual.group_id,
            tags=manual.tags,
            id=models.generate_uuid(),
            result=json.loads(result.to_json()),
            urls=get_all_urls(result),
            store_until=store_until,
        )

        db_archive = worker_crud.store_archived_url(db, archive)
        logger.debug(f"[MANUAL ARCHIVE STORED] {db_archive.author_id} {db_archive.url}")
        return JSONResponse({"id": db_archive.id}, status_code=201)
    except sqlalchemy.exc.IntegrityError as e:
        log_error(e)
        raise HTTPException(status_code=422, detail=f"Cannot insert into DB due to integrity error, likely duplicate urls.")
