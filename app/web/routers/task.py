from celery.result import AsyncResult
from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.shared import schemas
from app.shared.log import log_error
from app.shared.task_messaging import get_celery
from app.web.security import get_token_or_user_auth
from app.web.utils.misc import custom_jsonable_encoder


router = APIRouter(prefix="/task", tags=["Async task operations"])

celery = get_celery()


@router.get(
    "/{task_id}",
    summary="Check the status of an async task by its id, works for URLs and Sheet tasks.",
)
def get_status(
    task_id, email=Depends(get_token_or_user_auth)
) -> schemas.TaskResult:
    task = AsyncResult(task_id, app=celery)
    try:
        if task.status == "FAILURE":
            # *FAILURE* The task raised an exception, or has exceeded the retry limit.
            # The :attr:`result` attribute then contains the exception raised by
            # the task.
            # https://docs.celeryq.dev/en/stable/_modules/celery/result.html#AsyncResult
            raise task.result

        response = {"id": task_id, "status": task.status, "result": task.result}
        return JSONResponse(
            jsonable_encoder(
                response,
                exclude_unset=True,
                custom_encoder={bytes: custom_jsonable_encoder},
            )
        )

    except Exception as e:
        log_error(e)
        return JSONResponse(
            {"id": task_id, "status": "FAILURE", "result": {"error": str(e)}}
        )
