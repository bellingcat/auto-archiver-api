import json
from unittest.mock import MagicMock, patch

from app.shared.schemas import ArchiveCreate, TaskResult


def test_archive_url_unauthenticated(client, test_no_auth):
    test_no_auth(client.post, "/url/archive")


@patch("app.web.endpoints.url.UserState")
@patch("app.web.endpoints.url.celery", return_value=MagicMock())
def test_archive_url(m_celery, m2, client_with_auth):
    m_signature = MagicMock()
    m_signature.apply_async.return_value = TaskResult(id="123-456-789", status="PENDING", result="")
    m_celery.signature.return_value = m_signature

    m_user_state = MagicMock()
    m2.return_value = m_user_state

    # url is too short
    response = client_with_auth.post("/url/archive", json={"url": "bad"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == 'String should have at least 5 characters'
    m_celery.signature.assert_not_called()

    # url is invalid
    response = client_with_auth.post("/url/archive", json={"url": "example.com"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid URL received."

    # valid request
    m_user_state.has_quota_max_monthly_urls.return_value = True
    m_user_state.has_quota_max_monthly_mbs.return_value = True
    response = client_with_auth.post("/url/archive", json={"url": "https://example.com"})
    assert response.status_code == 201
    assert response.json() == {'id': '123-456-789'}
    m_celery.signature.assert_called_once()
    m_signature.apply_async.assert_called_once()
    called_val = m_celery.signature.call_args
    assert called_val[0][0] == "create_archive_task"
    assert json.loads(called_val[1]['args'][0]) ==  {"id": None, "url": "https://example.com", "result": None, "public": False, "author_id": "rick@example.com", "group_id": "default", "tags": None, "sheet_id": None, "store_until": None, "urls": None}
    m_user_state.has_quota_max_monthly_urls.assert_called_once()
    m_user_state.has_quota_max_monthly_mbs.assert_called_once()
    m_user_state.in_group.assert_called_once_with("default")

    # user is not in group
    m_user_state.in_group.return_value = False
    response = client_with_auth.post("/url/archive", json={"url": "https://example.com", "group_id": "new-group"})
    assert response.status_code == 403
    assert response.json()["detail"] == "User does not have access to this group."
    m_user_state.in_group.assert_called_with("new-group")

    # user is in group
    m_user_state.in_group.return_value = True
    response = client_with_auth.post("/url/archive", json={"url": "https://example.com", "group_id": "spaceship"})
    assert response.status_code == 201
    assert response.json() == {'id': '123-456-789'}
    assert m_celery.signature.call_count == 2
    assert m_signature.apply_async.call_count == 2
    called_val = m_celery.signature.call_args
    assert json.loads(called_val[1]['args'][0])["group_id"] == "spaceship"
    m_user_state.in_group.assert_called_with("spaceship")

    # user is over monthly URL quota
    m_user_state.has_quota_max_monthly_urls.return_value = False
    m_user_state.has_quota_max_monthly_mbs.return_value = True
    response = client_with_auth.post("/url/archive", json={"url": "https://example.com", "group_id": "spaceship"})
    assert response.status_code == 429
    assert response.json()["detail"] == "User has reached their monthly URL quota."
    m_user_state.has_quota_max_monthly_urls.assert_called_with("spaceship")

    # user is over monthly MB quota
    m_user_state.has_quota_max_monthly_urls.return_value = True
    m_user_state.has_quota_max_monthly_mbs.return_value = False
    response = client_with_auth.post("/url/archive", json={"url": "https://example.com", "group_id": "spacesuit"})
    assert response.status_code == 429
    assert response.json()["detail"] == "User has reached their monthly MB quota."
    m_user_state.has_quota_max_monthly_mbs.assert_called_with("spacesuit")
    assert m_celery.signature.call_count == 2
    assert m_signature.apply_async.call_count == 2


@patch("app.web.endpoints.url.UserState")
def test_archive_url_quotas(m1, client_with_auth):
    m_user_state = MagicMock()
    m1.return_value = m_user_state

    # misses on monthly URLs quota
    m_user_state.has_quota_max_monthly_urls.return_value = False
    response = client_with_auth.post("/url/archive", json={"url": "https://example.com"})
    assert response.status_code == 429
    assert response.json()["detail"] == "User has reached their monthly URL quota."
    m_user_state.has_quota_max_monthly_urls.assert_called_once()

    # misses on monthly MBs quota
    m_user_state.has_quota_max_monthly_urls.return_value = True
    m_user_state.has_quota_max_monthly_mbs.return_value = False
    response = client_with_auth.post("/url/archive", json={"url": "https://example.com"})
    assert response.status_code == 429
    assert response.json()["detail"] == "User has reached their monthly MB quota."
    m_user_state.has_quota_max_monthly_mbs.assert_called_once()


@patch("app.web.endpoints.url.celery", return_value=MagicMock())
def test_archive_url_with_api_token(m_celery, client_with_token):
    m_signature = MagicMock()
    m_signature.apply_async.return_value = TaskResult(id="123-456-789", status="PENDING", result="")
    m_celery.signature.return_value = m_signature
    response = client_with_token.post("/url/archive", json={"url": "https://example.com"})
    assert response.status_code == 201
    assert response.json() == {'id': '123-456-789'}
    m_celery.signature.assert_called_once()
    m_signature.apply_async.assert_called_once()
    called_val = m_celery.signature.call_args
    assert called_val[0][0] == "create_archive_task"


def test_search_by_url_unauthenticated(client, test_no_auth):
    test_no_auth(client.get, "/url/search")


def test_search_by_url(client_with_auth, client_with_token, db_session):
    # tests the search endpoint, including through some db data for the endpoint params
    response = client_with_auth.get("/url/search")
    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "Field required"

    response = client_with_auth.get("/url/search?url=https://example.com")
    assert response.status_code == 200
    assert response.json() == []

    from app.shared import schemas
    from app.shared.db import worker_crud
    for i in range(11):
        worker_crud.create_archive(db_session, ArchiveCreate(id=f"url-456-{i}", url="https://example.com" if i < 10 else "https://something-else.com", result={}, public=True, author_id="rick@example.com"), [], [])
        # NB: this insertion is too fast for the ordering to be correct as they are within the same second

    response = client_with_auth.get("/url/search?url=https://example.com")
    assert response.status_code == 200
    assert len(j := response.json()) == 10
    assert "url-456-0" in [i["id"] for i in j]
    assert "url-456-9" in [i["id"] for i in j]
    assert "url-456-10" not in [i["id"] for i in j]
    assert j[0].keys() == schemas.ArchiveResult.model_fields.keys()

    response = client_with_auth.get("/url/search?url=https://example.com&limit=5")
    assert response.status_code == 200
    assert len(response.json()) == 5

    response = client_with_auth.get("/url/search?url=https://example.com&skip=5&limit=2")
    assert response.status_code == 200
    assert len(response.json()) == 2

    response = client_with_auth.get("/url/search?url=https://example.com&archived_before=2010-01-01")
    assert response.status_code == 200
    assert len(response.json()) == 0

    response = client_with_auth.get("/url/search?url=https://example.com&archived_after=2010-01-01")
    assert response.status_code == 200
    assert len(response.json()) == 10

    # API token will also work
    response = client_with_token.get("/url/search?url=https://example.com&archived_after=2010-01-01")
    assert response.status_code == 200
    assert len(response.json()) == 10


@patch("app.web.endpoints.url.UserState")
def test_search_no_read_access(mock_user_state, client_with_auth):
    mock_user_state.return_value.read = False
    mock_user_state.return_value.read_public = False

    response = client_with_auth.get("/url/search?url=https://example.com")
    assert response.status_code == 403
    assert response.json() == {"detail": "User does not have read access."}


def test_delete_task_unauthenticated(client, test_no_auth):
    test_no_auth(client.delete, "/url/123-456-789")


def test_delete_task(client_with_auth, db_session):
    response = client_with_auth.delete("/url/delete-123-456-789")
    assert response.status_code == 200
    assert response.json() == {"id": "delete-123-456-789", "deleted": False}

    from app.shared.db import worker_crud
    worker_crud.create_archive(db_session, ArchiveCreate(id="delete-123-456-789", url="https://example.com", result={}, public=True, author_id="morty@example.com"), [], [])

    response = client_with_auth.delete("/url/delete-123-456-789")
    assert response.status_code == 200
    assert response.json() == {"id": "delete-123-456-789", "deleted": True}
