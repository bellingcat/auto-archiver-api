from datetime import datetime
import json
from unittest.mock import patch

from app.shared.config import ALLOW_ANY_EMAIL
from app.shared.db import crud


def test_submit_manual_archive_unauthenticated(client, test_no_auth):
    test_no_auth(client.post, "/interop/submit-archive")


def test_submit_manual_archive_not_user_auth(client_with_auth, test_no_auth):
    test_no_auth(client_with_auth.post, "/interop/submit-archive")


@patch("endpoints.interoperability.get_store_until", return_value=datetime.now())
def test_submit_manual_archive(m1, client_with_token, db_session):
    # normal workflow
    aa_metadata = json.dumps({"status": "test: success", "metadata": {"url": "http://example.com"}, "media": [{"filename": "fn1", "urls": ["http://example.s3.com"]}]})
    r = client_with_token.post("/interop/submit-archive", json={"result": aa_metadata, "public": True, "author_id": "jerry@gmail.com", "group_id": "spaceship", "tags": ["test"]})
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
    r = client_with_token.post("/interop/submit-archive", json={"result": aa_metadata, "public": False, "author_id": "jerry@gmail.com", "tags": ["test"]})
    assert r.status_code == 422
    assert r.json() == {"detail": "Cannot insert into DB due to integrity error, likely duplicate urls."}
