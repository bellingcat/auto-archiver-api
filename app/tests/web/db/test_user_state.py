
from unittest.mock import MagicMock, PropertyMock, patch
import pytest

from app.shared.db import models
from app.shared.user_groups import GroupInfo, GroupPermissions
from app.web.db.user_state import UserState


def fresh_user_state():
    return UserState(None, email="test@example.com")


@pytest.fixture
def user_state():
    return fresh_user_state()


@pytest.fixture
def user_state_with_groups(user_state):
    user_groups = [
        models.Group(id="no-permissions", permissions={}),
        models.Group(id="group1", description="this is g1", service_account_email="sa1@example.com", permissions={"read": ["group1", "no-permissions"], "read_public": True, "archive_url": True, "archive_sheet": True, "max_archive_lifespan_months": 24, "max_monthly_urls": 100, "max_monthly_mbs": 1000, "priority": "high"}),
        models.Group(id="group2", description="this is g2", service_account_email="sa2@example.com", permissions={"read": ["all"], "read_public": True, "archive_url": False, "archive_sheet": False, "max_archive_lifespan_months": -1, "max_monthly_urls": -1, "max_monthly_mbs": -1, "priority": "low", "sheet_frequency": {"daily"}}),
    ]

    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=user_groups):
        yield user_state


def test_permissions(user_state_with_groups):
    permissions = user_state_with_groups.permissions

    assert permissions["all"].read == True
    assert permissions["all"].read_public == True
    assert permissions["all"].archive_url == True
    assert permissions["all"].archive_sheet == True
    assert permissions["all"].max_archive_lifespan_months == -1
    assert permissions["all"].max_monthly_urls == -1
    assert permissions["all"].max_monthly_mbs == -1
    assert permissions["all"].priority == "high"

    assert permissions["group1"].read == set(["group1", "no-permissions"])
    assert permissions["group1"].read_public == True
    assert permissions["group1"].archive_url == True
    assert permissions["group1"].archive_sheet == True
    assert permissions["group1"].max_archive_lifespan_months == 24
    assert permissions["group1"].max_monthly_urls == 100
    assert permissions["group1"].max_monthly_mbs == 1000
    assert permissions["group1"].priority == "high"

    assert permissions["group2"].read == set(["all"])
    assert permissions["group2"].read_public == True
    assert permissions["group2"].archive_url == False
    assert permissions["group2"].archive_sheet == False
    assert permissions["group2"].max_archive_lifespan_months == -1
    assert permissions["group2"].max_monthly_urls == -1
    assert permissions["group2"].max_monthly_mbs == -1
    assert permissions["group2"].priority == "low"

    assert len(permissions) == 3


def test_user_groups_names(user_state):
    with patch('app.web.db.crud.get_user_group_names', return_value=["group1", "group2"]) as mock:
        assert user_state.user_groups_names == ["group1", "group2", "default"]
        mock.assert_called_once_with(None, "test@example.com")


def test_user_groups(user_state):
    with patch('app.web.db.crud.get_user_groups_by_name', return_value=[MagicMock(), MagicMock()]) as mock:
        user_state._user_groups_names = ["group1", "group2"]
        assert len(user_state.user_groups) == 2
        mock.assert_called_once_with(None, ["group1", "group2"])


def test_read():
    us = fresh_user_state()

    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="no-permissions", permissions={})]) as mock:
        assert not hasattr(us, "_read")
        assert us.read == set()
        assert us._read == set()
        mock.assert_called_once()

    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="group1", permissions={"read": ["group1", "no-permissions"]})]):
        assert us.read == set(["group1", "no-permissions"])

    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="group1", permissions={"read": ["all"]})]):
        assert us.read == True


def test_read_public():
    us = fresh_user_state()

    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="no-permissions", permissions={})]) as mock:
        assert not hasattr(us, "_read_public")
        assert us.read_public == False
        assert us._read_public == False
        mock.assert_called_once()
        # no new calls
        assert us.read_public == False
        mock.assert_called_once()

    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="group1", permissions={"read_public": True})]):
        assert us.read_public == True

    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="group1", permissions={"read_public": False})]):
        assert us.read_public == False


def test_archive_url():
    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="no-permissions", permissions={})]) as mock:
        assert not hasattr(us, "_archive_url")
        assert us.archive_url == False
        assert us._archive_url == False
        mock.assert_called_once()
        # no new calls
        assert us.archive_url == False
        mock.assert_called_once()

    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="group1", permissions={"archive_url": False})]):
        assert us.archive_url == False

    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="group1", permissions={"archive_url": True})]):
        assert us.archive_url == True


def test_archive_sheet():
    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="no-permissions", permissions={})]) as mock:
        assert not hasattr(us, "_archive_sheet")
        assert us.archive_sheet == False
        assert us._archive_sheet == False
        mock.assert_called_once()
        # no new calls
        assert us.archive_sheet == False
        mock.assert_called_once()

    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="group1", permissions={"archive_sheet": False})]):
        assert us.archive_sheet == False

    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="group1", permissions={"archive_sheet": True})]):
        assert us.archive_sheet == True


def test_sheet_frequency():
    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="no-permissions", permissions={})]) as mock:
        assert not hasattr(us, "_sheet_frequency")
        assert us.sheet_frequency == set()
        assert us._sheet_frequency == set()
        mock.assert_called_once()
        # no new calls
        assert us.sheet_frequency == set()
        mock.assert_called_once()

    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="group1", permissions={"sheet_frequency": ["daily", "hourly"]})]):
        assert us.sheet_frequency == {"daily", "hourly"}

    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="group1", permissions={"sheet_frequency": []})]):
        assert us.sheet_frequency == set()


def test_max_archive_lifespan_months():
    us = fresh_user_state()
    default = GroupPermissions.model_fields["max_archive_lifespan_months"].default
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="no-permissions", permissions={})]) as mock:
        assert not hasattr(us, "_max_archive_lifespan_months")
        assert us.max_archive_lifespan_months == default
        assert us._max_archive_lifespan_months == default
        mock.assert_called_once()
        # no new calls
        assert us.max_archive_lifespan_months == default
        mock.assert_called_once()

    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="group1", permissions={"max_archive_lifespan_months": 24})]):
        assert us.max_archive_lifespan_months == 24

    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="group1", permissions={"max_archive_lifespan_months": 150}), models.Group(id="group2", permissions={"max_archive_lifespan_months": -1})]):
        assert us.max_archive_lifespan_months == -1


def test_max_monthly_urls():
    us = fresh_user_state()
    default = GroupPermissions.model_fields["max_monthly_urls"].default
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="no-permissions", permissions={})]) as mock:
        assert not hasattr(us, "_max_monthly_urls")
        assert us.max_monthly_urls == default
        assert us._max_monthly_urls == default
        mock.assert_called_once()
        # no new calls
        assert us.max_monthly_urls == default
        mock.assert_called_once()

    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="group1", permissions={"max_monthly_urls": 100})]):
        assert us.max_monthly_urls == 100

    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="group1", permissions={"max_monthly_urls": 150}), models.Group(id="group2", permissions={"max_monthly_urls": -1})]):
        assert us.max_monthly_urls == -1


def test_max_monthly_mbs():
    us = fresh_user_state()
    default = GroupPermissions.model_fields["max_monthly_mbs"].default
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="no-permissions", permissions={})]) as mock:
        assert not hasattr(us, "_max_monthly_mbs")
        assert us.max_monthly_mbs == default
        assert us._max_monthly_mbs == default
        mock.assert_called_once()
        # no new calls
        assert us.max_monthly_mbs == default
        mock.assert_called_once()

    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="group1", permissions={"max_monthly_mbs": 1000})]):
        assert us.max_monthly_mbs == 1000

    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="group1", permissions={"max_monthly_mbs": 1500}), models.Group(id="group2", permissions={"max_monthly_mbs": -1})]):
        assert us.max_monthly_mbs == -1


def test_priority(user_state):
    default = GroupPermissions.model_fields["priority"].default
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="no-permissions", permissions={})]) as mock:
        assert not hasattr(user_state, "_priority")
        assert user_state.priority == default
        assert user_state._priority == default
        mock.assert_called_once()
        # no new calls
        assert user_state.priority == default
        mock.assert_called_once()

    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="group1", permissions={"priority": "high"})]):
        assert us.priority == "high"

    us = fresh_user_state()
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[models.Group(id="group1", permissions={"priority": "low"}), models.Group(id="group2", permissions={"priority": "medium"})]):
        assert us.priority == "low"


def test_active():
    for read, read_public, archive_url, archive_sheet, is_active in [
        (False, False, False, False, False),
        (True, False, False, False, True),
        (False, True, False, False, True),
        (False, False, True, False, True),
        (False, False, False, True, True)
    ]:
        us = fresh_user_state()
        with patch.object(UserState, 'read', new_callable=PropertyMock, return_value=read), \
                patch.object(UserState, 'read_public', new_callable=PropertyMock, return_value=read_public), \
                patch.object(UserState, 'archive_url', new_callable=PropertyMock, return_value=archive_url), \
                patch.object(UserState, 'archive_sheet', new_callable=PropertyMock, return_value=archive_sheet):
            assert us.active == is_active


def test_in_group(user_state):
    with patch.object(UserState, 'user_groups_names', new_callable=PropertyMock, return_value=["group1", "group2"]):
        assert user_state.in_group("group1") == True
        assert user_state.in_group("group2") == True
        assert user_state.in_group("group3") == False


def test_usage(db_session):
    user_state = UserState(db_session, email="test@example.com")
    user_sheets = [
        MagicMock(group_id="group1", sheet_count=5),
        MagicMock(group_id="group2", sheet_count=10),
        MagicMock(group_id="group3", sheet_count=100),
    ]
    bytes = [1000000, 2000000, 3000000]
    urls_by_group = [
        MagicMock(group_id="group1", url_count=50, total_bytes=bytes[0]),
        MagicMock(group_id="group2", url_count=100, total_bytes=bytes[1]),
        MagicMock(group_id="group4", url_count=5, total_bytes=bytes[2]),
    ]
    megabytes = int(sum(bytes) / 1024 / 1024)

    with patch.object(db_session, 'query', side_effect=[
        MagicMock(filter=MagicMock(return_value=MagicMock(group_by=MagicMock(return_value=MagicMock(all=MagicMock(return_value=user_sheets)))))),
        MagicMock(filter=MagicMock(return_value=MagicMock(group_by=MagicMock(return_value=MagicMock(all=MagicMock(return_value=urls_by_group))))))
    ]):
        usage_response = user_state.usage()

        assert usage_response.monthly_urls == 155
        assert usage_response.monthly_mbs == megabytes
        assert usage_response.total_sheets == 115

        assert usage_response.groups["group1"].monthly_urls == 50
        assert usage_response.groups["group1"].monthly_mbs == int(bytes[0] / 1024 / 1024)
        assert usage_response.groups["group1"].total_sheets == 5

        assert usage_response.groups["group2"].monthly_urls == 100
        assert usage_response.groups["group2"].monthly_mbs == int(bytes[1] / 1024 / 1024)
        assert usage_response.groups["group2"].total_sheets == 10

        assert usage_response.groups["group3"].monthly_urls == 0
        assert usage_response.groups["group3"].monthly_mbs == 0
        assert usage_response.groups["group3"].total_sheets == 100

        assert usage_response.groups["group4"].monthly_urls == 5
        assert usage_response.groups["group4"].monthly_mbs == int(bytes[2] / 1024 / 1024)
        assert usage_response.groups["group4"].total_sheets == 0


def test_has_quota_monthly_sheets(db_session):
    us = UserState(db_session, email="test@example.com")

    test_cases = [
        ({"unkonwn": GroupInfo(max_sheets=5)}, 1, False),
        ({"group1": GroupInfo(max_sheets=-1)}, 1000, True),
        ({"group1": GroupInfo(max_sheets=5)}, 3, True),
        ({"group1": GroupInfo(max_sheets=5)}, 5, False),
        ({"group1": GroupInfo(max_sheets=5)}, 6, False),
    ]

    for permissions, count, expected in test_cases:
        with patch.object(UserState, 'permissions', new_callable=PropertyMock, return_value=permissions):
            with patch.object(us.db, 'query', return_value=MagicMock(filter=MagicMock(return_value=MagicMock(count=MagicMock(return_value=count))))):
                assert us.has_quota_monthly_sheets("group1") == expected


def test_has_quota_max_monthly_urls(db_session):
    us = UserState(db_session, email="test@example.com")

    test_cases = [
        ({"group1": GroupInfo(max_monthly_urls=-1)}, 1000, True),
        ({"group1": GroupInfo(max_monthly_urls=100)}, 50, True),
        ({"group1": GroupInfo(max_monthly_urls=100)}, 100, False),
        ({"group1": GroupInfo(max_monthly_urls=100)}, 150, False),
    ]

    for permissions, count, expected in test_cases:
        with patch.object(UserState, 'permissions', new_callable=PropertyMock, return_value=permissions):
            with patch.object(us.db, 'query', return_value=MagicMock(filter=MagicMock(return_value=MagicMock(count=MagicMock(return_value=count))))):
                assert us.has_quota_max_monthly_urls("group1") == expected
    test_cases = [
        (-1, 1000, True),
        (100, 50, True),
        (100, 100, False),
        (100, 150, False),
    ]

    for max_urls, count, expected in test_cases:
        with patch.object(UserState, 'max_monthly_urls', new_callable=PropertyMock, return_value=max_urls):
            with patch.object(us.db, 'query', return_value=MagicMock(filter=MagicMock(return_value=MagicMock(count=MagicMock(return_value=count))))):
                assert us.has_quota_max_monthly_urls("") == expected


def test_has_quota_max_monthly_mbs(db_session):
    us = UserState(db_session, email="test@example.com")

    test_cases = [
        ({"group1": GroupInfo(max_monthly_mbs=-1)}, 1000, True),
        ({"group1": GroupInfo(max_monthly_mbs=100)}, 50, True),
        ({"group1": GroupInfo(max_monthly_mbs=100)}, 100, False),
        ({"group1": GroupInfo(max_monthly_mbs=100)}, 150, False),
    ]

    for permissions, mbs, expected in test_cases:
        with patch.object(UserState, 'permissions', new_callable=PropertyMock, return_value=permissions):
            with patch.object(us.db, 'query', return_value=MagicMock(filter=MagicMock(return_value=MagicMock(with_entities=MagicMock(return_value=MagicMock(scalar=MagicMock(return_value=mbs * 1024 * 1024))))))):
                assert us.has_quota_max_monthly_mbs("group1") == expected

    test_cases = [
        (-1, 1000, True),
        (100, 50, True),
        (100, 100, False),
        (100, 150, False),
    ]

    for max_mbs, mbs, expected in test_cases:
        with patch.object(UserState, 'max_monthly_mbs', new_callable=PropertyMock, return_value=max_mbs):
            with patch.object(us.db, 'query', return_value=MagicMock(filter=MagicMock(return_value=MagicMock(with_entities=MagicMock(return_value=MagicMock(scalar=MagicMock(return_value=mbs * 1024 * 1024))))))):
                assert us.has_quota_max_monthly_mbs("") == expected


def test_can_manually_trigger(user_state):
    permissions = {
        "group1": GroupInfo(manually_trigger_sheet=True),
        "group2": GroupInfo(manually_trigger_sheet=False),
    }

    with patch.object(UserState, 'permissions', new_callable=PropertyMock, return_value=permissions):
        assert user_state.can_manually_trigger("group1") == True
        assert user_state.can_manually_trigger("group2") == False
        assert user_state.can_manually_trigger("group3") == False


def test_is_sheet_frequency_allowed(user_state):
    permissions = {
        "group1": GroupInfo(sheet_frequency={"daily", "hourly"}),
        "group2": GroupInfo(sheet_frequency={"daily"}),
    }

    with patch.object(UserState, 'permissions', new_callable=PropertyMock, return_value=permissions):
        assert user_state.is_sheet_frequency_allowed("group1", "daily") == True
        assert user_state.is_sheet_frequency_allowed("group1", "hourly") == True
        assert user_state.is_sheet_frequency_allowed("group1", "weekly") == False
        assert user_state.is_sheet_frequency_allowed("group2", "hourly") == False
        assert user_state.is_sheet_frequency_allowed("group2", "daily") == True
        assert user_state.is_sheet_frequency_allowed("group3", "daily") == False


def test_priority_group(user_state):
    from app.web.utils.misc import convert_priority_to_queue_dict
    with patch.object(UserState, 'user_groups', new_callable=PropertyMock, return_value=[
        models.Group(id="group1", permissions={"priority": "high"}),
        models.Group(id="group2", permissions={"priority": "medium"}),
        models.Group(id="group3", permissions={"priority": "low"}),
    ]):
        assert user_state.priority_group("group1") == convert_priority_to_queue_dict("high")
        assert user_state.priority_group("group2") == convert_priority_to_queue_dict("medium")
        assert user_state.priority_group("group3") == convert_priority_to_queue_dict("low")
        assert user_state.priority_group("group4") == convert_priority_to_queue_dict("low")
