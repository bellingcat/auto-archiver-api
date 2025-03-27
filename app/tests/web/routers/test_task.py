from http import HTTPStatus
from unittest.mock import patch

from app.shared.constants import STATUS_FAILURE, STATUS_PENDING, STATUS_SUCCESS


def test_endpoint_task_status_no_auth(client, test_no_auth):
    test_no_auth(client.get, "/task/test-task-id")


@patch("app.web.routers.task.AsyncResult")
def test_get_status_success(mock_async_result, client_with_auth):
    mock_async_result.return_value.status = STATUS_SUCCESS
    mock_async_result.return_value.result = {"data": "some result"}

    response = client_with_auth.get("/task/test-task-id")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "id": "test-task-id",
        "status": STATUS_SUCCESS,
        "result": {"data": "some result"},
    }


@patch("app.web.routers.task.AsyncResult")
def test_get_status_failure(mock_async_result, client_with_auth):
    mock_async_result.return_value.status = STATUS_FAILURE
    mock_async_result.return_value.result = Exception("Some error")

    response = client_with_auth.get("/task/test-task-id")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "id": "test-task-id",
        "status": STATUS_FAILURE,
        "result": {"error": "Some error"},
    }


@patch("app.web.routers.task.AsyncResult")
def test_get_status_pending(mock_async_result, client_with_auth):
    mock_async_result.return_value.status = STATUS_PENDING
    mock_async_result.return_value.result = None

    response = client_with_auth.get("/task/test-task-id")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "id": "test-task-id",
        "status": STATUS_PENDING,
        "result": None,
    }
