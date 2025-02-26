import os
from typing import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.shared.db import models
from app.shared.db.database import (
    make_async_engine,
    make_async_session_local,
    make_engine,
    make_session_local,
)
from app.shared.settings import Settings
from app.web.config import ALLOW_ANY_EMAIL
from app.web.db import crud
from app.web.db.crud import get_user_group_names
from app.web.db.user_state import UserState
from app.web.main import app_factory
from app.web.security import (
    get_token_or_user_auth,
    get_user_auth,
    get_user_state,
    token_api_key_auth,
)


@pytest.fixture(autouse=True)
def mock_logger_add():
    """Fixture to mock loguru.logger.add for all tests."""
    with patch("loguru.logger.add") as mock_add:
        yield mock_add  # This makes the mock available to tests


@pytest.fixture()
def get_settings():
    return Settings(_env_file=".env.test")


@pytest.fixture(autouse=True)
def mock_settings():
    with patch(
        "app.shared.settings.Settings",
        return_value=Settings(_env_file=".env.test"),
    ) as mock_settings:
        yield mock_settings


@pytest.fixture()
def test_db(get_settings: Settings):
    get_user_group_names.cache_clear()
    make_engine.cache_clear()
    engine = make_engine(get_settings.DATABASE_PATH)

    fs = get_settings.DATABASE_PATH.replace("sqlite:///", "")
    if not os.path.exists(fs):
        open(fs, "w").close()

    models.Base.metadata.create_all(engine)

    connection = engine.connect()
    yield connection
    connection.close()

    models.Base.metadata.drop_all(bind=engine)
    for suffix in ["", "-wal", "-shm"]:
        new_fs = fs + suffix
        if os.path.exists(new_fs):
            os.remove(new_fs)


@pytest.fixture()
def db_session(test_db):
    session_local = make_session_local(test_db)
    with session_local() as session:
        yield session


@pytest_asyncio.fixture()
async def async_test_db(get_settings: Settings):
    get_user_group_names.cache_clear()
    engine = await make_async_engine(get_settings.ASYNC_DATABASE_PATH)

    fs = get_settings.ASYNC_DATABASE_PATH.replace("sqlite+aiosqlite:///", "")
    if not os.path.exists(fs):
        open(fs, "w").close()

    async def create_all():
        async with engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.create_all)

    await create_all()

    yield engine

    async def drop_all():
        async with engine.begin() as conn:
            await conn.run_sync(models.Base.metadata.drop_all)

    await drop_all()

    engine.dispose()
    for suffix in ["", "-wal", "-shm"]:
        new_fs = fs + suffix
        if os.path.exists(new_fs):
            os.remove(new_fs)


@pytest_asyncio.fixture()
async def async_db_session(
    async_test_db: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    session_local = await make_async_session_local(async_test_db)
    async with session_local() as session:
        yield session


@pytest.fixture()
def app(db_session):
    app = app_factory()
    crud.upsert_user_groups(db_session)
    return app


@pytest.fixture()
def client(app):
    client = TestClient(app)
    return client


@pytest.fixture()
def app_with_auth(app, db_session):
    app.dependency_overrides[get_token_or_user_auth] = (
        lambda: "rick@example.com"
    )
    app.dependency_overrides[get_user_auth] = lambda: "morty@example.com"
    app.dependency_overrides[get_user_state] = lambda: UserState(
        db_session, "MORTY@example.com"
    )
    return app


@pytest.fixture()
def client_with_auth(app_with_auth):
    client = TestClient(app_with_auth)
    return client


@pytest.fixture()
def app_with_token(app):
    app.dependency_overrides[token_api_key_auth] = lambda: ALLOW_ANY_EMAIL
    app.dependency_overrides[get_token_or_user_auth] = lambda: ALLOW_ANY_EMAIL
    return app


@pytest.fixture()
def client_with_token(app_with_token):
    client = TestClient(app_with_token)
    return client


@pytest.fixture()
def test_no_auth():
    # reusable code to ensure a method/endpoint combination is unauthorized
    def no_auth(http_method, endpoint):
        response = http_method(endpoint)
        assert response.status_code == 403
        assert response.json() == {"detail": "Not authenticated"}

    return no_auth
