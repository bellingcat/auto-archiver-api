
from loguru import logger
from fastapi import Request
from app.shared.log import log_error
from app.web.utils.metrics import EXCEPTION_COUNTER


async def logging_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        #TODO: use Origin to have summary prometheus metrics on where requests come from
        # origin = request.headers.get("origin")
        logger.info(f"{request.client.host}:{request.client.port} {request.method} {request.url._url} - HTTP {response.status_code}")
        return response
    except Exception as e:
        EXCEPTION_COUNTER.labels(type=e.__class__.__name__).inc()
        logger.info(f"{request.client.host}:{request.client.port} {request.method} {request.url._url} - {e.__class__.__name__} {e}")
        log_error(e)
        raise e
