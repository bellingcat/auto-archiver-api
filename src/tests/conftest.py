import pytest
from unittest.mock import patch
from sqlalchemy import create_engine

# from sqlalchemy_utils import create_database, database_exists, drop_database
from sqlalchemy.orm import sessionmaker

@pytest.fixture(autouse=True)
def mock_logger_add():
    """Fixture to mock loguru.logger.add for all tests."""
    with patch('loguru.logger.add') as mock_add:
        yield mock_add  # This makes the mock available to tests

@pytest.fixture(autouse=True)
def mock_database_url():
    with patch('core.config.SQLALCHEMY_DATABASE_URL', "sqlite:////app/auto-archiver.test.db") as mock_wb_url:
        yield mock_wb_url
