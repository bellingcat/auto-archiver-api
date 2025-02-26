from datetime import datetime
from unittest.mock import patch

import pytest
from auto_archiver.core import Media, Metadata

from app.shared import schemas
from app.shared.db import models


class TestCreateArchiveTask:
    URL = "https://example-live.com"
    archive = schemas.ArchiveCreate(
        url=URL,
        tags=["tag-celery"],
        public=True,
        author_id="rick@example.com",
        group_id="interstellar",
    )

    @patch("app.worker.main.ArchivingOrchestrator")
    @patch("app.worker.main.get_all_urls", return_value=[])
    @patch("app.worker.main.insert_result_into_db")
    @patch("app.worker.main.get_store_until", return_value=datetime.now())
    @patch(
        "app.worker.main.get_orchestrator_args", return_value=["arg1", "arg2"]
    )
    @patch("celery.app.task.Task.request")
    def test_success(
        self,
        m_req,
        m_args,
        m_store,
        m_insert,
        m_urls,
        m_orchestrator,
        db_session,
    ):
        from app.worker.main import create_archive_task

        m_req.id = "this-just-in"
        m_orchestrator.return_value.feed.return_value = iter(
            [Metadata().set_url(self.URL).success()]
        )

        task = create_archive_task(self.archive.model_dump_json())

        m_args.assert_called_once()
        m_store.assert_called_once_with("interstellar")
        m_insert.assert_called_once()
        m_urls.assert_called_once()
        m_orchestrator.return_value.feed.assert_called_once()
        m_orchestrator.return_value.setup.assert_called_once()

        assert task["status"] == "success"
        assert task["metadata"]["url"] == self.URL
        assert len(task["media"]) == 0

    def test_raise_invalid(self):
        from app.worker.main import create_archive_task

        with pytest.raises(Exception) as _:
            create_archive_task(self.archive.model_dump_json())

    @patch("app.worker.main.ArchivingOrchestrator")
    @patch("app.worker.main.get_orchestrator_args")
    def test_raise_db_error(self, m_args, m_orchestrator):
        from app.worker.main import create_archive_task

        m_orchestrator.return_value.feed.side_effect = Exception(
            "Orchestrator failed"
        )

        with pytest.raises(Exception) as e:
            create_archive_task(self.archive.model_dump_json())
        assert str(e.value) == "Orchestrator failed"
        m_args.assert_called_once()
        m_orchestrator.return_value.feed.assert_called_once()

    @patch("app.worker.main.ArchivingOrchestrator")
    @patch("app.worker.main.insert_result_into_db", return_value=None)
    @patch("app.worker.main.get_orchestrator_args")
    def test_raise_empty_result(self, m_args, m_insert, m_orchestrator):
        from app.worker.main import create_archive_task

        m_orchestrator.return_value.feed.return_value = iter([None])

        with pytest.raises(Exception) as e:
            create_archive_task(self.archive.model_dump_json())
        assert str(e.value) == "UNABLE TO archive: https://example-live.com"
        m_orchestrator.return_value.feed.assert_called_once()


class TestCreateSheetTask:
    URL = "https://example-live.com"
    sheet = schemas.SubmitSheet(
        sheet_id="123",
        author_id="rick@example.com",
        group_id="interstellar",
        tags=["spaceship"],
    )

    @patch("app.worker.main.get_all_urls", return_value=[])
    @patch("app.worker.main.ArchivingOrchestrator")
    @patch("app.worker.main.models.generate_uuid", return_value="constant-uuid")
    @patch("app.worker.main.get_store_until", return_value=datetime.now())
    @patch("app.worker.main.get_orchestrator_args")
    def test_success(
        self, m_args, m_store, m_uuid, m_orchestrator, m_urls, db_session
    ):
        from app.worker.main import create_sheet_task

        assert (
            db_session.query(models.Archive)
            .filter(models.Archive.url == self.URL)
            .count()
            == 0
        )

        mock_metadata = Metadata().set_url(self.URL).success()
        mock_metadata.add_media(Media("fn1.txt", urls=["outcome1.com"]))

        m_orchestrator.return_value.feed.return_value = iter(
            [False, mock_metadata, mock_metadata]
        )

        res = create_sheet_task(self.sheet.model_dump_json())

        m_args.assert_called_once_with(
            "interstellar", True, ["--gsheet_feeder.sheet_id", "123"]
        )
        m_orchestrator.return_value.setup.assert_called_once()
        m_orchestrator.return_value.feed.assert_called_once()
        m_store.assert_called_with("interstellar")
        assert m_store.call_count == 2
        assert m_uuid.call_count == 2
        assert isinstance(res, dict)
        assert res["stats"]["archived"] == 1
        assert res["stats"]["failed"] == 1
        assert len(res["stats"]["errors"]) == 1
        assert res["sheet_id"] == "123"
        assert res["success"]
        assert isinstance(res["time"], datetime)

        # query created archive entry
        inserted = (
            db_session.query(models.Archive)
            .filter(models.Archive.url == self.URL)
            .one()
        )
        assert inserted is not None
        assert inserted.url == self.URL
        assert len(inserted.tags) == 1
        assert inserted.tags[0].id == "spaceship"
        assert inserted.group_id == "interstellar"
        assert inserted.author_id == "rick@example.com"
        assert inserted.public is False


def test_get_all_urls(db_session):
    from app.worker.main import get_all_urls

    meta = Metadata().set_url("https://example.com")
    m1 = meta.add_media(Media("fn1.txt", urls=["outcome1.com"]))
    m2 = meta.add_media(Media("fn2.txt", urls=["outcome2.com"]))
    m3 = meta.add_media(Media("fn3.txt", urls=["outcome3.com"]))
    m1.set("screenshot", Media("screenshot.png", urls=["screenshot.com"]))
    m2.set(
        "thumbnails",
        [
            Media("thumb1.png", urls=["thumb1.com"]),
            Media("thumb2.png", urls=["thumb2.com"]),
        ],
    )
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
