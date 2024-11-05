import json


def test_submit_manual_archive_unauthenticated(client, test_no_auth):
    test_no_auth(client.post, "/interop/submit-archive")


def test_submit_manual_archive_not_user_auth(client_with_auth, test_no_auth):
    test_no_auth(client_with_auth.post, "/interop/submit-archive")


def test_submit_manual_archive(client_with_token):
    aa_metadata = json.dumps({"status": "test: success", "metadata": {"url": "http://example.com"}, "media": []})

    r = client_with_token.post("/interop/submit-archive", json={"result": aa_metadata, "public": False, "author_id": "jerry@gmail.com", "group_id": None, "tags": ["test"]})
    assert r.status_code == 201
    assert "id" in r.json()

    # cannot have the same URL twice
    aa_metadata = json.dumps({"status": "test: success", "metadata": {"url": "http://example.com"}, "media": [{"filename": "fn1", "urls": ["http://example.com", "http://example.com"]}]})
    r = client_with_token.post("/interop/submit-archive", json={"result": aa_metadata, "public": False, "author_id": "jerry@gmail.com", "group_id": None, "tags": ["test"]})
    assert r.status_code == 422
    assert r.json() == {"detail": "Cannot insert into DB due to integrity error"}
