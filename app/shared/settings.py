
from functools import lru_cache
import os
from fastapi_mail import ConnectionConfig
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Annotated, Set
from annotated_types import Len


class Settings(BaseSettings):
    
    model_config = SettingsConfigDict(env_file=os.environ.get("ENVIRONMENT_FILE") , env_file_encoding='utf-8', extra='ignore', str_strip_whitespace=True)

	# general
    SERVE_LOCAL_ARCHIVE: str = ""
    USER_GROUPS_FILENAME: str = "user-groups.yaml"
    SHEET_ORCHESTRATION_YAML : str = "secrets/orchestration-sheet.yaml"
    
    # cronjobs
    #TODO: disable by default?
    CRON_ARCHIVE_SHEETS: bool = False
    CRON_DELETE_STALE_SHEETS: bool = True
    DELETE_STALE_SHEETS_DAYS: int = 14
    CRON_DELETE_SCHEDULED_ARCHIVES: bool = True
    DELETE_SCHEDULED_ARCHIVES_NOTIFY_DAYS: int = 14

	# database
    DATABASE_PATH: str
    DATABASE_QUERY_LIMIT: int = 100
    @property
    def ASYNC_DATABASE_PATH(self) -> str:
        return self.DATABASE_PATH.replace("sqlite://", "sqlite+aiosqlite://")

    # redis
    REDIS_PASSWORD: str = ""
    REDIS_HOSTNAME: str = "localhost"
    @property
    def CELERY_BROKER_URL(self)-> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOSTNAME}:6379"
        return f"redis://{self.REDIS_HOSTNAME}:6379"
    REDIS_EXCEPTIONS_CHANNEL: str = "exceptions-channel"
    
	# observability
    REPEAT_COUNT_METRICS_SECONDS: int = 30

	# security
    API_BEARER_TOKEN: Annotated[str, Len(min_length=20)]
    ALLOWED_ORIGINS: Annotated[Set[str], Len(min_length=1)]
    CHROME_APP_IDS: Annotated[Set[Annotated[str, Len(min_length=10)]], Len(min_length=1)]
    #TODO: deprecate blocklist?
    BLOCKED_EMAILS: Annotated[Set[str], Len(min_length=0)] = set()

    # email configuration, if needed
    MAIL_FROM: str = "noreply@bellingcat.com"
    MAIL_FROM_NAME: str = "Bellingcat's Auto Archiver"
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_SERVER: str = ""
    MAIL_PORT: int = 587
    MAIL_STARTTLS: bool = False
    MAIL_SSL_TLS: bool = True
    @property
    def MAIL_CONFIG(self) -> str:
        return ConnectionConfig(
            MAIL_FROM=self.MAIL_FROM,
            MAIL_FROM_NAME=self.MAIL_FROM_NAME,
            MAIL_USERNAME=self.MAIL_USERNAME,
            MAIL_PASSWORD=self.MAIL_PASSWORD,
            MAIL_SERVER=self.MAIL_SERVER,
            MAIL_PORT=self.MAIL_PORT,
            MAIL_STARTTLS=self.MAIL_STARTTLS,
            MAIL_SSL_TLS=self.MAIL_SSL_TLS,
        )


@lru_cache
def get_settings():
    return Settings()