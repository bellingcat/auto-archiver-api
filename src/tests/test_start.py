import pytest
from fastapi.testclient import TestClient
from core.config import VERSION

def test_mock_logger():
    from main import app

    client = TestClient(app)
    
    response = client.get("/")
    assert response.status_code == 200
    r = response.json()
    assert "version" in r and r["version"] == VERSION