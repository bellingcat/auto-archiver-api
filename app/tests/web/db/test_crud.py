from datetime import datetime
from unittest.mock import patch

import pytest
import yaml
from app.shared.db import models
from app.shared.settings import Settings

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

    # creates a sheet for each user
    for i, email in enumerate(authors):
        db_session.add(models.Sheet(id=f"sheet-{i}", name=f"sheet-{i}", author_id=email, group_id=None, frequency="daily"))
        if email == "rick@example.com":
            db_session.add(models.Sheet(id=f"sheet-{i}-2", name=f"sheet-{i}-2", author_id=email, group_id="spaceship", frequency="hourly"))

    db_session.commit()

    assert db_session.query(models.Archive).count() == 100
    assert db_session.query(models.Tag).count() == 20 + 10 + 25
    assert db_session.query(models.ArchiveUrl).count() == 1000
    assert db_session.query(models.ArchiveUrl).filter(models.ArchiveUrl.archive_id == "archive-id-456-0").count() == 10

    # setup groups
    assert db_session.query(models.Group).count() == 0
    from app.web.db import crud
    crud.upsert_user_groups(db_session)
    assert db_session.query(models.Group).count() == 4
    assert db_session.query(models.User).count() == 3


def test_get_archive(test_data, db_session):
    from app.web.db import crud
    from app.shared.config import ALLOW_ANY_EMAIL

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
    from app.web.db import crud
    from app.shared.config import ALLOW_ANY_EMAIL

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
    assert len(crud.search_archives_by_url(db_session, "https://example", ALLOW_ANY_EMAIL, limit=-1)) == 1

    # skip
    assert len(crud.search_archives_by_url(db_session, "https://example", ALLOW_ANY_EMAIL, skip=10)) == 90


def test_search_archives_by_email(test_data, db_session):
    from app.shared.config import ALLOW_ANY_EMAIL
    from app.web.db import crud

    # lower/upper case
    assert len(crud.search_archives_by_email(db_session, "rick@example.com")) == 34

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


@patch("app.web.db.crud.DATABASE_QUERY_LIMIT", new=25)
def test_max_query_limit(test_data, db_session):
    from app.web.db import crud
    from app.shared.config import ALLOW_ANY_EMAIL

    assert len(crud.search_archives_by_url(db_session, "https://example", ALLOW_ANY_EMAIL)) == 25
    assert len(crud.search_archives_by_url(db_session, "https://example", ALLOW_ANY_EMAIL, limit=1000)) == 25

    assert len(crud.search_archives_by_email(db_session, "rick@example.com")) == 25
    assert len(crud.search_archives_by_email(db_session, "rick@example.com", limit=1000)) == 25


def test_soft_delete(test_data, db_session):
    from app.web.db import crud

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
    from app.web.db import crud

    assert crud.count_archives(db_session) == 100
    db_session.query(models.Archive).filter(models.Archive.id == "archive-id-456-0").delete()
    db_session.commit()
    assert crud.count_archives(db_session) == 99


def test_count_archive_urls(test_data, db_session):
    from app.web.db import crud

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
    from app.web.db import crud

    assert crud.count_users(db_session) == 3
    db_session.query(models.User).filter(models.User.email == "rick@example.com").delete()
    db_session.commit()
    assert crud.count_users(db_session) == 2


def test_count_by_users_since(test_data, db_session):
    from app.web.db import crud

    # 100y window
    assert len(cu := crud.count_by_user_since(db_session, 60 * 60 * 24 * 31 * 12 * 100)) == 3
    assert cu[0].total == 34
    assert cu[1].total == 33
    assert cu[2].total == 33


def test_is_user_in_group(test_data, db_session):
    from app.web.db import crud
    from app.shared.config import ALLOW_ANY_EMAIL

    # see user-groups.test.yaml
    test_pairs = [
        (ALLOW_ANY_EMAIL, "spaceship", True),
        (ALLOW_ANY_EMAIL, "non-existant!@#!%!", True),

        ("rick@example.com", "spaceship", True),
        ("rick@example.com", "SPACESHIP", False),
        ("rick@example.com", "interdimensional", True),
        ("rick@example.com", "animated-characters", True),
        ("rick@example.com", "the-jerrys-club", False),

        ("morty@example.com", "spaceship", True),
        ("morty@example.com", "interdimensional", False),
        ("morty@example.com", "the-jerrys-club", False),

        ("jerry@example.com", "spaceship", False),
        ("jerry@example.com", "interdimensional", False),
        ("jerry@example.com", "the-jerrys-club", False),  # group not in 'groups'

        ("rick@example.com", "animated-characters", True),
        ("morty@example.com", "animated-characters", True),
        ("jerry@example.com", "animated-characters", True),
        ("anyone@example.com", "animated-characters", True),
        ("anyone@birdy.com", "animated-characters", True),

        ("summer@herself.com", "animated-characters", False),

        ("rick@example.com", "", False),
        ("", "spaceship", False),
        ("bademailexample.com", "spaceship", False),
    ]
    for email, group, expected in test_pairs:
        print(f"{email} in {group} == {expected}")
        assert crud.is_user_in_group(email, group) == expected



def test_upsert_group(test_data, db_session):
    from app.web.db import crud

    assert db_session.query(models.Group).count() == 4

    repeatable_params = ["desc 1", "orch.yaml", "sheet.yaml", {"read": ["all"]}, ["example.com"]]

    assert (g1 := crud.upsert_group(db_session, "spaceship", *repeatable_params)) is not None
    assert g1.id == "spaceship"
    assert g1.description == "desc 1"
    assert g1.orchestrator == "orch.yaml"
    assert g1.orchestrator_sheet == "sheet.yaml"
    assert g1.permissions == {"read": ["all"]}
    assert g1.domains == ["example.com"]
    assert len(g1.users) == 2
    assert [u.email for u in g1.users] == ["rick@example.com", "morty@example.com"]

    assert (g2 := crud.upsert_group(db_session, "interdimensional", *repeatable_params)) is not None
    assert g2.id == "interdimensional"
    assert len(g2.users) == 1
    assert [u.email for u in g2.users] == ["rick@example.com"]

    assert (g3 := crud.upsert_group(db_session, "this-is-a-new-group", *repeatable_params)) is not None
    assert g3.id == "this-is-a-new-group"
    assert len(g3.users) == 0

    assert db_session.query(models.Group).count() == 5


def test_upsert_user_groups(db_session):
    from app.web.db import crud

    @patch('app.web.db.crud.get_settings', new=lambda: bad_setings)
    def test_missing_yaml(db_session):
        with pytest.raises(FileNotFoundError):
            crud.upsert_user_groups(db_session)

    @patch('app.web.db.crud.get_settings', new=lambda: bad_setings)
    def test_broken_yaml(db_session):
        with pytest.raises(yaml.YAMLError):
            crud.upsert_user_groups(db_session)

    bad_setings = Settings(_env_file=".env.test")

    bad_setings.USER_GROUPS_FILENAME = "app/tests/user-groups.test.missing.yaml"
    test_missing_yaml(db_session)

    bad_setings.USER_GROUPS_FILENAME = "app/tests/user-groups.test.broken.yaml"
    test_broken_yaml(db_session)


def test_create_sheet(db_session):
    from app.web.db import crud

    assert db_session.query(models.Sheet).count() == 0

    s = crud.create_sheet(db_session, "sheet-id-123", "sheet name", "email@example.com", "group-id", "hourly")
    assert s is not None
    assert s.id == "sheet-id-123"
    assert s.name == "sheet name"
    assert s.author_id == "email@example.com"
    assert s.group_id == "group-id"
    assert s.frequency == "hourly"

    assert db_session.query(models.Sheet).count() == 1

    # duplicate id
    import sqlalchemy
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        crud.create_sheet(db_session, "sheet-id-123", "I thought this was another sheet", "email", "group-id", "hourly")


def test_get_user_sheet(test_data, db_session):
    from app.web.db import crud

    assert crud.get_user_sheet(db_session, "", "sheet-0") is None
    assert crud.get_user_sheet(db_session, "morty@example.com", "sheet-0") is None

    assert crud.get_user_sheet(db_session, "rick@example.com", "sheet-0") is not None
    assert crud.get_user_sheet(db_session, "rick@example.com", "sheet-0-2") is not None
    assert crud.get_user_sheet(db_session, "morty@example.com", "sheet-1") is not None


def test_get_user_sheets(test_data, db_session):
    from app.web.db import crud

    assert len(crud.get_user_sheets(db_session, "")) == 0
    rick_sheets = crud.get_user_sheets(db_session, "rick@example.com")
    assert len(rick_sheets) == 2
    assert [s.id for s in rick_sheets] == ["sheet-0", "sheet-0-2"]
    assert len(crud.get_user_sheets(db_session, "morty@example.com")) == 1


def test_delete_sheet(test_data, db_session):
    from app.web.db import crud

    assert crud.delete_sheet(db_session, "sheet-0", "") == False
    assert crud.delete_sheet(db_session, "sheet-0", "rick@example.com") == True
    assert crud.delete_sheet(db_session, "sheet-0", "rick@example.com") == False
