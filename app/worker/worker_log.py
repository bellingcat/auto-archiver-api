import sys

from app.shared.log import logger
from app.shared.task_messaging import get_celery


celery = get_celery("worker")


def setup_celery_logger(c):
    # Remove Celery's default handlers to prevent duplicate logs
    celery_logger = c.log.get_default_logger()
    for handler in celery_logger.handlers[:]:
        celery_logger.removeHandler(handler)

    # Redirect Celery logs to Loguru
    class InterceptHandler:
        @staticmethod
        def write(message):
            if message.strip():
                msg = message.strip()
                # TODO: serialize to include extra information
                with logger.contextualize(worker=True):
                    logger.info(msg)

        # Required to prevent issues with buffered output
        @staticmethod
        def flush():
            pass

        @staticmethod
        def isatty():
            return False

    sys.stdout = InterceptHandler()
    sys.stderr = InterceptHandler()
