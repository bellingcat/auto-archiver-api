import os
import pytest
from unittest.mock import patch
from shared.settings import Settings

@pytest.fixture(autouse=True)
def mock_logger_add():
    """Fixture to mock loguru.logger.add for all tests."""
    with patch('loguru.logger.add') as mock_add:
        yield mock_add  # This makes the mock available to tests

# @pytest.fixture(autouse=True)
# def settings():
#     return Settings(_env_file=".env.test")


@pytest.fixture(autouse=True)
def settings():
    with patch('shared.settings.Settings', return_value=Settings(_env_file=".env.test")) as mock_settings:
        yield mock_settings


@pytest.fixture()
def test_db(settings):
    from db.database import make_engine, make_session_local
    from db import models

    engine = make_engine(settings.DATABASE_PATH)

    if not os.path.exists(settings.DATABASE_PATH):
        open(settings.DATABASE_PATH, 'w').close()

    models.Base.metadata.create_all(engine)

    connection = engine.connect()
    yield connection
    connection.close()

    models.Base.metadata.drop_all(bind=engine)
    os.remove(settings.DATABASE_PATH)

# @pytest.fixture()
# def db_session(test_db):
#     session_local = make_session_local(test_db)
#     with session_local() as session:
#         yield session

# # create test data and insert it into the database
# def create_test_data():
#     from db.database import SessionLocal
#     from db.models import Task

#     db = SessionLocal()
#     task = Task(id="test-task-id", status="PENDING")
#     db.add(task)
#     db.commit()
#     db.refresh(task)
#     db.close()

#     return task.id