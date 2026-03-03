from datetime import datetime
from http import HTTPStatus
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.shared.constants import STATUS_PENDING
from app.shared.db import models
from app.shared.schemas import TaskResult
from app.web.db.user_state import UserState
from app.web.security import get_user_state


def test_endpoints_no_auth(client, test_no_auth):
    test_no_auth(client.post, "/sheet/create")
    test_no_auth(client.get, "/sheet/mine")
    test_no_auth(client.delete, "/sheet/123-sheet-id")
    test_no_auth(client.post, "/sheet/123-sheet-id/archive")


def test_create_sheet_endpoint(app_with_auth, db_session):
    client_with_auth = TestClient(app_with_auth)
    good_data = {
        "id": "123-sheet-id",
        "name": "Test Sheet",
        "group_id": "spaceship",
        "frequency": "daily",
    }

    # with good data
    response = client_with_auth.post("/sheet/create", json=good_data)
    assert response.status_code == HTTPStatus.CREATED
    j = response.json()
    assert datetime.fromisoformat(j.pop("created_at"))
    assert datetime.fromisoformat(j.pop("last_url_archived_at"))
    assert j.pop("author_id") == "morty@example.com"
    assert j == good_data

    # already exists
    response = client_with_auth.post("/sheet/create", json=good_data)
    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert response.json() == {
        "detail": "Sheet with this ID is already being archived."
    }

    # bad group
    bad_data = good_data.copy()
    bad_data["group_id"] = "not a group"
    response = client_with_auth.post("/sheet/create", json=bad_data)
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json() == {
        "detail": "User does not have access to this group."
    }

    # switch to jerry who's got less quota/permissions
    app_with_auth.dependency_overrides[get_user_state] = lambda: UserState(
        db_session, "jerry@example.com"
    )
    client_jerry = TestClient(app_with_auth)

    # frequency not allowed
    jerry_data = good_data.copy()
    jerry_data["group_id"] = "animated-characters"
    jerry_data["frequency"] = "hourly"
    jerry_data["id"] = "jerry-sheet-id"
    response = client_jerry.post("/sheet/create", json=jerry_data)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json() == {
        "detail": "Invalid frequency selected for this group."
    }

    jerry_data["frequency"] = "daily"
    # success for the first sheet, bad quota on second
    response = client_jerry.post("/sheet/create", json=jerry_data)
    assert response.status_code == HTTPStatus.CREATED

    response = client_jerry.post("/sheet/create", json=jerry_data)
    assert response.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert response.json() == {
        "detail": "User has reached their sheet quota for this group."
    }


def test_get_user_sheets_endpoint(client_with_auth, db_session):
    # no data
    response = client_with_auth.get("/sheet/mine")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == []

    # with data
    db_session.add(
        models.Sheet(
            id="123",
            name="Test Sheet 1",
            author_id="morty@example.com",
            group_id="spaceship",
            frequency="hourly",
        )
    )
    db_session.commit()
    db_session.add_all(
        [
            models.Sheet(
                id="456",
                name="Test Sheet 2",
                author_id="morty@example.com",
                group_id="interdimensional",
                frequency="daily",
            ),
            models.Sheet(
                id="789",
                name="Test Sheet 3",
                author_id="rick@example.com",
                group_id="interdimensional",
                frequency="hourly",
            ),
        ]
    )
    db_session.commit()

    response = client_with_auth.get("/sheet/mine")
    assert response.status_code == HTTPStatus.OK
    r = response.json()
    assert isinstance(r, list)
    assert len(r) == 2
    assert datetime.fromisoformat(r[0].pop("created_at"))
    assert datetime.fromisoformat(r[0].pop("last_url_archived_at"))
    assert datetime.fromisoformat(r[1].pop("created_at"))
    assert datetime.fromisoformat(r[1].pop("last_url_archived_at"))
    assert r[0] == {
        "id": "123",
        "author_id": "morty@example.com",
        "frequency": "hourly",
        "group_id": "spaceship",
        "name": "Test Sheet 1",
    }
    assert r[1] == {
        "id": "456",
        "author_id": "morty@example.com",
        "frequency": "daily",
        "group_id": "interdimensional",
        "name": "Test Sheet 2",
    }


def test_delete_sheet_endpoint(client_with_auth, db_session):
    # missing sheet
    response = client_with_auth.delete("/sheet/123-sheet-id")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"id": "123-sheet-id", "deleted": False}

    # add sheets for deletion
    db_session.add_all(
        [
            models.Sheet(
                id="123-sheet-id",
                name="Test Sheet 1",
                author_id="morty@example.com",
                group_id="interdimensional",
                frequency="daily",
            ),
            models.Sheet(
                id="456-sheet-id",
                name="Test Sheet 2",
                author_id="rick@example.com",
                group_id="spaceship",
                frequency="hourly",
            ),
        ]
    )
    db_session.commit()

    # morty can delete his
    response = client_with_auth.delete("/sheet/123-sheet-id")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"id": "123-sheet-id", "deleted": True}
    # but only once
    response = client_with_auth.delete("/sheet/123-sheet-id")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"id": "123-sheet-id", "deleted": False}
    # and not Rick's
    response = client_with_auth.delete("/sheet/456-sheet-id")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"id": "456-sheet-id", "deleted": False}


class TestArchiveUserSheetEndpoint:
    @patch("app.web.routers.sheet.celery", return_value=MagicMock())
    def test_normal_flow(self, m_celery, client_with_auth, db_session):
        db_session.add(
            models.Sheet(
                id="123-sheet-id",
                name="Test Sheet 1",
                author_id="rick@example.com",
                group_id="spaceship",
                frequency="hourly",
            )
        )
        db_session.commit()

        m_signature = MagicMock()
        m_signature.apply_async.return_value = TaskResult(
            id="123-taskid", status=STATUS_PENDING, result=""
        )
        m_celery.signature.return_value = m_signature

        r = client_with_auth.post("/sheet/123-sheet-id/archive")
        assert r.status_code == HTTPStatus.CREATED
        assert r.json() == {"id": "123-taskid"}
        m_celery.signature.assert_called_once()
        m_signature.apply_async.assert_called_once()

    def test_token_auth(self, client_with_token):
        # API token with nonexistent sheet returns 404
        r = client_with_token.post("/sheet/123-sheet-id/archive")
        assert r.status_code == HTTPStatus.NOT_FOUND
        assert r.json() == {"detail": "Sheet not found."}

    @patch("app.web.routers.sheet.celery", return_value=MagicMock())
    def test_token_auth_triggers_any_sheet(
        self, m_celery, client_with_token, db_session
    ):
        # Add a sheet owned by someone else
        db_session.add(
            models.Sheet(
                id="rick-sheet-id",
                name="Rick's Sheet",
                author_id="rick@example.com",
                group_id="spaceship",
                frequency="hourly",
            )
        )
        db_session.commit()

        m_signature = MagicMock()
        m_signature.apply_async.return_value = TaskResult(
            id="token-taskid", status=STATUS_PENDING, result=""
        )
        m_celery.signature.return_value = m_signature

        r = client_with_token.post("/sheet/rick-sheet-id/archive")
        assert r.status_code == HTTPStatus.CREATED
        assert r.json() == {"id": "token-taskid"}
        m_celery.signature.assert_called_once()
        # Verify it was queued as high priority
        m_signature.apply_async.assert_called_once_with(
            priority=0, queue="high_priority"
        )

    @patch("app.web.routers.sheet.celery", return_value=MagicMock())
    def test_token_auth_uses_sheet_owner_as_author(
        self, m_celery, client_with_token, db_session
    ):
        db_session.add(
            models.Sheet(
                id="jerry-sheet-id",
                name="Jerry's Sheet",
                author_id="jerry@example.com",
                group_id="the-jerrys-club",
                frequency="daily",
            )
        )
        db_session.commit()

        m_signature = MagicMock()
        m_signature.apply_async.return_value = TaskResult(
            id="token-taskid-2", status=STATUS_PENDING, result=""
        )
        m_celery.signature.return_value = m_signature

        r = client_with_token.post("/sheet/jerry-sheet-id/archive")
        assert r.status_code == HTTPStatus.CREATED
        # Verify the sheet task uses the original sheet owner as author
        call_args = m_celery.signature.call_args
        import json

        submitted = json.loads(
            call_args[1]["args"][0]
            if "args" in call_args[1]
            else call_args[0][1][0]
        )
        assert submitted["author_id"] == "jerry@example.com"
        assert submitted["sheet_id"] == "jerry-sheet-id"

    def test_token_auth_sheet_not_found(self, client_with_token):
        r = client_with_token.post("/sheet/nonexistent-sheet/archive")
        assert r.status_code == HTTPStatus.NOT_FOUND
        assert r.json() == {"detail": "Sheet not found."}

    def test_missing_data(self, client_with_auth):
        r = client_with_auth.post("/sheet/123-sheet-id/archive")
        assert r.status_code == HTTPStatus.FORBIDDEN
        assert r.json() == {"detail": "No access to this sheet."}

    def test_no_access(self, client_with_auth, db_session):
        # Sheet owned by morty, but auth user is rick — rick can't see morty's sheet
        db_session.add(
            models.Sheet(
                id="123-sheet-id",
                name="Test Sheet 1",
                author_id="morty@example.com",
                group_id="spaceship",
                frequency="hourly",
            )
        )
        db_session.commit()
        r = client_with_auth.post("/sheet/123-sheet-id/archive")
        assert r.status_code == HTTPStatus.FORBIDDEN
        assert r.json() == {"detail": "No access to this sheet."}

    def test_user_not_in_group(self, client_with_auth, db_session):
        # Rick owns the sheet but is not in this group
        db_session.add(
            models.Sheet(
                id="123-sheet-id",
                name="Test Sheet 1",
                author_id="rick@example.com",
                group_id="the-jerrys-club",
                frequency="hourly",
            )
        )
        db_session.commit()
        r = client_with_auth.post("/sheet/123-sheet-id/archive")
        assert r.status_code == HTTPStatus.FORBIDDEN
        assert r.json() == {
            "detail": "User does not have access to this group."
        }

    def test_user_cannot_manually_trigger(self, client_with_auth, db_session):
        # Rick is in 'animated-characters' (via domain) but that group
        # does not have manually_trigger_sheet permission
        db_session.add(
            models.Sheet(
                id="123-sheet-id",
                name="Test Sheet 1",
                author_id="rick@example.com",
                group_id="animated-characters",
                frequency="hourly",
            )
        )
        db_session.commit()
        r = client_with_auth.post("/sheet/123-sheet-id/archive")
        assert r.status_code == HTTPStatus.TOO_MANY_REQUESTS
        assert r.json() == {
            "detail": "User cannot manually trigger sheet archiving in this group."
        }


class TestSheetAccessPermissionCheck:
    """Tests for the Google Sheet write access permission check."""

    ERROR_MSG = (
        "The Google Sheet has not been shared with the Auto Archiver "
        "service account (sa@test.iam.gserviceaccount.com). Please "
        "share the sheet with this email address and give it Editor "
        "permissions."
    )

    @patch(
        "app.web.routers.sheet.get_sheet_access_error",
        return_value=ERROR_MSG,
    )
    def test_create_sheet_no_write_access(
        self, m_access, app_with_auth, db_session
    ):
        """Sheet creation is blocked when the SA has no write access."""
        client = TestClient(app_with_auth)
        data = {
            "id": "no-access-sheet",
            "name": "Test Sheet",
            "group_id": "spaceship",
            "frequency": "daily",
        }
        r = client.post("/sheet/create", json=data)
        assert r.status_code == HTTPStatus.FORBIDDEN
        assert "service account" in r.json()["detail"]
        m_access.assert_called_once()

    @patch(
        "app.web.routers.sheet.get_sheet_access_error",
        return_value=None,
    )
    def test_create_sheet_access_indeterminate_proceeds(
        self, m_access, app_with_auth, db_session
    ):
        """Sheet creation proceeds when access check is indeterminate."""
        client = TestClient(app_with_auth)
        data = {
            "id": "maybe-access-sheet",
            "name": "Test Sheet",
            "group_id": "spaceship",
            "frequency": "daily",
        }
        r = client.post("/sheet/create", json=data)
        assert r.status_code == HTTPStatus.CREATED
        m_access.assert_called_once()

    @patch(
        "app.web.routers.sheet.get_sheet_access_error",
        return_value=ERROR_MSG,
    )
    def test_archive_sheet_no_write_access(
        self, m_access, app_with_auth, db_session
    ):
        """Manual trigger is blocked when the SA has no write access."""
        db_session.add(
            models.Sheet(
                id="123-sheet-id",
                name="Test Sheet 1",
                author_id="rick@example.com",
                group_id="spaceship",
                frequency="hourly",
            )
        )
        db_session.commit()
        client = TestClient(app_with_auth)
        r = client.post("/sheet/123-sheet-id/archive")
        assert r.status_code == HTTPStatus.FORBIDDEN
        assert "service account" in r.json()["detail"]
        assert "Editor" in r.json()["detail"]
        m_access.assert_called_once()

    @patch("app.web.routers.sheet.celery", return_value=MagicMock())
    @patch(
        "app.web.routers.sheet.get_sheet_access_error",
        return_value=None,
    )
    def test_archive_sheet_access_ok_proceeds(
        self, m_access, m_celery, app_with_auth, db_session
    ):
        """Manual trigger proceeds when access check passes."""
        db_session.add(
            models.Sheet(
                id="123-sheet-id",
                name="Test Sheet 1",
                author_id="rick@example.com",
                group_id="spaceship",
                frequency="hourly",
            )
        )
        db_session.commit()

        m_signature = MagicMock()
        m_signature.apply_async.return_value = TaskResult(
            id="task-123", status=STATUS_PENDING, result=""
        )
        m_celery.signature.return_value = m_signature

        client = TestClient(app_with_auth)
        r = client.post("/sheet/123-sheet-id/archive")
        assert r.status_code == HTTPStatus.CREATED
        m_access.assert_called_once()
        m_celery.signature.assert_called_once()

    @patch(
        "app.web.routers.sheet.get_sheet_access_error",
        return_value=ERROR_MSG,
    )
    def test_token_archive_sheet_no_write_access(
        self, m_access, app_with_token, db_session
    ):
        """API token trigger is also blocked when SA has no write access."""
        db_session.add(
            models.Sheet(
                id="token-sheet-id",
                name="Token Sheet",
                author_id="rick@example.com",
                group_id="spaceship",
                frequency="hourly",
            )
        )
        db_session.commit()
        client = TestClient(app_with_token)
        r = client.post("/sheet/token-sheet-id/archive")
        assert r.status_code == HTTPStatus.FORBIDDEN
        assert "service account" in r.json()["detail"]
