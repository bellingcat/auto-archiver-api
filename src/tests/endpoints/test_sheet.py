from datetime import datetime
import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from db.schemas import TaskResult


def test_endpoints_no_auth(client, test_no_auth):
    test_no_auth(client.post, "/sheet/create")
    test_no_auth(client.get, "/sheet/mine")
    test_no_auth(client.delete, "/sheet/123-sheet-id")
    test_no_auth(client.post, "/sheet/123-sheet-id/archive")
    test_no_auth(client.post, "/sheet/archive")


def test_create_sheet_endpoint(app_with_auth, db_session):
    client_with_auth = TestClient(app_with_auth)
    good_data = {
        "id": "123-sheet-id",
        "name": "Test Sheet",
        "group_id": "spaceship",
        "frequency": "daily"
    }

    # with good data
    response = client_with_auth.post("/sheet/create", json=good_data)
    assert response.status_code == 201
    j = response.json()
    assert datetime.fromisoformat(j.pop("created_at"))
    assert datetime.fromisoformat(j.pop("last_url_archived_at"))
    assert j.pop("author_id") == 'morty@example.com'
    assert j == good_data

    # already exists
    response = client_with_auth.post("/sheet/create", json=good_data)
    assert response.status_code == 400
    assert response.json() == {"detail": "Sheet with this ID is already being archived."}

    # bad group
    bad_data = good_data.copy()
    bad_data["group_id"] = "not a group"
    response = client_with_auth.post("/sheet/create", json=bad_data)
    assert response.status_code == 403
    assert response.json() == {"detail": "User does not have access to this group."}

    # switch to jerry who's got less quota/permissions
    from web.security import get_user_state
    from db.user_state import UserState
    app_with_auth.dependency_overrides[get_user_state] = lambda: UserState(db_session, "jerry@example.com")
    client_jerry = TestClient(app_with_auth)

    # frequency not allowed
    jerry_data = good_data.copy()
    jerry_data["group_id"] = "animated-characters"
    jerry_data["frequency"] = "hourly"
    jerry_data["id"] = "jerry-sheet-id"
    response = client_jerry.post("/sheet/create", json=jerry_data)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid frequency selected for this group."}

    jerry_data["frequency"] = "daily"
    # success for the first sheet, bad quota on second
    response = client_jerry.post("/sheet/create", json=jerry_data)
    assert response.status_code == 201

    response = client_jerry.post("/sheet/create", json=jerry_data)
    assert response.status_code == 429
    assert response.json() == {"detail": "User has reached their sheet quota for this group."}


def test_get_user_sheets_endpoint(client_with_auth, db_session):
    # no data
    response = client_with_auth.get("/sheet/mine")
    assert response.status_code == 200
    assert response.json() == []

    # with data
    from db import models
    db_session.add(
        models.Sheet(id="123", name="Test Sheet 1", author_id="morty@example.com", group_id="spaceship", frequency="hourly")
    )
    db_session.commit()
    db_session.add_all([
        models.Sheet(id="456", name="Test Sheet 2", author_id="morty@example.com", group_id="interdimensional", frequency="daily"),
        models.Sheet(id="789", name="Test Sheet 3", author_id="rick@example.com", group_id="interdimensional", frequency="hourly"),
    ])
    db_session.commit()

    response = client_with_auth.get("/sheet/mine")
    assert response.status_code == 200
    r = response.json()
    assert isinstance(r, list)
    assert len(r) == 2
    assert datetime.fromisoformat(r[0].pop("created_at"))
    assert datetime.fromisoformat(r[0].pop("last_url_archived_at"))
    assert datetime.fromisoformat(r[1].pop("created_at"))
    assert datetime.fromisoformat(r[1].pop("last_url_archived_at"))
    assert r[0] == {
        'id': '123',
        'author_id': 'morty@example.com',
        'frequency': 'hourly',
        'group_id': 'spaceship',
        'name': 'Test Sheet 1',
    }
    assert r[1] == {
        'id': '456',
        'author_id': 'morty@example.com',
        'frequency': 'daily',
        'group_id': 'interdimensional',
        'name': 'Test Sheet 2',
    }


def test_delete_sheet_endpoint(client_with_auth, db_session):
    # missing sheet
    response = client_with_auth.delete("/sheet/123-sheet-id")
    assert response.status_code == 200
    assert response.json() == {
        "id": "123-sheet-id",
        "deleted": False
    }

    # add sheets for deletion
    from db import models
    db_session.add_all([
        models.Sheet(id="123-sheet-id", name="Test Sheet 1", author_id="morty@example.com", group_id="interdimensional", frequency="daily"),
        models.Sheet(id="456-sheet-id", name="Test Sheet 2", author_id="rick@example.com", group_id="spaceship", frequency="hourly"),
    ])
    db_session.commit()

    # morty can delete his
    response = client_with_auth.delete("/sheet/123-sheet-id")
    assert response.status_code == 200
    assert response.json() == {"id": "123-sheet-id", "deleted": True}
    # but only once
    response = client_with_auth.delete("/sheet/123-sheet-id")
    assert response.status_code == 200
    assert response.json() == {"id": "123-sheet-id", "deleted": False}
    # and not rick's
    response = client_with_auth.delete("/sheet/456-sheet-id")
    assert response.status_code == 200
    assert response.json() == {"id": "456-sheet-id", "deleted": False}


class TestArchiveUserSheetEndpoint:
    @patch("worker.main.create_sheet_task.delay", return_value=TaskResult(id="123-taskid", status="PENDING", result=""))
    def test_normal_flow(self, m1, client_with_auth, db_session):
        from db import models
        db_session.add(models.Sheet(id="123-sheet-id", name="Test Sheet 1", author_id="morty@example.com", group_id="spaceship", frequency="hourly"))
        db_session.commit()
        r = client_with_auth.post("/sheet/123-sheet-id/archive")
        assert r.status_code == 201
        assert r.json() == {"id": "123-taskid"}
        m1.assert_called_once()

    def test_token_auth(self, client_with_token, test_no_auth):
        test_no_auth(client_with_token.post, "/sheet/123-sheet-id/archive")

    def test_missing_data(self, client_with_auth):
        r = client_with_auth.post("/sheet/123-sheet-id/archive")
        assert r.status_code == 403
        assert r.json() == {"detail": "No access to this sheet."}

    def test_no_access(self, client_with_auth, db_session):
        from db import models
        db_session.add(models.Sheet(id="123-sheet-id", name="Test Sheet 1", author_id="rick@example.com", group_id="spaceship", frequency="hourly"))
        db_session.commit()
        r = client_with_auth.post("/sheet/123-sheet-id/archive")
        assert r.status_code == 403
        assert r.json() == {"detail": "No access to this sheet."}

    def test_user_not_in_group(self, client_with_auth, db_session):
        from db import models
        db_session.add(models.Sheet(id="123-sheet-id", name="Test Sheet 1", author_id="morty@example.com", group_id="interdimensional", frequency="hourly"))
        db_session.commit()
        r = client_with_auth.post("/sheet/123-sheet-id/archive")
        assert r.status_code == 403
        assert r.json() == {"detail": "User does not have access to this group."}

    def test_user_cannot_manually_trigger(self, client_with_auth, db_session):
        from db import models
        db_session.add(models.Sheet(id="123-sheet-id", name="Test Sheet 1", author_id="morty@example.com", group_id="default", frequency="hourly"))
        db_session.commit()
        r = client_with_auth.post("/sheet/123-sheet-id/archive")
        assert r.status_code == 429
        assert r.json() == {"detail": "User cannot manually trigger sheet archiving in this group."}


class TestTokenArchiveEndpoint:

    def test_user_auth(self, client_with_auth, test_no_auth):
        test_no_auth(client_with_auth.post, "/sheet/archive")

    def test_missing_data(self, client_with_token):
        r = client_with_token.post("/sheet/archive", json={})
        assert r.status_code == 422
        assert r.json() == {"detail": "sheet id is required"}

    @patch("worker.main.create_sheet_task.delay", return_value=TaskResult(id="123-456-789", status="PENDING", result=""))
    def test_normal_flow(self, m1, client_with_token):

        # minimum data
        response = client_with_token.post("/sheet/archive", json={"sheet_id": "123-sheet-id"})
        assert response.status_code == 201
        assert response.json() == {'id': '123-456-789'}

        m1.assert_called_once()
        called_val = m1.call_args.args[0]
        assert json.loads(called_val) == {"sheet_id": "123-sheet-id", "sheet_name": None, "public": False, "author_id": "api-endpoint", "group_id": None, "tags": [], "columns": {}, "header": 1}

        # maximum data
        response = client_with_token.post("/sheet/archive", json={"sheet_id": "123-sheet-id", "sheet_name": "768-sheet-name", "author_id": "birdman@example.com", "header": 2, "public": True, "group_id": "456-group-id", "tags": ["tag1"], "columns": {"col1": "type1"}})
        assert response.status_code == 201
        assert response.json() == {'id': '123-456-789'}

        m1.call_count == 2
        called_val = m1.call_args.args[0]
        assert json.loads(called_val) == {"sheet_id": "123-sheet-id", "sheet_name": "768-sheet-name", "public": True, "author_id": "birdman@example.com", "group_id": "456-group-id", "tags": ["tag1"], "columns": {"col1": "type1"}, "header": 2}
