import os
from fastapi.testclient import TestClient


def test_serve_local_archive_logic():
    os.environ["SERVE_LOCAL_ARCHIVE"] = "/app/local_archive_test"

    # create a test file
    os.makedirs("local_archive_test", exist_ok=True)
    with open("local_archive_test/temp.txt", "w") as f:
        f.write("test")

    from main import app, setup_local_archive_serve
    setup_local_archive_serve()
    client = TestClient(app)

    r = client.get("/app/local_archive_test/temp.txt")
    assert r.status_code == 200
    assert r.text == "test"

    os.remove("local_archive_test/temp.txt")
    os.rmdir("local_archive_test")
