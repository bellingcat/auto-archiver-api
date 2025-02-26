from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.shared.schemas import Usage, UsageResponse
from app.shared.user_groups import GroupInfo
from app.web.config import VERSION


def test_endpoint_home(client_with_auth):
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
    assert (
        r.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
    )
    assert "disk_utilization" in r.text
    assert "database_metrics" in r.text
    assert "exceptions" in r.text
    assert "worker_exceptions_total" in r.text
    assert 'disk_utilization{type="used"}' not in r.text

    # after metrics calculation
    from app.web.utils.metrics import measure_regular_metrics

    await measure_regular_metrics(
        get_settings.DATABASE_PATH, 60 * 60 * 24 * 31 * 12 * 100
    )
    r2 = client_with_token.get("/metrics")
    assert 'disk_utilization{type="used"}' in r2.text
    assert 'disk_utilization{type="free"}' in r2.text
    assert 'disk_utilization{type="database"}' in r2.text
    assert 'database_metrics{query="count_archives"} 100.0' in r2.text
    assert 'database_metrics{query="count_archive_urls"} 1000.0' in r2.text
    assert 'database_metrics{query="count_users"} 3.0' in r2.text
    assert (
        'database_metrics_counter_total{query="count_by_user",user="rick@example.com"} 34.0'
        in r2.text
    )
    assert (
        'database_metrics_counter_total{query="count_by_user",user="morty@example.com"} 33.0'
        in r2.text
    )
    assert (
        'database_metrics_counter_total{query="count_by_user",user="jerry@example.com"} 33.0'
        in r2.text
    )

    # 30s window, should not change the gauges nor the total in the counters
    from app.web.utils.metrics import measure_regular_metrics

    await measure_regular_metrics(get_settings.DATABASE_PATH, 30)
    r3 = client_with_token.get("/metrics")
    assert 'database_metrics{query="count_archives"} 100.0' in r3.text
    assert 'database_metrics{query="count_archive_urls"} 1000.0' in r3.text
    assert 'database_metrics{query="count_users"} 3.0' in r3.text
    assert (
        'database_metrics_counter_total{query="count_by_user",user="rick@example.com"} 34.0'
        in r3.text
    )
    assert (
        'database_metrics_counter_total{query="count_by_user",user="morty@example.com"} 33.0'
        in r3.text
    )
    assert (
        'database_metrics_counter_total{query="count_by_user",user="jerry@example.com"} 33.0'
        in r3.text
    )


def test_endpoint_get_user_permissions_no_user_auth(client, test_no_auth):
    test_no_auth(client.get, "/user/permissions")


def test_endpoint_get_user_permissions(app):
    from app.web.security import get_user_state

    m_user_state = MagicMock()
    rv = {
        "all": GroupInfo(read=True),
        "group1": GroupInfo(archive_url=True),
    }
    from loguru import logger

    logger.info(rv)
    m_user_state.permissions = rv

    app.dependency_overrides[get_user_state] = lambda: m_user_state

    client = TestClient(app)
    r = client.get("/user/permissions")
    assert r.status_code == 200
    response = r.json()
    assert response.keys() == {"all", "group1"}
    assert response["all"]["read"]
    assert response["group1"]["read"] == []
    assert response["group1"]["archive_url"]
    assert response["all"]["archive_url"] is False


def test_endpoint_get_user_usage_no_user_auth(client, test_no_auth):
    test_no_auth(client.get, "/user/usage")


def test_endpoint_get_user_usage_inactive(app):
    from app.web.security import get_user_state

    m_user_state = MagicMock()
    m_user_state.active = False

    app.dependency_overrides[get_user_state] = lambda: m_user_state

    client = TestClient(app)
    r = client.get("/user/usage")
    assert r.status_code == 403
    assert r.json() == {"detail": "User is not active."}


def test_endpoint_get_user_usage_active(app):
    from app.web.security import get_user_state

    m_user_state = MagicMock()
    m_user_state.active = True
    mock_usage = UsageResponse(
        monthly_urls=1,
        monthly_mbs=2,
        total_sheets=3,
        groups={
            "group1": Usage(monthly_urls=4, monthly_mbs=5, total_sheets=6),
            "group2": Usage(monthly_urls=7, monthly_mbs=8, total_sheets=9),
        },
    )
    m_user_state.usage.return_value = mock_usage

    app.dependency_overrides[get_user_state] = lambda: m_user_state

    client = TestClient(app)
    r = client.get("/user/usage")
    assert r.status_code == 200
    assert UsageResponse(**r.json()) == mock_usage
