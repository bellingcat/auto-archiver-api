import os
import traceback

from auto_archiver.utils.custom_logger import logger


# logging configurations
if not os.getenv("TESTING", "").lower() == "true":
    logger.add(
        "logs/all_logs.log", retention="60 days", format="{extra[serialized]}"
    )
    logger.add(
        "logs/all_error_logs.log",
        retention="120 days",
        level="ERROR",
        format="{extra[serialized]}",
    )


def log_error(e: Exception, traceback_str: str = None, extra: str = ""):
    if not traceback_str:
        traceback_str = traceback.format_exc()
    if extra:
        extra = f"{extra}\n"
    logger.error(f"{extra}{e.__class__.__name__}: {e}\n{traceback_str}")
