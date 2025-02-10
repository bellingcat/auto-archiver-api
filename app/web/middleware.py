
from loguru import logger
from fastapi import Request
from app.shared.log import log_error


async def logging_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        logger.info(f"{request.client.host}:{request.client.port} {request.method} {request.url._url} - HTTP {response.status_code}")
        return response
    except Exception as e:
        from web.utils.metrics import EXCEPTION_COUNTER
        EXCEPTION_COUNTER.labels(type=e.__class__.__name__).inc()
        logger.info(f"{request.client.host}:{request.client.port} {request.method} {request.url._url} - {e.__class__.__name__} {e}")
        log_error(e)
        raise e
