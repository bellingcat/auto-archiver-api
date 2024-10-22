from unittest import mock

from unittest.mock import MagicMock, patch

import pytest

from db import models, schemas
from auto_archiver import Metadata
from auto_archiver.core import Media


@pytest.fixture()
def worker_init():
    from worker.main import at_start
    at_start(None)


class Test_create_archive_task():
    URL = "https://example-live.com"
    archive = schemas.ArchiveCreate(url=URL, tags=[], public=True, group_id=None, author_id="rick@example.com")

    @patch("worker.main.insert_result_into_db")
    @patch("worker.main.is_group_invalid_for_user", return_value=None)
    @patch("worker.main.choose_orchestrator")
    @patch("celery.app.task.Task.request")
    def test_success(self, m_req, m_choose, m_is_group, m_insert, worker_init, db_session):
        from worker.main import create_archive_task

        m_req.id = "this-just-in"
        mock_orchestrator = self.mock_orchestrator_choice(m_choose)

        task = create_archive_task(self.archive.model_dump_json())

        m_choose.assert_called_once()
        mock_orchestrator.feed_item.assert_called_once()

        assert task["status"] == "success"
        assert task["metadata"]["url"] == self.URL
        assert len(task["media"]) == 0

    @patch("worker.main.is_group_invalid_for_user", return_value=True)
    def test_raise_invalid(self, m_is_group, worker_init):
        from worker.main import create_archive_task
        with pytest.raises(Exception):
            create_archive_task(self.archive.model_dump_json())

    @patch("worker.main.insert_result_into_db", side_effect=Exception)
    @patch("worker.main.is_group_invalid_for_user", return_value=False)
    @patch("worker.main.choose_orchestrator")
    def test_raise_db_error(self, m_choose, m_is_group, m_insert, worker_init):
        from worker.main import create_archive_task
        mock_orchestrator = self.mock_orchestrator_choice(m_choose)

        with pytest.raises(Exception):
            create_archive_task(self.archive.model_dump_json())
        mock_orchestrator.feed_item.assert_called_once()

    def mock_orchestrator_choice(self, m_choose):
        mock_orchestrator = mock.MagicMock()
        mock_orchestrator.configure_mock(feed_item=mock.MagicMock(return_value=Metadata().set_url(self.URL).success()))
        m_choose.return_value = mock_orchestrator
        return mock_orchestrator


class Test_create_sheet_task():
    URL = "https://example-live.com"
    sheet = schemas.SubmitSheet(sheet_name="Sheet", sheet_id="123", author_id="rick@example.com", group_id=None)

    # @patch("worker.main.insert_result_into_db")
    @patch("worker.main.models.generate_uuid", return_value="constant-uuid")
    @patch("worker.main.is_group_invalid_for_user", return_value=False)
    @patch("worker.main.ArchivingOrchestrator")
    def test_success(self, m_orch_generator, m_is_group, m_uuid, worker_init, db_session):
        from worker.main import create_sheet_task

        assert db_session.query(models.Archive).filter(models.Archive.url == self.URL).count() == 0

        mock_metadata = Metadata().set_url(self.URL).success()
        mock_metadata.add_media(Media("fn1.txt", urls=["outcome1.com"]))
        m_orch = MagicMock()
        m_orch.feed.return_value = iter([False, mock_metadata, mock_metadata])
        m_orch_generator.return_value = m_orch

        res = create_sheet_task(self.sheet.model_dump_json())
        print(res)
        assert res["archived"] == 1
        assert res["failed"] == 0
        assert len(res["errors"]) == 0
        assert res["sheet"] == "Sheet"
        assert res["sheet_id"] == "123"
        assert res["success"] == True
        assert len(res["time"]) > 0

        # query created archive entry
        inserted = db_session.query(models.Archive).filter(models.Archive.url == self.URL).one()
        assert inserted is not None
        assert inserted.url == self.URL
        assert inserted.tags[0].id == "gsheet"

    @patch("worker.main.insert_result_into_db", side_effect=Exception("some-error"))
    @patch("worker.main.models.generate_uuid", return_value="constant-uuid")
    @patch("worker.main.is_group_invalid_for_user", return_value=False)
    @patch("worker.main.ArchivingOrchestrator")
    def test_has_exception(self, m_orch_generator, m_is_group, m_uuid, worker_init, db_session):
        from worker.main import create_sheet_task

        assert db_session.query(models.Archive).filter(models.Archive.url == self.URL).count() == 0

        mock_metadata = Metadata().set_url(self.URL).success()
        mock_metadata.add_media(Media("fn1.txt", urls=["outcome1.com"]))
        m_orch = MagicMock()
        m_orch.feed.return_value = iter([mock_metadata])
        m_orch_generator.return_value = m_orch

        res = create_sheet_task(self.sheet.model_dump_json())
        print(res)
        assert res["archived"] == 0
        assert res["failed"] == 1
        assert res["errors"] == ["some-error"]
        assert res["sheet_id"] == "123"
        assert res["success"] == True

        assert db_session.query(models.Archive).filter(models.Archive.url == self.URL).count() == 0

    @patch("worker.main.is_group_invalid_for_user", return_value="Access denied")
    def test_error_access(self, m_insert, worker_init, db_session):
        from worker.main import create_sheet_task

        res = create_sheet_task(self.sheet.model_dump_json())
        assert "error" in res
        assert res["error"] == "Access denied"


def test_choose_orchestrator(worker_init):
    from worker.main import choose_orchestrator

    assert choose_orchestrator(None, "rick@example.com").__class__.__name__ == "ArchivingOrchestrator"


@patch("worker.main.get_user_first_group", return_value="does-not-exist")
def test_choose_orchestrator_assertion(worker_init):
    from worker.main import choose_orchestrator

    with pytest.raises(Exception):
        choose_orchestrator(None, "rick@example.com")


@patch("worker.main.read_user_groups")
def test_get_user_first_group(m_read_user_groups, worker_init):
    from worker.main import get_user_first_group

    m_read_user_groups.return_value = {"users": {}}
    assert get_user_first_group("email1") == "default"
    m_read_user_groups.return_value = {"users": {"email1": []}}
    assert get_user_first_group("email1") == "default"
    m_read_user_groups.return_value = {"users": {"email1": ["group1", "group2"]}}
    assert get_user_first_group("email1") == "group1"


def test_is_group_invalid_for_user(worker_init, db_session):
    from worker.main import is_group_invalid_for_user
    from db.crud import upsert_user_groups

    upsert_user_groups(db_session)

    assert is_group_invalid_for_user(True, "", "") == False
    assert is_group_invalid_for_user(False, "", "") == False

    assert is_group_invalid_for_user(False, "default", "") == "User  is not part of default, no permission"
    assert is_group_invalid_for_user(False, "spaceship", "jerry@example.com") == "User jerry@example.com is not part of spaceship, no permission"

    assert is_group_invalid_for_user(False, "spaceship", "rick@example.com") == False


def test_get_all_urls(worker_init, db_session):
    from worker.main import get_all_urls
    from auto_archiver import Metadata

    meta = Metadata().set_url("https://example.com")
    m1 = meta.add_media(Media("fn1.txt", urls=["outcome1.com"]))
    m2 = meta.add_media(Media("fn2.txt", urls=["outcome2.com"]))
    m3 = meta.add_media(Media("fn3.txt", urls=["outcome3.com"]))
    m1.set("screenshot", Media("screenshot.png", urls=["screenshot.com"]))
    m2.set("thumbnails", [Media("thumb1.png", urls=["thumb1.com"]), Media("thumb2.png", urls=["thumb2.com"])])
    m3.set("ssl_data", Media("ssl_data.txt", urls=["ssl_data.com"]).to_dict())
    m3.set("bad_data", {"bad": "dict is ignored"})

    urls = [u.url for u in get_all_urls(meta)]
    assert len(urls) == 7
    assert "outcome1.com" in urls
    assert "outcome2.com" in urls
    assert "outcome3.com" in urls
    assert "screenshot.com" in urls
    assert "thumb1.com" in urls
    assert "thumb2.com" in urls
    assert "ssl_data.com" in urls
