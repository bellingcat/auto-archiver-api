from datetime import datetime
from unittest.mock import patch

import pytest
import yaml
from db import models
from shared.settings import Settings

authors = ["rick@example.com", "morty@example.com", "jerry@example.com"]


@pytest.fixture()
def test_data(db_session):

    # creates 3 users
    for email in authors:
        db_session.add(models.User(email=email))
    db_session.commit()
    assert db_session.query(models.User).count() == 3

    # creates 100 archives for 3 users over 2 months with repeating URLs
    for i in range(100):
        author = authors[i % 3]
        archive = models.Archive(
            id=f"archive-id-456-{i}",
            url=f"https://example-{i%3}.com",
            result={},
            public=author == "jerry@example.com",
            author_id=author,
            group_id="spaceship" if author == "morty@example.com" and i % 2 == 0 else None,
            created_at=datetime(2021, (i % 2) + 1, (i % 25) + 1)
        )
        if i % 5 == 0:
            archive.tags.append(models.Tag(id=f"tag-{i}"))
        if i % 10 == 0:
            archive.tags.append(models.Tag(id=f"tag-second-{i}"))
        if i % 4 == 0:
            archive.tags.append(models.Tag(id=f"tag-third-{i}"))
        for j in range(10):
            archive.urls.append(models.ArchiveUrl(url=f"https://example-{i}.com/{j}", key=f"media_{j}"))
        db_session.add(archive)

    db_session.commit()

    assert db_session.query(models.Archive).count() == 100
    assert db_session.query(models.Tag).count() == 20 + 10 + 25
    assert db_session.query(models.ArchiveUrl).count() == 1000
    assert db_session.query(models.ArchiveUrl).filter(models.ArchiveUrl.archive_id == "archive-id-456-0").count() == 10

    # setup groups
    assert db_session.query(models.Group).count() == 0
    from db import crud
    crud.upsert_user_groups(db_session)
    assert db_session.query(models.Group).count() == 3
    assert db_session.query(models.User).count() == 4


def test_get_archive(test_data, db_session):
    from db import crud
    from core.config import ALLOW_ANY_EMAIL

    print(db_session.query(models.Group).all())

    # each author's archives work
    assert (a0 := crud.get_archive(db_session, "archive-id-456-0", authors[0])) is not None
    assert a0.id == "archive-id-456-0"
    assert a0.url == "https://example-0.com"
    assert a0.author_id == authors[0]
    assert a0.public == False

    assert crud.get_archive(db_session, "archive-id-456-1", authors[1]) is not None
    assert crud.get_archive(db_session, "archive-id-456-2", authors[2]) is not None

    # ALLOW_ANY_EMAIL
    assert crud.get_archive(db_session, "archive-id-456-0", ALLOW_ANY_EMAIL) is not None
    assert crud.get_archive(db_session, "archive-id-456-1", ALLOW_ANY_EMAIL) is not None

    # not found
    assert crud.get_archive(db_session, "archive-missing", authors[0]) is None

    # public
    assert (a_public := crud.get_archive(db_session, "archive-id-456-2", authors[0])) is not None
    assert a_public.public == True

    # not public - rick's
    assert crud.get_archive(db_session, "archive-id-456-0", authors[1]) is None


def test_search_archives_by_url(test_data, db_session):
    from db import crud
    from core.config import ALLOW_ANY_EMAIL

    # rick's archives are private
    assert len(crud.search_archives_by_url(db_session, "https://example-0.com", "rick@example.com")) == 34
    assert len(crud.search_archives_by_url(db_session, "https://example-0.com", ALLOW_ANY_EMAIL)) == 34
    assert len(crud.search_archives_by_url(db_session, "https://example-0.com", "morty@example.com")) == 0

    # morty's archives are public but half are in spaceship group
    assert len(crud.search_archives_by_url(db_session, "https://example-1.com", "rick@example.com")) == 16

    # jerry's archives are public
    assert len(crud.search_archives_by_url(db_session, "https://example-2.com", "jerry@example.com")) == 33
    assert len(crud.search_archives_by_url(db_session, "https://example-2.com", "rick@example.com")) == 33

    # fuzzy search
    assert len(crud.search_archives_by_url(db_session, "https://example", ALLOW_ANY_EMAIL)) == 100
    assert len(crud.search_archives_by_url(db_session, "https://EXAMPLE", ALLOW_ANY_EMAIL)) == 100
    assert len(crud.search_archives_by_url(db_session, "2.com", ALLOW_ANY_EMAIL)) == 33

    # absolute search
    assert len(crud.search_archives_by_url(db_session, "example-2.com", ALLOW_ANY_EMAIL, absolute_search=True)) == 0
    assert len(crud.search_archives_by_url(db_session, "https://example-2.com", ALLOW_ANY_EMAIL, absolute_search=True)) == 33

    # archived_after
    assert len(crud.search_archives_by_url(db_session, "https://example", ALLOW_ANY_EMAIL, archived_after=datetime(2010, 1, 1))) == 100
    assert len(crud.search_archives_by_url(db_session, "https://example", ALLOW_ANY_EMAIL, archived_after=datetime(2021, 1, 15))) == 70
    assert len(crud.search_archives_by_url(db_session, "https://example", ALLOW_ANY_EMAIL, archived_after=datetime(2031, 1, 1))) == 0

    # archived before
    assert len(crud.search_archives_by_url(db_session, "https://example", ALLOW_ANY_EMAIL, archived_before=datetime(2010, 1, 1))) == 0
    assert len(crud.search_archives_by_url(db_session, "https://example", ALLOW_ANY_EMAIL, archived_before=datetime(2021, 1, 15))) == 28
    assert len(crud.search_archives_by_url(db_session, "https://example", ALLOW_ANY_EMAIL, archived_before=datetime(2031, 1, 1))) == 100

    # archived before and after
    assert len(crud.search_archives_by_url(db_session, "https://example", ALLOW_ANY_EMAIL, archived_after=datetime(2001, 1, 1), archived_before=datetime(2031, 1, 11))) == 100
    assert len(crud.search_archives_by_url(db_session, "https://example", ALLOW_ANY_EMAIL, archived_after=datetime(2021, 1, 14), archived_before=datetime(2021, 1, 16))) == 2

    # limit
    assert len(crud.search_archives_by_url(db_session, "https://example", ALLOW_ANY_EMAIL, limit=10)) == 10

    # skip
    assert len(crud.search_archives_by_url(db_session, "https://example", ALLOW_ANY_EMAIL, skip=10)) == 90


def test_search_archives_by_email(test_data, db_session):
    from core.config import ALLOW_ANY_EMAIL
    from db import crud

    # lower/upper case
    assert len(crud.search_archives_by_email(db_session, "rick@example.com")) == 34
    assert len(crud.search_archives_by_email(db_session, "RICK@example.com")) == 34

    # ALLOW_ANY_EMAIL is not a user
    assert len(crud.search_archives_by_email(db_session, ALLOW_ANY_EMAIL)) == 0

    # most recent first
    a1 = crud.search_archives_by_email(db_session, "rick@example.com", limit=1)
    assert len(a1) == 1
    assert a1[0].created_at == datetime(2021, 2, 25)

    # earliest is the last
    a2 = crud.search_archives_by_email(db_session, "rick@example.com", skip=33)
    assert len(a2) == 1
    assert a2[0].created_at == datetime(2021, 1, 1)


@patch("db.crud.DATABASE_QUERY_LIMIT", new=25)
def test_max_query_limit(test_data, db_session):
    from db import crud
    from core.config import ALLOW_ANY_EMAIL

    assert len(crud.search_archives_by_url(db_session, "https://example", ALLOW_ANY_EMAIL)) == 25
    assert len(crud.search_archives_by_url(db_session, "https://example", ALLOW_ANY_EMAIL, limit=1000)) == 25

    assert len(crud.search_archives_by_email(db_session, "rick@example.com")) == 25
    assert len(crud.search_archives_by_email(db_session, "rick@example.com", limit=1000)) == 25


def test_create_task(db_session):
    from db import crud
    from db import schemas

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
    nt = crud.create_task(db_session, task, [models.Tag(id="tag-101")], [models.ArchiveUrl(url="https://example-0.com/0", key="media_0")])

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
    nt = crud.create_task(db_session, task, [], [])
    assert nt is not None
    assert nt.id == "archive-id-456-102"
    assert nt.url == "https://example-0.com"
    assert nt.author_id == "rick@example.com"
    assert nt.public == False
    assert nt.group_id == "spaceship"
    assert len(nt.tags) == 0
    assert len(nt.urls) == 0
    assert nt.created_at is not None


def test_soft_delete(test_data, db_session):
    from db import crud

    # none deleted yet
    assert crud.get_archive(db_session, "archive-id-456-0", "rick@example.com") is not None
    assert db_session.query(models.Archive).filter(models.Archive.deleted == True).count() == 0

    # delete
    assert crud.soft_delete_task(db_session, "archive-id-456-0", "rick@example.com") == True

    # ensure soft delete
    assert db_session.query(models.Archive).filter(models.Archive.deleted == True).count() == 1
    assert crud.get_archive(db_session, "archive-id-456-0", "rick@example.com") is None

    # already deleted
    assert crud.soft_delete_task(db_session, "archive-id-456-0", "rick@example.com") == False


def test_count_archives(test_data, db_session):
    from db import crud

    assert crud.count_archives(db_session) == 100
    db_session.query(models.Archive).filter(models.Archive.id == "archive-id-456-0").delete()
    db_session.commit()
    assert crud.count_archives(db_session) == 99


def test_count_archive_urls(test_data, db_session):
    from db import crud

    assert crud.count_archive_urls(db_session) == 1000
    db_session.query(models.ArchiveUrl).filter(models.ArchiveUrl.url == "https://example-0.com/0").delete()
    db_session.commit()
    assert crud.count_archive_urls(db_session) == 999

    db_session.query(models.Archive).filter(models.Archive.id == "archive-id-456-0").delete()
    db_session.commit()
    # no Cascade is enabled
    assert crud.count_archives(db_session) == 99
    assert crud.count_archive_urls(db_session) == 999

def test_count_users(test_data, db_session):
    from db import crud

    assert crud.count_users(db_session) == 4
    db_session.query(models.User).filter(models.User.email == "rick@example.com").delete()
    db_session.commit()
    assert crud.count_users(db_session) == 3

def test_count_by_users_since(test_data, db_session):
    from db import crud

    # 100y window
    assert len(cu := crud.count_by_user_since(db_session, 60 * 60 * 24 * 31 * 12 * 100)) == 3
    assert cu[0].total == 34
    assert cu[1].total == 33
    assert cu[2].total == 33


def test_create_tag(db_session):
    from db import crud

    assert db_session.query(models.Tag).count() == 0

    # create first
    create_tag = crud.create_tag(db_session, "tag-101")
    assert create_tag is not None
    assert create_tag.id == "tag-101"
    assert db_session.query(models.Tag).count() == 1
    assert db_session.query(models.Tag).filter(models.Tag.id == "tag-101").first() == create_tag

    # same id does not add new db entry
    existing_tag = crud.create_tag(db_session, "tag-101")
    assert existing_tag == create_tag
    assert db_session.query(models.Tag).count() == 1

    # create second
    second_tag = crud.create_tag(db_session, "tag-102")
    assert second_tag is not None
    assert second_tag.id == "tag-102"
    assert db_session.query(models.Tag).count() == 2

def test_is_active_user(test_data, db_session):
    from db import crud

    assert crud.is_active_user(db_session, "") == False
    assert crud.is_active_user(db_session, "example.com") == False
    assert crud.is_active_user(db_session, "unknown@example.com") == False
    assert crud.is_active_user(db_session, "rick@example.com") == True
    assert crud.is_active_user(db_session, "RICK@example.com") == True


def test_is_user_in_group(test_data, db_session):
    from db import crud
    from core.config import ALLOW_ANY_EMAIL

    # see user-groups.test.yaml
    test_pairs = [
        (ALLOW_ANY_EMAIL, "spaceship", True),
        (ALLOW_ANY_EMAIL, "non-existant!@#!%!", True),

        ("rick@example.com", "spaceship", True),
        ("rick@example.com", "SPACESHIP", False),
        ("RICK@example.com", "interdimensional", True),
        ("rick@example.com", "the-jerrys-club", False),

        ("morty@example.com", "spaceship", True),
        ("morty@example.com", "interdimensional", False),
        ("morty@example.com", "the-jerrys-club", False),

        ("jerry@example.com", "spaceship", False),
        ("jerry@example.com", "interdimensional", False),
        ("jerry@example.com", "the-jerrys-club", True),

        ("rick@example.com", "animated-characters", True),
        ("morty@example.com", "animated-characters", True),
        ("jerry@example.com", "animated-characters", True),

        ("rick@example.com", "", False),
        ("", "spaceship", False),
        ("BADEMAILexample.com", "spaceship", False),
    ]
    for email, group, expected in test_pairs:
        assert crud.is_user_in_group(db_session, group, email) == expected


def test_create_or_get_user(test_data, db_session):
    from db import crud

    assert db_session.query(models.User).count() == 4

    assert (u1 := crud.create_or_get_user(db_session, "rick@example.com")) is not None
    assert u1.email == "rick@example.com"
    assert u1.is_active == True

    assert (u2 := crud.create_or_get_user(db_session, "beth@example.com")) is not None
    assert u2.email == "beth@example.com"
    assert u2.is_active == True

    assert db_session.query(models.User).count() == 5


def test_get_group(test_data, db_session):
    from db import crud

    assert db_session.query(models.Group).count() == 3

    assert (g1 := crud.create_or_get_group(db_session, "spaceship")) is not None
    assert g1.id == "spaceship"
    assert len(g1.users) == 2
    assert [u.email for u in g1.users] == ["rick@example.com", "morty@example.com"]

    assert (g2 := crud.create_or_get_group(db_session, "the-jerrys-club")) is not None
    assert g2.id == "the-jerrys-club"
    assert len(g2.users) == 1
    assert g2.users[0].email == "jerry@example.com"

    assert (g3 := crud.create_or_get_group(db_session, "this-is-a-new-group")) is not None
    assert g3.id == "this-is-a-new-group"
    assert len(g3.users) == 0

    assert db_session.query(models.Group).count() == 4


def test_upsert_user_groups(db_session):
    from db import crud

    @patch('db.crud.get_settings', new = lambda: bad_setings)
    def test_missing_yaml(db_session):
        with pytest.raises(FileNotFoundError):
            crud.upsert_user_groups(db_session)


    @patch('db.crud.get_settings', new = lambda: bad_setings)
    def test_broken_yaml(db_session):
        with pytest.raises(yaml.YAMLError):
            crud.upsert_user_groups(db_session)

    bad_setings = Settings(_env_file=".env.test")

    bad_setings.USER_GROUPS_FILENAME = "tests/user-groups.test.missing.yaml"
    test_missing_yaml(db_session)

    bad_setings.USER_GROUPS_FILENAME = "tests/user-groups.test.broken.yaml"
    test_broken_yaml(db_session)