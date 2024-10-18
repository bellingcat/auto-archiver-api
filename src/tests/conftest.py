import os
from fastapi.testclient import TestClient
import pytest
from unittest.mock import patch
from shared.settings import Settings


@pytest.fixture(autouse=True)
def mock_logger_add():
    """Fixture to mock loguru.logger.add for all tests."""
    with patch('loguru.logger.add') as mock_add:
        yield mock_add  # This makes the mock available to tests


@pytest.fixture()
def settings():
    return Settings(_env_file=".env.test")


@pytest.fixture(autouse=True)
def mock_settings():
    with patch('shared.settings.Settings', return_value=Settings(_env_file=".env.test")) as mock_settings:
        yield mock_settings


@pytest.fixture()
def test_db(settings: Settings):
    from db.database import make_engine
    from db import models

    engine = make_engine(settings.DATABASE_PATH)

    fs = settings.DATABASE_PATH.replace("sqlite:///", "")
    if not os.path.exists(fs):
        open(fs, 'w').close()

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
    from db.database import make_session_local
    session_local = make_session_local(test_db)
    with session_local() as session:
        yield session


@pytest.fixture()
def app(db_session):
    from web.main import app_factory
    app = app_factory()
    return app


@pytest.fixture()
def client(app):
    client = TestClient(app)
    return client


@pytest.fixture()
def app_with_auth(app):
    from security import get_token_or_user_auth, get_user_auth
    app.dependency_overrides[get_token_or_user_auth] = lambda: "rick@example.com"
    app.dependency_overrides[get_user_auth] = lambda: "morty@example.com"
    return app


@pytest.fixture()
def client_with_auth(app_with_auth):
    client = TestClient(app_with_auth)
    return client
