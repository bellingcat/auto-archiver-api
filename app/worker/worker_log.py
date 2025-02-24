import sys

from loguru import logger

from app.shared.task_messaging import get_celery


celery = get_celery("worker")


def setup_celery_logger(celery):
    # Remove Celery's default handlers to prevent duplicate logs
    celery_logger = celery.log.get_default_logger()
    for handler in celery_logger.handlers[:]:
        celery_logger.removeHandler(handler)

    # Set up Loguru logging
    logger.add("logs/celery_logs.log", retention="30 days", level="DEBUG")
    logger.add("logs/celery_error_logs.log", retention="30 days", level="ERROR")

    # Redirect Celery logs to Loguru
    class InterceptHandler:
        def write(self, message):
            if message.strip():
                logger.info(message.strip())

        # Required to prevent issues with buffered output
        def flush(self):
            pass

        def isatty(self):
            return False

    sys.stdout = InterceptHandler()
    sys.stderr = InterceptHandler()
