from unittest.mock import patch
from fastapi.testclient import TestClient


@patch("endpoints.task.AsyncResult")
def test_get_status_success(mock_async_result, client):
    mock_async_result.return_value.status = "SUCCESS"
    mock_async_result.return_value.result = {"data": "some result"}

    response = client.get("/task/test-task-id")

    assert response.status_code == 200
    assert response.json() == {
        "id": "test-task-id",
        "status": "SUCCESS",
        "result": {"data": "some result"}
    }


@patch("endpoints.task.AsyncResult")
def test_get_status_failure(mock_async_result, client):

    mock_async_result.return_value.status = "FAILURE"
    mock_async_result.return_value.result = Exception("Some error")

    response = client.get("/task/test-task-id")

    assert response.status_code == 200
    assert response.json() == {
        "id": "test-task-id",
        "status": "FAILURE",
        "result": {"error": "Some error"}
    }


@patch("endpoints.task.AsyncResult")
def test_get_status_pending(mock_async_result, client):
    mock_async_result.return_value.status = "PENDING"
    mock_async_result.return_value.result = None

    response = client.get("/task/test-task-id")

    assert response.status_code == 200
    assert response.json() == {
        "id": "test-task-id",
        "status": "PENDING",
        "result": None
    }
