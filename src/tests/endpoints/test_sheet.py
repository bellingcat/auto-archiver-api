import json
from unittest.mock import patch

from db.schemas import TaskResult


def test_sheet_no_auth(client, test_no_auth):
    test_no_auth(client.post, "/sheet/archive")


@patch("worker.main.create_sheet_task.delay", return_value=TaskResult(id="123-456-789", status="PENDING", result=""))
def test_sheet_rick(m1, client_with_auth):

    response = client_with_auth.post("/sheet/archive", json={"sheet_id": "123-sheet-id"})
    assert response.status_code == 201
    assert response.json() == {'id': '123-456-789'}

    m1.assert_called_once()
    called_val = m1.call_args.args[0]
    assert json.loads(called_val) == {"sheet_id": "123-sheet-id", "sheet_name": None, "public": False, "author_id": "rick@example.com", "group_id": None, "tags": [], "columns": {}, "header": 1}


def test_sheet_missing_sheet_data(client_with_auth):
    r = client_with_auth.post("/sheet/archive", json={})
    assert r.status_code == 422
    assert r.json() == {"detail": "sheet name or id is required"}


@patch("worker.main.create_sheet_task.delay", return_value=TaskResult(id="123-API-789", status="PENDING", result=""))
def test_sheet_api(m1, client):

    response = client.post("/sheet/archive", json={"sheet_name": "456-sheet_name-id"}, headers={"Authorization": "Bearer this_is_the_test_api_token"})
    assert response.status_code == 201
    assert response.json() == {'id': '123-API-789'}

    m1.assert_called_once()
    called_val = m1.call_args.args[0]
    assert json.loads(called_val) == {"sheet_name": "456-sheet_name-id", "sheet_id": None, "public": False, "author_id": "api-endpoint", "group_id": None, "tags": [], "columns": {}, "header": 1}

    response = client.post("/sheet/archive", json={"sheet_id": "456-sheet-id", "author_id": "custom-author"}, headers={"Authorization": "Bearer this_is_the_test_api_token"})
    assert response.status_code == 201
    assert response.json() == {'id': '123-API-789'}

    assert m1.call_count == 2
    called_val = m1.call_args.args[0]
    assert json.loads(called_val) == {"sheet_id": "456-sheet-id", "sheet_name": None, "public": False, "author_id": "custom-author", "group_id": None, "tags": [], "columns": {}, "header": 1}
