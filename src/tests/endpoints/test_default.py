from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from core.config import VERSION


def test_endpoint_home(client_with_auth):
    r = client_with_auth.get("/")
    assert r.status_code == 200
    j = r.json()
    assert "version" in j and j["version"] == VERSION
    assert "breakingChanges" in j
    assert "groups" not in j


@patch("endpoints.default.bearer_security", new_callable=AsyncMock)
@patch("endpoints.default.get_user_auth", new_callable=AsyncMock, return_value="test@example.com")
@patch("endpoints.default.crud.get_user_groups", return_value=["group1", "group2"])
def test_endpoint_home_with_groups(m1, m2, m3, client_with_auth):
    r = client_with_auth.get("/")
    assert r.status_code == 200
    j = r.json()
    assert "version" in j and j["version"] == VERSION
    assert "breakingChanges" in j
    assert "groups" in j
    assert j["groups"] == ["group1", "group2"]

@patch("endpoints.default.bearer_security", new_callable=AsyncMock)
@patch("endpoints.default.get_user_auth", new_callable=AsyncMock, return_value="test@example.com")
@patch("endpoints.default.crud.get_user_groups", side_effect=Exception('mocked error'))
def test_endpoint_home_with_groups_exception(m1, m2, m3, client_with_auth): # mocks call that triggers an internal error
    r = client_with_auth.get("/")
    assert r.status_code == 200
    j = r.json()
    assert "version" in j and j["version"] == VERSION
    assert "breakingChanges" in j
    assert "groups" not in j


def test_endpoint_health(client_with_auth):
    r = client_with_auth.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_endpoint_groups_403(client):
    r = client.get("/groups")
    assert r.status_code == 403


def test_endpoint_groups_empty(client_with_auth):
    r = client_with_auth.get("/groups")
    assert r.status_code == 200
    assert r.json() == []


@patch("endpoints.default.crud.get_user_groups", return_value=["group1", "group2"])
def test_endpoint_groups(m1, app):
    from security import get_user_auth
    app.dependency_overrides[get_user_auth] = lambda: True
    client = TestClient(app)

    r = client.get("/groups")

    assert r.status_code == 200
    assert r.json() == ["group1", "group2"]


def test_no_serve_local_archive_by_default(client_with_auth):
    r = client_with_auth.get("/app/local_archive_test/temp.txt")
    assert r.status_code == 404


def test_favicon(client_with_auth):
    r = client_with_auth.get("/favicon.ico")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/vnd.microsoft.icon"
