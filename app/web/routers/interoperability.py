import json
from http import HTTPStatus

import sqlalchemy
from auto_archiver.core import Metadata
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.shared import business_logic, schemas
from app.shared.db import models, worker_crud
from app.shared.db.database import get_db_dependency
from app.shared.log import log_error, logger
from app.shared.utils.misc import get_all_urls
from app.web.config import ALLOW_ANY_EMAIL
from app.web.security import token_api_key_auth


router = APIRouter(prefix="/interop", tags=["Interoperability endpoints."])


# ----- endpoint to submit data archived elsewhere
@router.post(
    "/submit-archive",
    status_code=HTTPStatus.CREATED,
    summary="Submit a manual archive entry, for data that was archived elsewhere.",
)
def submit_manual_archive(
    manual: schemas.SubmitManualArchive,
    auth=Depends(token_api_key_auth),
    db: Session = Depends(get_db_dependency),
):
    try:
        result: Metadata = Metadata.from_json(manual.result)
    except json.JSONDecodeError as e:
        log_error(e)
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail="Invalid JSON in result field.",
        ) from e
    manual.author_id = manual.author_id or ALLOW_ANY_EMAIL
    manual.tags.add("manual")

    store_until = business_logic.get_store_archive_until_or_never(
        db, manual.group_id
    )
    logger.debug(
        f"[MANUAL ARCHIVE] {manual.author_id} {manual.url} {store_until}"
    )

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
        logger.debug(
            f"[MANUAL ARCHIVE STORED] {db_archive.author_id} {db_archive.url}"
        )
        return JSONResponse(
            {"id": db_archive.id}, status_code=HTTPStatus.CREATED
        )
    except sqlalchemy.exc.IntegrityError as e:
        log_error(e)
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail="Cannot insert into DB due to integrity error, likely duplicate urls.",
        ) from e
