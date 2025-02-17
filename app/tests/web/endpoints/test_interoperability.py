from datetime import datetime
import json
from unittest.mock import MagicMock, patch

from app.web.config import ALLOW_ANY_EMAIL
from app.web.db import crud


def test_submit_manual_archive_unauthenticated(client, test_no_auth):
    test_no_auth(client.post, "/interop/submit-archive")


def test_submit_manual_archive_not_user_auth(client_with_auth, test_no_auth):
    test_no_auth(client_with_auth.post, "/interop/submit-archive")


@patch("app.web.endpoints.interoperability.business_logic", return_value=MagicMock(get_store_archive_until=MagicMock(return_value=datetime)))
def test_submit_manual_archive(m1, client_with_token, db_session):
    # normal workflow
    aa_metadata = json.dumps({"status": "test: success", "metadata": {"url": "http://example.com"}, "media": [{"filename": "fn1", "urls": ["http://example.s3.com"]}]})
    r = client_with_token.post("/interop/submit-archive", json={"result": aa_metadata, "public": True, "author_id": "jerry@gmail.com", "group_id": "spaceship", "tags": ["test"], "url": "http://example.com"})
    assert r.status_code == 201
    assert "id" in r.json()

    inserted = crud.get_archive(db_session, r.json()["id"], ALLOW_ANY_EMAIL)
    assert inserted.url == "http://example.com"
    assert inserted.group_id == "spaceship"
    assert inserted.author_id == "jerry@gmail.com"
    assert sorted([t.id for t in inserted.tags]) == sorted(["test", "manual"])
    assert inserted.public
    assert type(inserted.result) == dict
    assert [u.url for u in inserted.urls] == ["http://example.s3.com"]
    assert type(inserted.store_until) == datetime

    # cannot have the same URL twice
    aa_metadata = json.dumps({"status": "test: success", "metadata": {"url": "http://example.com"}, "media": [{"filename": "fn1", "urls": ["http://example.com", "http://example.com"]}]})
    r = client_with_token.post("/interop/submit-archive", json={"result": aa_metadata, "public": False, "author_id": "jerry@gmail.com", "tags": ["test"], "url": "http://example.com"})
    assert r.status_code == 422
    assert r.json() == {"detail": "Cannot insert into DB due to integrity error, likely duplicate urls."}


# test with invalid JSON
def test_submit_manual_archive_invalid_json(client_with_token):
    r = client_with_token.post("/interop/submit-archive", json={"result": "invalid json", "public": False, "author_id": "jer", "tags": ["test"], "url": "http://example.com"})
    assert r.status_code == 422
    assert r.json() == {"detail": "Invalid JSON in result field."}


@patch("app.web.endpoints.interoperability.business_logic")
def test_submit_manual_archive_no_store_until(m_b, client_with_token, db_session):
    m_b.get_store_archive_until.side_effect = AssertionError("AssertionError")
    aa_metadata = json.dumps({"status": "test: success", "metadata": {"url": "http://example.com"}, "media": [{"filename": "fn1", "urls": ["http://example.s3.com"]}]})
    r = client_with_token.post("/interop/submit-archive", json={"result": aa_metadata, "public": True, "author_id": "jerry@gmail.com", "group_id": "spaceship", "tags": ["test"], "url": "http://example.com"})
    assert r.status_code == 422
    assert r.json() == {"detail": "AssertionError"}
