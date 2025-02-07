
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Annotated, Set
from annotated_types import Len


class Settings(BaseSettings):
    model_config = ConfigDict(extra='ignore', str_strip_whitespace=True)
    
	# general
    SERVE_LOCAL_ARCHIVE: str = ""
    USER_GROUPS_FILENAME: str = "user-groups.yaml"
    SHEET_ORCHESTRATION_YAML : str = "secrets/orchestration-sheet.yaml"
    
    # cronjobs
    CRON_ARCHIVE_SHEETS: bool = False

	# database
    DATABASE_PATH: str
    DATABASE_QUERY_LIMIT: int = 100
    @property
    def ASYNC_DATABASE_PATH(self) -> str:
        return self.DATABASE_PATH.replace("sqlite://", "sqlite+aiosqlite://")

    # redis
    CELERY_BROKER_URL: str = "redis://localhost:6379"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379"
    REDIS_EXCEPTIONS_CHANNEL: str = "exceptions-channel"
    
	# observability
    REPEAT_COUNT_METRICS_SECONDS: int = 30

	# security
    API_BEARER_TOKEN: Annotated[str, Len(min_length=20)]
    ALLOWED_ORIGINS: Annotated[set[str], Len(min_length=1)]
    CHROME_APP_IDS: Annotated[set[Annotated[str, Len(min_length=10)]], Len(min_length=1)]
    #TODO: deprecate blocklist?
    BLOCKED_EMAILS: Annotated[Set[str], Len(min_length=0)] = set()

@lru_cache
def get_settings():
    return Settings()