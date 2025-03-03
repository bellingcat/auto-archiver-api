import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger
from prometheus_fastapi_instrumentator import Instrumentator

from app.shared.settings import get_settings
from app.shared.task_messaging import get_celery
from app.web.config import API_DESCRIPTION, VERSION
from app.web.endpoints.default import default_router
from app.web.endpoints.interoperability import interoperability_router
from app.web.endpoints.sheet import sheet_router
from app.web.endpoints.task import task_router
from app.web.endpoints.url import url_router
from app.web.events import lifespan
from app.web.middleware import logging_middleware
from app.web.security import token_api_key_auth


celery = get_celery()


def app_factory():
    settings = get_settings()

    app = FastAPI(
        title="Auto-Archiver API",
        description=API_DESCRIPTION,
        version=VERSION,
        contact={
            "name": "GitHub",
            "url": "https://github.com/bellingcat/auto-archiver-api",
        },
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(logging_middleware)

    app.include_router(default_router)
    app.include_router(url_router)
    app.include_router(sheet_router)
    app.include_router(task_router)
    app.include_router(interoperability_router)

    # prometheus exposed in /metrics with authentication
    Instrumentator(
        should_group_status_codes=False,
        excluded_handlers=[
            "/metrics",
            "/health",
            "/openapi.json",
            "/favicon.ico",
        ],
    ).instrument(app).expose(app, dependencies=[Depends(token_api_key_auth)])

    if settings.SERVE_LOCAL_ARCHIVE:
        local_dir = settings.SERVE_LOCAL_ARCHIVE
        if not os.path.isdir(local_dir) and os.path.isdir(
            local_dir.replace("/app", ".")
        ):
            local_dir = local_dir.replace("/app", ".")
        if len(settings.SERVE_LOCAL_ARCHIVE) > 1 and os.path.isdir(local_dir):
            logger.warning(
                f"MOUNTing local archive, use this in development only {settings.SERVE_LOCAL_ARCHIVE}"
            )
            app.mount(
                settings.SERVE_LOCAL_ARCHIVE,
                StaticFiles(directory=local_dir),
                name=settings.SERVE_LOCAL_ARCHIVE,
            )

    return app
