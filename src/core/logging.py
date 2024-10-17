from loguru import logger
from fastapi import Request
from utils.metrics import EXCEPTION_COUNTER


# logging configurations
logger.add("logs/api_logs.log", retention="30 days", rotation="3 days")
async def logging_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        logger.info(f"{request.client.host}:{request.client.port} {request.method} {request.url._url} - HTTP {response.status_code}")
        return response
    except Exception as e:
        EXCEPTION_COUNTER.labels(type(e).__name__).inc()
        raise e