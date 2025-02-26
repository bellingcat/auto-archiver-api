from datetime import datetime

from app.shared.db import models, worker_crud
from tests.web.db.test_crud import test_data


def test_update_sheet_last_url_archived_at(db_session):

    # Create test sheet
    test_sheet = models.Sheet(id="sheet-123")
    db_session.add(test_sheet)
    db_session.commit()

    # Test updating existing sheet
    assert isinstance(test_sheet.last_url_archived_at, datetime)
    before = test_sheet.last_url_archived_at
    assert worker_crud.update_sheet_last_url_archived_at(db_session, "sheet-123") is True
    db_session.refresh(test_sheet)
    assert isinstance(test_sheet.last_url_archived_at, datetime)
    assert test_sheet.last_url_archived_at > before

    # Test non-existent sheet
    assert worker_crud.update_sheet_last_url_archived_at(db_session, "non-existent-sheet") is False

def test_get_group(test_data, db_session):
    from app.shared.db import worker_crud

    assert worker_crud.get_group(db_session, "spaceship") is not None
    assert worker_crud.get_group(db_session, "interdimensional") is not None
    assert worker_crud.get_group(db_session, "animated-characters") is not None
    assert worker_crud.get_group(db_session, "non-existent!@#!%!") is None


def test_create_or_get_user(test_data, db_session):
    from app.shared.db import worker_crud

    assert db_session.query(models.User).count() == 3

    # already exists
    assert (u1 := worker_crud.create_or_get_user(db_session, "rick@example.com")) is not None
    assert u1.email == "rick@example.com"

    # new user
    assert (u2 := worker_crud.create_or_get_user(db_session, "beth@example.com")) is not None
    assert u2.email == "beth@example.com"

    assert db_session.query(models.User).count() == 4


def test_create_tag(db_session):
    from app.shared.db import worker_crud

    assert db_session.query(models.Tag).count() == 0

    # create first
    create_tag = worker_crud.create_tag(db_session, "tag-101")
    assert create_tag is not None
    assert create_tag.id == "tag-101"
    assert db_session.query(models.Tag).count() == 1
    assert db_session.query(models.Tag).filter(models.Tag.id == "tag-101").first() == create_tag

    # same id does not add new db entry
    existing_tag = worker_crud.create_tag(db_session, "tag-101")
    assert existing_tag == create_tag
    assert db_session.query(models.Tag).count() == 1

    # create second
    second_tag = worker_crud.create_tag(db_session, "tag-102")
    assert second_tag is not None
    assert second_tag.id == "tag-102"
    assert db_session.query(models.Tag).count() == 2


def test_create_task(db_session):
    from app.shared import schemas
    from app.shared.db import worker_crud

    task = schemas.ArchiveCreate(
        id="archive-id-456-101",
        url="https://example-0.com",
        result={},
        public=False,
        author_id="rick@example.com",
        group_id="spaceship",
        tags=[],
        urls=[]
    )

    # with tags and urls
    nt = worker_crud.create_archive(db_session, task, [models.Tag(id="tag-101")], [models.ArchiveUrl(url="https://example-0.com/0", key="media_0")])

    assert nt is not None
    assert nt.id == "archive-id-456-101"
    assert nt.url == "https://example-0.com"
    assert nt.author_id == "rick@example.com"
    assert nt.public == False
    assert nt.group_id == "spaceship"
    assert len(nt.tags) == 1
    assert nt.tags[0].id == "tag-101"
    assert len(nt.urls) == 1
    assert nt.urls[0].url == "https://example-0.com/0"
    assert nt.urls[0].key == "media_0"
    assert nt.created_at is not None

    # without tags and urls
    task.id = "archive-id-456-102"
    nt = worker_crud.create_archive(db_session, task, [], [])
    assert nt is not None
    assert nt.id == "archive-id-456-102"
    assert nt.url == "https://example-0.com"
    assert nt.author_id == "rick@example.com"
    assert nt.public == False
    assert nt.group_id == "spaceship"
    assert len(nt.tags) == 0
    assert len(nt.urls) == 0
    assert nt.created_at is not None
