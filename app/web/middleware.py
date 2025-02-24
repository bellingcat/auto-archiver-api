import traceback

from fastapi import Request
from loguru import logger

from app.shared.log import log_error
from app.web.utils.metrics import EXCEPTION_COUNTER


async def logging_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        # TODO: use Origin to have summary prometheus metrics on where requests come from
        # origin = request.headers.get("origin")
        logger.info(
            f"{request.client.host}:{request.client.port} {request.method} {request.url._url} - HTTP {response.status_code}"
        )
        return response
    except Exception as e:
        location = f"{request.method} {request.url._url}"
        await increase_exceptions_counter(e, location)
        logger.info(
            f"{request.client.host}:{request.client.port} {location} - {e.__class__.__name__} {e}"
        )
        raise e


async def increase_exceptions_counter(e: Exception, location: str = "cronjob"):
    if location == "cronjob":
        try:
            last_trace = traceback.extract_tb(e.__traceback__)[-1]
            _file, _line, func_name, _text = last_trace
            location = func_name
        except Exception as e:
            logger.error(
                f"Unable to get function name from cronjob exception traceback: {e}"
            )
    EXCEPTION_COUNTER.labels(type=e.__class__.__name__, location=location).inc()
    log_error(e)
