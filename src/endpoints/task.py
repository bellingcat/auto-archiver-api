from celery.result import AsyncResult
from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from loguru import logger
from web.security import get_token_or_user_auth

from db import schemas
from core.logging import log_error
from worker import celery


task_router = APIRouter(prefix="/task", tags=["Async task operations"])


@task_router.get("/{task_id}", response_model=schemas.TaskResult, summary="Check the status of an async task by its id, works for URLs and Sheet tasks.")
def get_status(task_id, email=Depends(get_token_or_user_auth)):
    logger.info(f"status check for user {email} task {task_id}")
    task = AsyncResult(task_id, app=celery)
    try:
        if task.status == "FAILURE":
            # *FAILURE* The task raised an exception, or has exceeded the retry limit.
            # The :attr:`result` attribute then contains the exception raised by the task.
            # https://docs.celeryq.dev/en/stable/_modules/celery/result.html#AsyncResult
            raise task.result

        response = {
            "id": task_id,
            "status": task.status,
            "result": task.result
        }
        return JSONResponse(jsonable_encoder(response, exclude_unset=True))

    except Exception as e:
        log_error(e)
        return JSONResponse({
            "id": task_id,
            "status": "FAILURE",
            "result": {"error": str(e)}
        })
