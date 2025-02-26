from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
import sqlalchemy
import yaml
from sqlalchemy import false, true
from sqlalchemy.sql import select

from app.shared.db import models
from app.shared.settings import Settings
from app.web.config import ALLOW_ANY_EMAIL
from app.web.db import crud


AUTHOR_EMAILS = ["rick@example.com", "morty@example.com", "jerry@example.com"]


@pytest.fixture()
def test_data(db_session):
    # creates 3 users
    for email in AUTHOR_EMAILS:
        db_session.add(models.User(email=email))
    db_session.commit()
    assert db_session.query(models.User).count() == 3

    # creates 100 archives for 3 users over 2 months with repeating URLs
    for i in range(100):
        author = AUTHOR_EMAILS[i % 3]
        archive = models.Archive(
            id=f"archive-id-456-{i}",
            url=f"https://example-{i % 3}.com",
            result={},
            public=author == "jerry@example.com",
            author_id=author,
            group_id="spaceship"
            if author == "morty@example.com" and i % 2 == 0
            else None,
            created_at=datetime(2021, (i % 2) + 1, (i % 25) + 1),
        )
        if i % 5 == 0:
            archive.tags.append(models.Tag(id=f"tag-{i}"))
        if i % 10 == 0:
            archive.tags.append(models.Tag(id=f"tag-second-{i}"))
        if i % 4 == 0:
            archive.tags.append(models.Tag(id=f"tag-third-{i}"))
        for j in range(10):
            archive.urls.append(
                models.ArchiveUrl(
                    url=f"https://example-{i}.com/{j}", key=f"media_{j}"
                )
            )
        db_session.add(archive)

    # creates a sheet for each user
    for i, email in enumerate(AUTHOR_EMAILS):
        db_session.add(
            models.Sheet(
                id=f"sheet-{i}",
                name=f"sheet-{i}",
                author_id=email,
                group_id=None,
                frequency="daily",
            )
        )
        if email == "rick@example.com":
            db_session.add(
                models.Sheet(
                    id=f"sheet-{i}-2",
                    name=f"sheet-{i}-2",
                    author_id=email,
                    group_id="spaceship",
                    frequency="hourly",
                )
            )

    db_session.commit()

    assert db_session.query(models.Archive).count() == 100
    assert db_session.query(models.Tag).count() == 20 + 10 + 25
    assert db_session.query(models.ArchiveUrl).count() == 1000
    assert (
        db_session.query(models.ArchiveUrl)
        .filter(models.ArchiveUrl.archive_id == "archive-id-456-0")
        .count()
        == 10
    )

    # setup groups
    assert db_session.query(models.Group).count() == 0

    crud.upsert_user_groups(db_session)
    assert db_session.query(models.Group).count() == 4
    assert db_session.query(models.User).count() == 3


def test_search_archives_by_url(test_data, db_session):
    # Rick's archives are private
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example-0.com",
                "rick@example.com",
                True,
                False,
            )
        )
        == 34
    )
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example-0.com",
                "rick@example.com",
                [],
                False,
            )
        )
        == 34
    )
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example-0.com",
                "rick@example.com",
                [],
                True,
            )
        )
        == 34
    )
    assert (
        len(
            crud.search_archives_by_url(
                db_session, "https://example-0.com", ALLOW_ANY_EMAIL, [], False
            )
        )
        == 34
    )
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example-0.com",
                ALLOW_ANY_EMAIL,
                True,
                False,
            )
        )
        == 34
    )
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example-0.com",
                "morty@example.com",
                [],
                False,
            )
        )
        == 0
    )
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example-0.com",
                "morty@example.com",
                [],
                True,
            )
        )
        == 0
    )

    # morty's archives are public but half are in spaceship group
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example-1.com",
                "rick@example.com",
                ["spaceship"],
                False,
            )
        )
        == 16
    )
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example-1.com",
                "rick@example.com",
                True,
                False,
            )
        )
        == 16
    )
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example-1.com",
                "jerry@example.com",
                True,
                True,
            )
        )
        == 16
    )

    # Jerry's archives are public
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example-2.com",
                "jerry@example.com",
                [],
                True,
            )
        )
        == 33
    )
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example-2.com",
                "rick@example.com",
                [],
                True,
            )
        )
        == 33
    )

    # fuzzy search
    assert (
        len(
            crud.search_archives_by_url(
                db_session, "https://example", ALLOW_ANY_EMAIL, False, False
            )
        )
        == 100
    )
    assert (
        len(
            crud.search_archives_by_url(
                db_session, "https://EXAMPLE", ALLOW_ANY_EMAIL, False, False
            )
        )
        == 100
    )
    assert (
        len(
            crud.search_archives_by_url(
                db_session, "2.com", ALLOW_ANY_EMAIL, False, False
            )
        )
        == 33
    )

    # absolute search
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "example-2.com",
                ALLOW_ANY_EMAIL,
                [],
                False,
                absolute_search=True,
            )
        )
        == 0
    )
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example-2.com",
                ALLOW_ANY_EMAIL,
                [],
                False,
                absolute_search=True,
            )
        )
        == 33
    )

    # archived_after
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example",
                ALLOW_ANY_EMAIL,
                True,
                True,
                archived_after=datetime(2010, 1, 1),
            )
        )
        == 100
    )
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example",
                ALLOW_ANY_EMAIL,
                False,
                False,
                archived_after=datetime(2021, 1, 15),
            )
        )
        == 70
    )
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example",
                ALLOW_ANY_EMAIL,
                False,
                False,
                archived_after=datetime(2031, 1, 1),
            )
        )
        == 0
    )

    # archived before
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example",
                ALLOW_ANY_EMAIL,
                False,
                False,
                archived_before=datetime(2010, 1, 1),
            )
        )
        == 0
    )
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example",
                ALLOW_ANY_EMAIL,
                False,
                False,
                archived_before=datetime(2021, 1, 15),
            )
        )
        == 28
    )
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example",
                ALLOW_ANY_EMAIL,
                False,
                False,
                archived_before=datetime(2031, 1, 1),
            )
        )
        == 100
    )

    # archived before and after
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example",
                ALLOW_ANY_EMAIL,
                False,
                False,
                archived_after=datetime(2001, 1, 1),
                archived_before=datetime(2031, 1, 11),
            )
        )
        == 100
    )
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example",
                ALLOW_ANY_EMAIL,
                False,
                False,
                archived_after=datetime(2021, 1, 14),
                archived_before=datetime(2021, 1, 16),
            )
        )
        == 2
    )

    # limit
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example",
                ALLOW_ANY_EMAIL,
                False,
                False,
                limit=10,
            )
        )
        == 10
    )
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example",
                ALLOW_ANY_EMAIL,
                False,
                False,
                limit=-1,
            )
        )
        == 1
    )

    # skip
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example",
                ALLOW_ANY_EMAIL,
                False,
                False,
                skip=10,
            )
        )
        == 90
    )


def test_search_archives_by_email(test_data, db_session):
    # lower/upper case
    assert (
        len(crud.search_archives_by_email(db_session, "rick@example.com")) == 34
    )

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
    assert (
        len(
            crud.search_archives_by_url(
                db_session, "https://example", ALLOW_ANY_EMAIL, [], False
            )
        )
        == 25
    )
    assert (
        len(
            crud.search_archives_by_url(
                db_session,
                "https://example",
                ALLOW_ANY_EMAIL,
                True,
                True,
                limit=1000,
            )
        )
        == 25
    )

    assert (
        len(crud.search_archives_by_email(db_session, "rick@example.com")) == 25
    )
    assert (
        len(
            crud.search_archives_by_email(
                db_session, "rick@example.com", limit=1000
            )
        )
        == 25
    )


def test_soft_delete(test_data, db_session):
    # none deleted yet
    assert (
        db_session.query(models.Archive)
        .filter(models.Archive.id == "archive-id-456-0")
        .first()
        is not None
    )
    assert (
        db_session.query(models.Archive)
        .filter(models.Archive.deleted.is_(true()))
        .count()
        == 0
    )

    # delete
    assert (
        crud.soft_delete_archive(
            db_session, "archive-id-456-0", "rick@example.com"
        )
        is True
    )

    # ensure soft delete
    assert (
        db_session.query(models.Archive)
        .filter(models.Archive.deleted.is_(true()))
        .count()
        == 1
    )
    assert (
        db_session.query(models.Archive)
        .filter(models.Archive.id == "archive-id-456-0")
        .filter(models.Archive.deleted.is_(false()))
        .first()
        is None
    )

    # already deleted
    assert (
        crud.soft_delete_archive(
            db_session, "archive-id-456-0", "rick@example.com"
        )
        is False
    )


def test_count_archives(test_data, db_session):
    assert crud.count_archives(db_session) == 100
    db_session.query(models.Archive).filter(
        models.Archive.id == "archive-id-456-0"
    ).delete()
    db_session.commit()
    assert crud.count_archives(db_session) == 99


def test_count_archive_urls(test_data, db_session):
    assert crud.count_archive_urls(db_session) == 1000
    db_session.query(models.ArchiveUrl).filter(
        models.ArchiveUrl.url == "https://example-0.com/0"
    ).delete()
    db_session.commit()
    assert crud.count_archive_urls(db_session) == 999

    db_session.query(models.Archive).filter(
        models.Archive.id == "archive-id-456-0"
    ).delete()
    db_session.commit()
    # no Cascade is enabled
    assert crud.count_archives(db_session) == 99
    assert crud.count_archive_urls(db_session) == 999


def test_count_users(test_data, db_session):
    assert crud.count_users(db_session) == 3
    db_session.query(models.User).filter(
        models.User.email == "rick@example.com"
    ).delete()
    db_session.commit()
    assert crud.count_users(db_session) == 2


def test_count_by_users_since(test_data, db_session):
    # 100y window
    assert (
        len(
            cu := crud.count_by_user_since(
                db_session, 60 * 60 * 24 * 31 * 12 * 100
            )
        )
        == 3
    )
    assert cu[0].total == 34
    assert cu[1].total == 33
    assert cu[2].total == 33


def test_upsert_group(test_data, db_session):
    assert db_session.query(models.Group).count() == 4

    repeatable_params = [
        "desc 1",
        "orch.yaml",
        "sheet.yaml",
        "service_account_email@example.com",
        {"read": ["all"]},
        ["example.com"],
    ]

    assert (
        g1 := crud.upsert_group(db_session, "spaceship", *repeatable_params)
    ) is not None
    assert g1.id == "spaceship"
    assert g1.description == "desc 1"
    assert g1.orchestrator == "orch.yaml"
    assert g1.orchestrator_sheet == "sheet.yaml"
    assert g1.service_account_email == "service_account_email@example.com"
    assert g1.permissions == {"read": ["all"]}
    assert g1.domains == ["example.com"]
    assert len(g1.users) == 2
    assert [u.email for u in g1.users] == [
        "rick@example.com",
        "morty@example.com",
    ]

    assert (
        g2 := crud.upsert_group(
            db_session, "interdimensional", *repeatable_params
        )
    ) is not None
    assert g2.id == "interdimensional"
    assert len(g2.users) == 1
    assert [u.email for u in g2.users] == ["rick@example.com"]

    assert (
        g3 := crud.upsert_group(
            db_session, "this-is-a-new-group", *repeatable_params
        )
    ) is not None
    assert g3.id == "this-is-a-new-group"
    assert len(g3.users) == 0

    assert db_session.query(models.Group).count() == 5


def test_upsert_user_groups(db_session):
    @patch("app.web.db.crud.get_settings", new=lambda: bad_settings)
    def test_missing_yaml(db_session):
        with pytest.raises(FileNotFoundError):
            crud.upsert_user_groups(db_session)

    @patch("app.web.db.crud.get_settings", new=lambda: bad_settings)
    def test_broken_yaml(db_session):
        with pytest.raises(yaml.YAMLError):
            crud.upsert_user_groups(db_session)

    bad_settings = Settings(_env_file=".env.test")

    bad_settings.USER_GROUPS_FILENAME = (
        "app/tests/user-groups.test.missing.yaml"
    )
    test_missing_yaml(db_session)

    bad_settings.USER_GROUPS_FILENAME = "app/tests/user-groups.test.broken.yaml"
    test_broken_yaml(db_session)


def test_create_sheet(db_session):
    assert db_session.query(models.Sheet).count() == 0

    s = crud.create_sheet(
        db_session,
        "sheet-id-123",
        "sheet name",
        "email@example.com",
        "group-id",
        "hourly",
    )
    assert s is not None
    assert s.id == "sheet-id-123"
    assert s.name == "sheet name"
    assert s.author_id == "email@example.com"
    assert s.group_id == "group-id"
    assert s.frequency == "hourly"

    assert db_session.query(models.Sheet).count() == 1

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        crud.create_sheet(
            db_session,
            "sheet-id-123",
            "I thought this was another sheet",
            "email",
            "group-id",
            "hourly",
        )


def test_get_user_sheet(test_data, db_session):
    assert crud.get_user_sheet(db_session, "", "sheet-0") is None
    assert (
        crud.get_user_sheet(db_session, "morty@example.com", "sheet-0") is None
    )

    assert (
        crud.get_user_sheet(db_session, "rick@example.com", "sheet-0")
        is not None
    )
    assert (
        crud.get_user_sheet(db_session, "rick@example.com", "sheet-0-2")
        is not None
    )
    assert (
        crud.get_user_sheet(db_session, "morty@example.com", "sheet-1")
        is not None
    )


def test_get_user_sheets(test_data, db_session):
    assert len(crud.get_user_sheets(db_session, "")) == 0
    rick_sheets = crud.get_user_sheets(db_session, "rick@example.com")
    assert len(rick_sheets) == 2
    assert [s.id for s in rick_sheets] == ["sheet-0", "sheet-0-2"]
    assert len(crud.get_user_sheets(db_session, "morty@example.com")) == 1


def test_delete_sheet(test_data, db_session):
    assert crud.delete_sheet(db_session, "sheet-0", "") is False
    assert crud.delete_sheet(db_session, "sheet-0", "rick@example.com") is True
    assert crud.delete_sheet(db_session, "sheet-0", "rick@example.com") is False


@pytest.mark.asyncio
async def test_find_by_store_until(async_db_session):
    # Add archives with different store_until dates
    now = datetime.now()
    archive1 = models.Archive(
        id="archive-expired-1",
        url="https://example-expired-1.com",
        result={},
        author_id="rick@example.com",
        store_until=now - timedelta(days=1),
    )
    archive2 = models.Archive(
        id="archive-expired-2",
        url="https://example-expired-2.com",
        result={},
        author_id="rick@example.com",
        store_until=now - timedelta(hours=1),
    )
    archive3 = models.Archive(
        id="archive-active",
        url="https://example-active.com",
        result={},
        author_id="rick@example.com",
        store_until=now + timedelta(days=1),
    )
    async_db_session.add_all([archive1, archive2, archive3])
    await async_db_session.commit()

    # Should find 2 expired archives
    expired = await crud.find_by_store_until(async_db_session, now)
    assert len(list(expired)) == 2

    # Should find 1 archive expired before 2 hours ago
    expired = await crud.find_by_store_until(
        async_db_session, now - timedelta(hours=2)
    )
    assert len(list(expired)) == 1

    # Should find no archives expired before 2 days ago
    expired = await crud.find_by_store_until(
        async_db_session, now - timedelta(days=2)
    )
    assert len(list(expired)) == 0

    # Should not find deleted archives
    archive1.deleted = True
    await async_db_session.commit()
    expired = await crud.find_by_store_until(async_db_session, now)
    assert len(list(expired)) == 1


@pytest.mark.asyncio
async def test_get_sheets_by_id_hash(async_db_session):
    # Add test data
    sheets = [
        models.Sheet(
            id="sheet-0",
            name="sheet-0",
            author_id=AUTHOR_EMAILS[0],
            group_id=None,
            frequency="daily",
        ),
        models.Sheet(
            id="sheet-0-2",
            name="sheet-0-2",
            author_id=AUTHOR_EMAILS[0],
            group_id="spaceship",
            frequency="hourly",
        ),
        models.Sheet(
            id="sheet-1",
            name="sheet-1",
            author_id=AUTHOR_EMAILS[1],
            group_id=None,
            frequency="daily",
        ),
        models.Sheet(
            id="sheet-2",
            name="sheet-2",
            author_id=AUTHOR_EMAILS[2],
            group_id=None,
            frequency="daily",
        ),
    ]
    async_db_session.add_all(sheets)
    await async_db_session.commit()

    with patch("app.web.db.crud.fnv1a_hash_mod", return_value=1):
        # Test retrieving hourly sheets
        hourly_sheets = await crud.get_sheets_by_id_hash(
            async_db_session, "hourly", 4, 1
        )
        assert len(hourly_sheets) == 1
        assert hourly_sheets[0].id == "sheet-0-2"
        assert hourly_sheets[0].frequency == "hourly"

        # Test retrieving daily sheets
        daily_sheets = await crud.get_sheets_by_id_hash(
            async_db_session, "daily", 4, 1
        )
        assert len(daily_sheets) == 3
        assert all(sheet.frequency == "daily" for sheet in daily_sheets)
        assert {sheet.id for sheet in daily_sheets} == {
            "sheet-0",
            "sheet-1",
            "sheet-2",
        }

        # Test with non-matching hash
        no_sheets = await crud.get_sheets_by_id_hash(
            async_db_session, "daily", 4, 3
        )
        assert len(no_sheets) == 0

        # Test with non-existent frequency
        weekly_sheets = await crud.get_sheets_by_id_hash(
            async_db_session, "weekly", 4, 1
        )
        assert len(weekly_sheets) == 0


@pytest.mark.asyncio
async def test_delete_stale_sheets(async_db_session):
    now = datetime.now()
    active_date = now - timedelta(days=5)
    stale_date = now - timedelta(days=15)

    # Create test sheets with different last_url_archived_at dates
    sheets = [
        models.Sheet(
            id="sheet-active-1",
            name="Active Sheet 1",
            author_id="rick@example.com",
            frequency="daily",
            last_url_archived_at=active_date,
        ),
        models.Sheet(
            id="sheet-active-2",
            name="Active Sheet 2",
            author_id="morty@example.com",
            frequency="hourly",
            last_url_archived_at=active_date,
        ),
        models.Sheet(
            id="sheet-stale-1",
            name="Stale Sheet 1",
            author_id="rick@example.com",
            frequency="daily",
            last_url_archived_at=stale_date,
        ),
        models.Sheet(
            id="sheet-stale-2",
            name="Stale Sheet 2",
            author_id="morty@example.com",
            frequency="daily",
            last_url_archived_at=stale_date,
        ),
    ]
    async_db_session.add_all(sheets)
    await async_db_session.commit()

    # Should not delete sheets with 20 days inactivity threshold
    deleted = await crud.delete_stale_sheets(async_db_session, 20)
    assert len(deleted) == 0  # No sheets should be deleted
    result = await async_db_session.execute(select(models.Sheet))
    assert len(list(result.scalars())) == 4  # All sheets should remain

    # Should delete sheets with 7 days inactivity threshold
    deleted = await crud.delete_stale_sheets(async_db_session, 7)
    assert len(deleted) == 2  # Two authors affected
    assert len(deleted["rick@example.com"]) == 1  # One sheet deleted for Rick
    assert len(deleted["morty@example.com"]) == 1  # One sheet deleted for Morty
    assert deleted["rick@example.com"][0].id == "sheet-stale-1"
    assert deleted["morty@example.com"][0].id == "sheet-stale-2"

    # Verify only active sheets remain
    result = await async_db_session.execute(select(models.Sheet))
    remaining = list(result.scalars())
    assert len(remaining) == 2
    assert {s.id for s in remaining} == {"sheet-active-1", "sheet-active-2"}

    # Running again should not delete anything
    deleted = await crud.delete_stale_sheets(async_db_session, 7)
    assert len(deleted) == 0
