from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
import pytest
from app.web.config import VERSION
from app.tests.web.db.test_crud import test_data


def test_endpoint_home(client_with_auth):
    r = client_with_auth.get("/")
    assert r.status_code == 200
    j = r.json()
    assert "version" in j and j["version"] == VERSION
    assert "breakingChanges" in j
    assert "groups" not in j


@patch("app.web.endpoints.default.bearer_security", new_callable=AsyncMock)
@patch("app.web.endpoints.default.get_user_auth", new_callable=AsyncMock, return_value="test@example.com")
@patch("app.web.endpoints.default.crud.get_user_groups", return_value=["group1", "group2"])
def test_endpoint_home_with_groups(m1, m2, m3, client_with_auth):
    r = client_with_auth.get("/")
    assert r.status_code == 200
    j = r.json()
    assert "version" in j and j["version"] == VERSION
    assert "breakingChanges" in j
    assert "groups" in j
    assert j["groups"] == ["group1", "group2"]


@patch("app.web.endpoints.default.bearer_security", new_callable=AsyncMock)
@patch("app.web.endpoints.default.get_user_auth", new_callable=AsyncMock, return_value="test@example.com")
@patch("app.web.endpoints.default.crud.get_user_groups", side_effect=Exception('mocked error'))
def test_endpoint_home_with_groups_exception(m1, m2, m3, client_with_auth):  # mocks call that triggers an internal error
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


def test_endpoint_active_no_auth(client, test_no_auth):
    test_no_auth(client.get, "/user/active")


def test_endpoint_active(app):
    m_user_state = MagicMock()

    from app.web.security import get_user_state
    app.dependency_overrides[get_user_state] = lambda: m_user_state
    
    # inactive user
    m_user_state.active = False
    client = TestClient(app)
    r = client.get("/user/active")
    assert r.status_code == 200
    assert r.json() == {"active": False}

    # active user
    m_user_state.active = True
    client = TestClient(app)
    r = client.get("/user/active")
    assert r.status_code == 200
    assert r.json() == {"active": True}
    


def test_no_serve_local_archive_by_default(client_with_auth):
    r = client_with_auth.get("/app/local_archive_test/temp.txt")
    assert r.status_code == 404


def test_favicon(client_with_auth):
    r = client_with_auth.get("/favicon.ico")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/vnd.microsoft.icon"


def test_endpoint_test_prometheus_no_auth(client, test_no_auth):
    test_no_auth(client.get, "/metrics")


def test_endpoint_test_prometheus_no_user_auth(client_with_auth, test_no_auth):
    test_no_auth(client_with_auth.get, "/metrics")


@pytest.mark.asyncio
async def test_prometheus_metrics(test_data, client_with_token, get_settings):
    # before metrics calculation
    r = client_with_token.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
    assert "disk_utilization" in r.text
    assert "database_metrics" in r.text
    assert "exceptions" in r.text
    assert "worker_exceptions_total" in r.text
    assert 'disk_utilization{type="used"}' not in r.text

    # after metrics calculation
    from app.web.utils.metrics import measure_regular_metrics
    await measure_regular_metrics(get_settings.DATABASE_PATH, 60 * 60 * 24 * 31 * 12 * 100)
    r2 = client_with_token.get("/metrics")
    assert 'disk_utilization{type="used"}' in r2.text
    assert 'disk_utilization{type="free"}' in r2.text
    assert 'disk_utilization{type="database"}' in r2.text
    assert 'database_metrics{query="count_archives"} 100.0' in r2.text
    assert 'database_metrics{query="count_archive_urls"} 1000.0' in r2.text
    assert 'database_metrics{query="count_users"} 3.0' in r2.text
    assert 'database_metrics_counter_total{query="count_by_user",user="rick@example.com"} 34.0' in r2.text
    assert 'database_metrics_counter_total{query="count_by_user",user="morty@example.com"} 33.0' in r2.text
    assert 'database_metrics_counter_total{query="count_by_user",user="jerry@example.com"} 33.0' in r2.text

    # 30s window, should not change the gauges nor the total in the counters
    from app.web.utils.metrics import measure_regular_metrics
    await measure_regular_metrics(get_settings.DATABASE_PATH, 30)
    r3 = client_with_token.get("/metrics")
    assert 'database_metrics{query="count_archives"} 100.0' in r3.text
    assert 'database_metrics{query="count_archive_urls"} 1000.0' in r3.text
    assert 'database_metrics{query="count_users"} 3.0' in r3.text
    assert 'database_metrics_counter_total{query="count_by_user",user="rick@example.com"} 34.0' in r3.text
    assert 'database_metrics_counter_total{query="count_by_user",user="morty@example.com"} 33.0' in r3.text
    assert 'database_metrics_counter_total{query="count_by_user",user="jerry@example.com"} 33.0' in r3.text
