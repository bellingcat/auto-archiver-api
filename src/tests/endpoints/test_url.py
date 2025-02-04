import json
from unittest.mock import MagicMock, patch

from db.schemas import ArchiveCreate, TaskResult

def test_archive_url_unauthenticated(client, test_no_auth):
    test_no_auth(client.post, "/url/archive")


@patch("worker.main.create_archive_task.delay", return_value=TaskResult(id="123-456-789", status="PENDING", result=""))
def test_archive_url(m1, client_with_auth):
    # url is too short
    response = client_with_auth.post("/url/archive", json={"url": "bad"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == 'String should have at least 5 characters'
    m1.assert_not_called()

    # valid request
    response = client_with_auth.post("/url/archive", json={"url": "https://example.com"})
    assert response.status_code == 201
    assert response.json() == {'id': '123-456-789'}

    m1.assert_called_once()
    called_val = m1.call_args.args[0]
    assert json.loads(called_val) == {"id": None, "url": "https://example.com", "result": None, "public": True, "author_id": "rick@example.com", "group_id": None, "tags": [], "rearchive": True}

    # user is not in group
    response = client_with_auth.post("/url/archive", json={"url": "https://example.com", "group_id": "new-group"})
    assert response.status_code == 403
    assert response.json()["detail"] == "User does not have access to this group."

    # user is in group
    response = client_with_auth.post("/url/archive", json={"url": "https://example.com", "group_id": "spaceship"})
    assert response.status_code == 201
    assert response.json() == {'id': '123-456-789'}

    assert m1.call_count == 2
    called_val = m1.call_args.args[0]
    assert json.loads(called_val)["group_id"] == "spaceship"

@patch("endpoints.url.UserState")
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

@patch("worker.main.create_archive_task.delay", return_value=TaskResult(id="123-456-789", status="PENDING", result=""))
def test_archive_url_with_api_token(m1, client_with_token):
    response = client_with_token.post("/url/archive", json={"url": "https://example.com"})
    assert response.status_code == 201
    assert response.json() == {'id': '123-456-789'}

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

    from db import crud, schemas
    for i in range(11):
        crud.create_task(db_session, ArchiveCreate(id=f"url-456-{i}", url="https://example.com" if i < 10 else "https://something-else.com", result={}, public=True, author_id="rick@example.com", group_id=None), [], [])
        #NB: this insertion is too fast for the ordering to be correct as they are within the same second

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

@patch("endpoints.url.UserState")
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

    from db import crud
    crud.create_task(db_session, ArchiveCreate(id="delete-123-456-789", url="https://example.com", result={}, public=True, author_id="morty@example.com", group_id=None), [], [])

    response = client_with_auth.delete("/url/delete-123-456-789")
    assert response.status_code == 200
    assert response.json() == {"id": "delete-123-456-789", "deleted": True}
