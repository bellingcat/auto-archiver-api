import os
from fastapi.testclient import TestClient
from shared.settings import get_settings


import shutil

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
