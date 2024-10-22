

import json
from unittest.mock import patch

from db.schemas import ArchiveCreate, TaskResult

def test_archive_url_unauthenticated(client, test_no_auth):
    test_no_auth(client.post, "/url/archive")
    test_no_auth(client.get, "/url/archive")


@patch("worker.main.create_archive_task.delay", return_value=TaskResult(id="123-456-789", status="PENDING", result=""))
def test_archive_url(m1, client_with_auth):
    response = client_with_auth.post("/url/archive", json={"url": "bad"})
    assert response.status_code == 422
    assert response.json() == {'detail': 'Invalid URL received: bad'}
    m1.assert_not_called()

    response = client_with_auth.post("/url/archive", json={"url": "https://example.com"})
    assert response.status_code == 201
    assert response.json() == {'id': '123-456-789'}

    m1.assert_called_once()
    called_val = m1.call_args.args[0]
    assert json.loads(called_val) == {"id": None, "url": "https://example.com", "result": None, "public": True, "author_id": "rick@example.com", "group_id": None, "tags": [], "rearchive": True}


def test_search_by_url_unauthenticated(client, test_no_auth):
    test_no_auth(client.get, "/url/search")


def test_search_by_url(client_with_auth, db_session):
    # tests the search endpoint, including through some db data for the endpoint params
    response = client_with_auth.get("/url/search")
    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "Field required"

    response = client_with_auth.get("/url/search?url=https://example.com")
    assert response.status_code == 200
    assert response.json() == []

    from db import crud
    for i in range(11):
        crud.create_task(db_session, ArchiveCreate(id=f"url-456-{i}", url="https://example.com" if i < 10 else "https://something-else.com", result={}, public=True, author_id="rick@example.com", group_id=None), [], [])
        #NB: this insertion is too fast for the ordering to be correct as they are within the same second

    response = client_with_auth.get("/url/search?url=https://example.com")
    assert response.status_code == 200
    assert len(j := response.json()) == 10
    assert "url-456-0" in [i["id"] for i in j]
    assert "url-456-9" in [i["id"] for i in j]
    assert "url-456-10" not in [i["id"] for i in j]

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


def test_latest_unauthenticated(client, test_no_auth):
    test_no_auth(client.get, "/url/latest")


def test_latest(client_with_auth, db_session):
    response = client_with_auth.get("/url/latest")
    assert response.status_code == 200
    assert response.json() == []

    from db import crud
    for i in range(11):
        crud.create_task(db_session, ArchiveCreate(id=f"latest-456-{i}", url="https://example.com", result={}, public=True, author_id="morty@example.com" if i < 10 else "rick@example.com", group_id=None), [], [])
        #NB: this insertion is too fast for the ordering to be correct as they are within the same second

    # user must exist for /latest to work
    crud.create_or_get_user(db_session, "morty@example.com")

    response = client_with_auth.get("/url/latest")
    assert response.status_code == 200
    assert len(j := response.json()) == 10
    assert "latest-456-0" in [i["id"] for i in j]
    assert "latest-456-9" in [i["id"] for i in j]
    assert "latest-456-10" not in [i["id"] for i in j]

    response = client_with_auth.get("/url/latest?limit=5")
    assert response.status_code == 200
    assert len(response.json()) == 5

    response = client_with_auth.get("/url/latest?skip=5&limit=2")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_lookup_unauthenticated(client, test_no_auth):
    test_no_auth(client.get, "/url/123-456-789")


def test_lookup(client_with_auth, db_session):
    response = client_with_auth.get("/url/lookup-123-456-789")
    assert response.status_code == 404
    assert response.json() == {"detail": "Archive not found"}

    from db import crud
    crud.create_task(db_session, ArchiveCreate(id="lookup-123-456-789", url="https://example.com", result={}, public=True, author_id="rick@example.com", group_id=None), [], [])

    response = client_with_auth.get("/url/lookup-123-456-789")
    assert response.status_code == 200
    j = response.json()
    assert j["id"] == "lookup-123-456-789"
    assert j["url"] == "https://example.com"
    assert j["result"] == {}
    assert j["public"] == True
    assert j["author_id"] == "rick@example.com"
    assert j["group_id"] == None
    assert j["tags"] == []
    assert j["updated_at"] == None
    assert j["rearchive"] == True


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
