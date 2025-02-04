import os
from unittest.mock import patch
from fastapi.testclient import TestClient

import shutil

import pytest

def test_lifespan(app):
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

def test_alembic(db_session):
    import alembic.config
    alembic.config.main(argv=['--raiseerr', 'upgrade', 'head'])
    alembic.config.main(argv=['--raiseerr', 'downgrade', 'base'])

@patch("endpoints.default.crud.soft_delete_task", side_effect=Exception('mocked error'))
def test_logging_middleware(m1, client_with_auth):
    from utils.metrics import EXCEPTION_COUNTER
    assert len(EXCEPTION_COUNTER.collect()[0].samples) == 0
    with pytest.raises(Exception, match="mocked error"):
        client_with_auth.delete("/url/123")
    # creates one empty and one from above
    assert len(EXCEPTION_COUNTER.collect()[0].samples) == 2
    

def test_serve_local_archive_logic(get_settings):
    # create a test file first
    os.makedirs("local_archive_test", exist_ok=True)
    with open("local_archive_test/temp.txt", "w") as f:
        f.write("test")

    try:
        # modify the settings
        get_settings.SERVE_LOCAL_ARCHIVE = "/app/local_archive_test"
        from web.main import app_factory
        app = app_factory(get_settings)
        
        # test
        client = TestClient(app)
        r = client.get("/app/local_archive_test/temp.txt")
        assert r.status_code == 200
        assert r.text == "test"
    finally:
        # cleanup
        shutil.rmtree("local_archive_test")
