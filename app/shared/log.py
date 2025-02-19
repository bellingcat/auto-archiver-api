import traceback
from loguru import logger


# logging configurations
logger.add("logs/api_logs.log", retention="30 days")
logger.add("logs/error_logs.log", retention="30 days", level="ERROR")

    
def log_error(e: Exception, traceback_str: str = None, extra:str = ""):
    if not traceback_str: traceback_str = traceback.format_exc()
    if extra: extra = f"{extra}\n"
    logger.error(f"{extra}{e.__class__.__name__}: {e}\n{traceback_str}")
