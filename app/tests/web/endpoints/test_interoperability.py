import json
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.shared.db import models


def test_submit_manual_archive_unauthenticated(client, test_no_auth):
    test_no_auth(client.post, "/interop/submit-archive")


def test_submit_manual_archive_not_user_auth(client_with_auth, test_no_auth):
    test_no_auth(client_with_auth.post, "/interop/submit-archive")


@patch(
    "app.web.endpoints.interoperability.business_logic",
    return_value=MagicMock(
        get_store_archive_until=MagicMock(return_value=datetime)
    ),
)
def test_submit_manual_archive(m1, client_with_token, db_session):
    # normal workflow
    aa_metadata = json.dumps(
        {
            "status": "test: success",
            "metadata": {"url": "http://example.com"},
            "media": [{"filename": "fn1", "urls": ["http://example.s3.com"]}],
        }
    )
    r = client_with_token.post(
        "/interop/submit-archive",
        json={
            "result": aa_metadata,
            "public": True,
            "author_id": "jerry@gmail.com",
            "group_id": "spaceship",
            "tags": ["test"],
            "url": "http://example.com",
        },
    )
    assert r.status_code == 201
    assert "id" in r.json()

    inserted = (
        db_session.query(models.Archive)
        .filter(models.Archive.id == r.json()["id"])
        .first()
    )
    assert inserted.url == "http://example.com"
    assert inserted.group_id == "spaceship"
    assert inserted.author_id == "jerry@gmail.com"
    assert sorted([t.id for t in inserted.tags]) == sorted(["test", "manual"])
    assert inserted.public
    assert type(inserted.result) == dict
    assert [u.url for u in inserted.urls] == ["http://example.s3.com"]
    assert type(inserted.store_until) == datetime

    # cannot have the same URL twice
    aa_metadata = json.dumps(
        {
            "status": "test: success",
            "metadata": {"url": "http://example.com"},
            "media": [
                {
                    "filename": "fn1",
                    "urls": ["http://example.com", "http://example.com"],
                }
            ],
        }
    )
    r = client_with_token.post(
        "/interop/submit-archive",
        json={
            "result": aa_metadata,
            "public": False,
            "author_id": "jerry@gmail.com",
            "tags": ["test"],
            "url": "http://example.com",
        },
    )
    assert r.status_code == 422
    assert r.json() == {
        "detail": "Cannot insert into DB due to integrity error, likely duplicate urls."
    }


# test with invalid JSON
def test_submit_manual_archive_invalid_json(client_with_token):
    r = client_with_token.post(
        "/interop/submit-archive",
        json={
            "result": "invalid json",
            "public": False,
            "author_id": "jer",
            "tags": ["test"],
            "url": "http://example.com",
        },
    )
    assert r.status_code == 422
    assert r.json() == {"detail": "Invalid JSON in result field."}


@patch(
    "app.web.endpoints.interoperability.business_logic.get_store_archive_until",
    side_effect=AssertionError("AssertionError"),
)
def test_submit_manual_archive_no_store_until(
    m_sau, client_with_token, db_session
):
    aa_metadata = json.dumps(
        {
            "status": "test: success",
            "metadata": {"url": "http://example.com"},
            "media": [{"filename": "fn1", "urls": ["http://example.s3.com"]}],
        }
    )
    r = client_with_token.post(
        "/interop/submit-archive",
        json={
            "result": aa_metadata,
            "public": True,
            "author_id": "jerry@gmail.com",
            "group_id": "spaceship",
            "tags": ["test"],
            "url": "http://example.com",
        },
    )
    assert r.status_code == 201
    assert len(r.json()["id"]) == 36
    res = (
        db_session.query(models.Archive)
        .filter(models.Archive.id == r.json()["id"])
        .first()
    )
    assert res.store_until is None
    # testing that store_until = None is not comparable with datetime, and will always return False
    res = (
        db_session.query(models.Archive)
        .filter(
            models.Archive.id == r.json()["id"],
            models.Archive.store_until < datetime.now(),
        )
        .first()
    )
    assert res is None
