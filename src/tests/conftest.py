import pytest
import os
from unittest.mock import patch

@pytest.fixture(autouse=True)
def mock_logger_add():
    """Fixture to mock loguru.logger.add for all tests."""
    with patch('loguru.logger.add') as mock_add:
        yield mock_add  # This makes the mock available to tests

os.environ["CHROME_APP_IDS"] = 'test_app_id_1,test_app_id_2'
os.environ["DATABASE_PATH"] = "sqlite:////app/auto-archiver.test.db"
os.environ["BLOCKED_EMAILS"] = "blocked@example.com"