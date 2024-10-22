import traceback
from loguru import logger
from fastapi import Request


# logging configurations
logger.add("logs/api_logs.log", retention="30 days", rotation="3 days")
error_logger = logger.add("logs/error_logs.log", retention="30 days")

    
def log_error(e: Exception, traceback_str: str = None, extra:str = ""):
    # EXCEPTION_COUNTER.labels(type(e).__name__).inc()
    if not traceback_str: traceback_str = traceback.format_exc()
    if extra: extra = f"{extra}\n"
    logger.error(f"{extra}{e.__class__.__name__}: {e}")
    error_logger.error(f"{extra}{e.__class__.__name__}: {e}\n{traceback_str}")

async def logging_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        logger.info(f"{request.client.host}:{request.client.port} {request.method} {request.url._url} - HTTP {response.status_code}")
        return response
    except Exception as e:
        from utils.metrics import EXCEPTION_COUNTER
        EXCEPTION_COUNTER.labels(type(e).__name__).inc()
        log_error(e)
        raise e