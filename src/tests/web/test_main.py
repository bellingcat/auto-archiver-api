import os
from fastapi.testclient import TestClient
from shared.settings import Settings


import shutil

def test_serve_local_archive_logic(settings: Settings):
    # create a test file first
    os.makedirs("local_archive_test", exist_ok=True)
    with open("local_archive_test/temp.txt", "w") as f:
        f.write("test")

    try:
        # modify the settings
        settings.SERVE_LOCAL_ARCHIVE = "/app/local_archive_test"
        from web.main import app_factory
        app = app_factory(settings)
        
        # test
        client = TestClient(app)
        r = client.get("/app/local_archive_test/temp.txt")
        assert r.status_code == 200
        assert r.text == "test"
    finally:
        # cleanup
        shutil.rmtree("local_archive_test")
