from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from core.config import VERSION


def test_endpoint_home(client):
    r = client.get("/")
    assert r.status_code == 200
    j = r.json()
    assert "version" in j and j["version"] == VERSION
    assert "breakingChanges" in j
    assert "groups" not in j


@patch("endpoints.default.bearer_security", new_callable=AsyncMock)
@patch("endpoints.default.get_user_auth", new_callable=AsyncMock, return_value="test@example.com")
@patch("endpoints.default.crud.get_user_groups", return_value=["group1", "group2"])
def test_endpoint_home_with_groups(m1, m2, m3, client):
    r = client.get("/")
    assert r.status_code == 200
    j = r.json()
    assert "version" in j and j["version"] == VERSION
    assert "breakingChanges" in j
    assert "groups" in j
    assert j["groups"] == ["group1", "group2"]


def test_endpoint_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_endpoint_groups_403(client):
    r = client.get("/groups")
    assert r.status_code == 403


@patch("endpoints.default.crud.get_user_groups", return_value=["group1", "group2"])
def test_endpoint_groups(m1, app):
    async def mock_get_user_auth(): return True
    from security import get_user_auth
    app.dependency_overrides[get_user_auth] = mock_get_user_auth
    client = TestClient(app)

    r = client.get("/groups")

    assert r.status_code == 200
    j = r.json()
    assert j == ["group1", "group2"]
    app.dependency_overrides = {}


def test_no_serve_local_archive_by_default(client):
    r = client.get("/app/local_archive_test/temp.txt")
    assert r.status_code == 404


def test_favicon(client):
    r = client.get("/favicon.ico")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/vnd.microsoft.icon"
