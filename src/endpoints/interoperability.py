import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from auto_archiver import Metadata
import sqlalchemy

from core.config import ALLOW_ANY_EMAIL
from web.security import token_api_key_auth
from db import models, schemas
from worker.main import insert_result_into_db, get_all_urls, get_store_until
from core.logging import log_error


interoperability_router = APIRouter(prefix="/interop", tags=["Interoperability endpoints."])


# ----- endpoint to submit data archived elsewhere
@interoperability_router.post("/submit-archive", status_code=201, summary="Submit a manual archive entry, for data that was archived elsewhere.")
def submit_manual_archive(
    manual: schemas.SubmitManualArchive,
    auth=Depends(token_api_key_auth)
):
    result: Metadata = Metadata.from_json(manual.result)
    manual.author_id = manual.author_id or ALLOW_ANY_EMAIL
    manual.tags.add("manual")

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
            store_until=get_store_until(manual.group_id),
        )
        archive_id = insert_result_into_db(archive)
    except sqlalchemy.exc.IntegrityError as e:
        log_error(e)
        raise HTTPException(status_code=422, detail=f"Cannot insert into DB due to integrity error, likely duplicate urls.")
    return JSONResponse({"id": archive_id}, status_code=201)
