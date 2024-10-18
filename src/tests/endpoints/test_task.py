from unittest.mock import patch
from fastapi.testclient import TestClient


def setup_client():
    from main import app
    from security import get_token_or_user_auth
    async def mock_get_token_or_user_auth(): return "example@email.com"
    app.dependency_overrides[get_token_or_user_auth] = mock_get_token_or_user_auth
    return TestClient(app), app


@patch("endpoints.task.AsyncResult")
def test_get_status_success(mock_async_result):
    client, app = setup_client()

    mock_async_result.return_value.status = "SUCCESS"
    mock_async_result.return_value.result = {"data": "some result"}

    response = client.get("/task/test-task-id")

    assert response.status_code == 200
    assert response.json() == {
        "id": "test-task-id",
        "status": "SUCCESS",
        "result": {"data": "some result"}
    }
    app.dependency_overrides = {}


@patch("endpoints.task.AsyncResult")
def test_get_status_failure(mock_async_result):
    client, app = setup_client()

    mock_async_result.return_value.status = "FAILURE"
    mock_async_result.return_value.result = Exception("Some error")

    response = client.get("/task/test-task-id")

    assert response.status_code == 200
    assert response.json() == {
        "id": "test-task-id",
        "status": "FAILURE",
        "result": {"error": "Some error"}
    }
    app.dependency_overrides = {}


@patch("endpoints.task.AsyncResult")
def test_get_status_pending(mock_async_result):
    client, app = setup_client()

    mock_async_result.return_value.status = "PENDING"
    mock_async_result.return_value.result = None

    response = client.get("/task/test-task-id")

    assert response.status_code == 200
    assert response.json() == {
        "id": "test-task-id",
        "status": "PENDING",
        "result": None
    }
    app.dependency_overrides = {}
