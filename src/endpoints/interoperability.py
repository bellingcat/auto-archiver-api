from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from auto_archiver import Metadata
from loguru import logger
import sqlalchemy

from security import token_api_key_auth
from db import models, schemas
from worker import insert_result_into_db


interoperability_router = APIRouter(prefix="/interop", tags=["Interoperability endpoints."])


# ----- endpoint to submit data archived elsewhere
@interoperability_router.post("/submit-archive", status_code=201, summary="Submit a manual archive entry, for data that was archived elsewhere.")
def submit_manual_archive(manual: schemas.SubmitManual, auth=Depends(token_api_key_auth)):
    result = Metadata.from_json(manual.result)
    logger.info(f"MANUAL SUBMIT {result.get_url()} {manual.author_id}")
    manual.tags.add("manual")
    try:
        archive_id = insert_result_into_db(result, manual.tags, manual.public, manual.group_id, manual.author_id, models.generate_uuid())
    except sqlalchemy.exc.IntegrityError as e:
        logger.error(e)
        raise HTTPException(status_code=422, detail=f"Cannot insert into DB due to integrity error")
    return JSONResponse({"id": archive_id})
