from datetime import datetime
from typing import Dict, Set

import sqlalchemy
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.shared.db import models
from app.shared.schemas import Usage, UsageResponse
from app.shared.user_groups import GroupInfo, GroupPermissions
from app.web.db import crud
from app.web.utils.misc import convert_priority_to_queue_dict


class UserState:
    """
    Manage a user's state and permissions
    """

    def __init__(self, db: Session, email: str):
        self.db = db
        self.email = email.lower()
        self._permissions = {}

    @property
    def permissions(self) -> Dict[str, GroupInfo]:
        """
        Returns a dict of all group permissions and a special {"all": read/archive_url/archive_sheet} key
        """
        if not self._permissions:
            self._permissions["all"] = GroupInfo(
                read=self.read,
                read_public=self.read_public,
                archive_url=self.archive_url,
                archive_sheet=self.archive_sheet,
                # below are relevant only for /url endpoints
                max_archive_lifespan_months=self.max_archive_lifespan_months,
                max_monthly_urls=self.max_monthly_urls,
                max_monthly_mbs=self.max_monthly_mbs,
                priority=self.priority,
            )
            for group in self.user_groups:
                if not group.permissions:
                    continue
                self._permissions[group.id] = GroupInfo(
                    **group.permissions,
                    description=group.description,
                    service_account_email=group.service_account_email,
                )
        return self._permissions

    @property
    def user_groups_names(self):
        if not hasattr(self, "_user_groups_names"):
            self._user_groups_names = crud.get_user_group_names(
                self.db, self.email
            ) + ["default"]
        return self._user_groups_names

    @property
    def user_groups(self):
        if not hasattr(self, "_user_groups"):
            self._user_groups = crud.get_user_groups_by_name(
                self.db, self.user_groups_names
            )
        return self._user_groups

    @property
    def read(self) -> Set[str] | bool:
        """
        Read can be a list of group names or True, if all can be read.
        """
        if not hasattr(self, "_read"):
            self._read = set()
            for group in self.user_groups:
                if not group.permissions:
                    continue
                group_read_permissions = group.permissions.get("read", [])
                if "all" in group_read_permissions:
                    self._read = True
                    return self._read
                else:
                    self._read.update(group.permissions.get("read", []))
        return self._read

    @property
    def read_public(self) -> bool:
        """
        Read public permission
        """
        if not hasattr(self, "_read_public"):
            self._read_public = False
            for group in self.user_groups:
                if not group.permissions:
                    continue
                if group.permissions.get("read_public", False):
                    self._read_public = True
                    return self._read_public
        return self._read_public

    @property
    def archive_url(self) -> bool:
        """
        Archive URL permission
        """
        if not hasattr(self, "_archive_url"):
            self._archive_url = False
            for group in self.user_groups:
                if not group.permissions:
                    continue
                if group.permissions.get("archive_url", False):
                    self._archive_url = True
                    return self._archive_url
        return self._archive_url

    @property
    def archive_sheet(self) -> bool:
        """
        Archive sheet permission
        """
        if not hasattr(self, "_archive_sheet"):
            self._archive_sheet = False
            for group in self.user_groups:
                if not group.permissions:
                    continue
                if group.permissions.get("archive_sheet", False):
                    self._archive_sheet = True
                    return self._archive_sheet
        return self._archive_sheet

    @property
    def sheet_frequency(self):
        if not hasattr(self, "_sheet_frequency"):
            self._sheet_frequency = set()
            for group in self.user_groups:
                if not group.permissions:
                    continue
                self._sheet_frequency.update(
                    group.permissions.get("sheet_frequency", None)
                )
        return self._sheet_frequency

    @property
    def max_archive_lifespan_months(self) -> int:
        if not hasattr(self, "_max_archive_lifespan_months"):
            self._max_archive_lifespan_months = (
                self._helper_for_grouping_max_numerical_permissions(
                    "max_archive_lifespan_months"
                )
            )
        return self._max_archive_lifespan_months

    @property
    def max_monthly_urls(self) -> int:
        if not hasattr(self, "_max_monthly_urls"):
            self._max_monthly_urls = (
                self._helper_for_grouping_max_numerical_permissions(
                    "max_monthly_urls"
                )
            )
        return self._max_monthly_urls

    @property
    def max_monthly_mbs(self) -> int:
        if not hasattr(self, "_max_monthly_mbs"):
            self._max_monthly_mbs = (
                self._helper_for_grouping_max_numerical_permissions(
                    "max_monthly_mbs"
                )
            )
        return self._max_monthly_mbs

    @property
    def priority(self) -> str:
        if not hasattr(self, "_priority"):
            self._priority = "low"
            for group in self.user_groups:
                if not group.permissions:
                    continue
                if group.permissions.get("priority", self._priority) == "high":
                    self._priority = "high"
                    break
        return self._priority

    @property
    def active(self) -> bool:
        """
        A user is active if they can read/archive anything
        """
        if not hasattr(self, "_active"):
            self._active = bool(
                self.read
                or self.read_public
                or self.archive_url
                or self.archive_sheet
            )
        return self._active

    def _helper_for_grouping_max_numerical_permissions(
        self, permission_name: str
    ) -> int:
        """
        Iterates one of the numerical permissions where -1 means no restrictions and returns either -1 or the maximum value, defaults according to GroupPermissions
        """
        default = GroupPermissions.model_fields[permission_name].default
        max_value = default
        for group in self.user_groups:
            if not group.permissions:
                continue
            group_value = group.permissions.get(permission_name, default)
            if group_value == -1:
                max_value = -1
                return max_value
            max_value = max(max_value, group_value)
        return max_value

    def in_group(self, group_id: str) -> bool:
        return group_id in self.user_groups_names

    def usage(self) -> Dict:
        """
        returns the monthly quotas for the URLs/MBs and the totals for Sheets
        """
        current_month = datetime.now().month
        current_year = datetime.now().year

        # find and sum all user sheets over this month
        user_sheets = (
            self.db.query(
                models.Sheet.group_id,
                func.count(models.Sheet.id).label("sheet_count"),
            )
            .filter(models.Sheet.author_id == self.email)
            .group_by(models.Sheet.group_id)
            .all()
        )

        sheets_by_group = {
            sheet.group_id: sheet.sheet_count for sheet in user_sheets
        }

        # find and sum all user urls over this month
        urls_by_group = (
            self.db.query(
                models.Archive.group_id,
                func.count(models.Archive.id).label("url_count"),
                func.coalesce(
                    func.sum(
                        func.coalesce(
                            func.cast(
                                func.json_extract(
                                    models.Archive.result,
                                    "$.metadata.total_bytes",
                                ),
                                sqlalchemy.Integer,
                            ),
                            0,
                        )
                    ),
                    0,
                ).label("total_bytes"),
            )
            .filter(
                models.Archive.author_id == self.email,
                func.extract("month", models.Archive.created_at)
                == current_month,
                func.extract("year", models.Archive.created_at) == current_year,
            )
            .group_by(models.Archive.group_id)
            .all()
        )

        # merge the two queries
        usage_by_group: Dict[str, Usage] = {
            (url.group_id or ""): Usage(
                monthly_urls=url.url_count,
                monthly_mbs=int(url.total_bytes / 1024 / 1024),
            )
            for url in urls_by_group
        }
        for group_id, sheet_count in sheets_by_group.items():
            group_id = group_id or ""
            if group_id in usage_by_group:
                usage_by_group[group_id].total_sheets = sheet_count
            else:
                usage_by_group[group_id] = Usage(total_sheets=sheet_count)

        # calculate totals
        total_sheets = sum([sheet.sheet_count for sheet in user_sheets])
        total_bytes = sum([url.total_bytes for url in urls_by_group])
        total_urls = sum([url.url_count for url in urls_by_group])

        return UsageResponse(
            monthly_urls=total_urls,
            monthly_mbs=int(total_bytes / 1024 / 1024),
            total_sheets=total_sheets,
            groups=usage_by_group,
        )

    def has_quota_monthly_sheets(self, group_id: str) -> bool:
        """
        checks if a user has reached their sheet quota for a given group
        """
        if group_id not in self.permissions:
            return False

        user_sheets = (
            self.db.query(models.Sheet)
            .filter(
                models.Sheet.author_id == self.email,
                models.Sheet.group_id == group_id,
            )
            .count()
        )

        sheet_quota = self.permissions[group_id].max_sheets
        if sheet_quota == -1:
            return True
        return user_sheets < sheet_quota

    def has_quota_max_monthly_urls(self, group_id: str) -> bool:
        """
        checks if a user has reached their monthly url quota for a group, if global then group should be empty string
        """
        quota = 0
        if not group_id:
            quota = self.max_monthly_urls
        else:
            if group_id not in self.permissions:
                return False
            quota = self.permissions[group_id].max_monthly_urls

        if quota == -1:
            return True

        current_month = datetime.now().month
        current_year = datetime.now().year
        user_urls = (
            self.db.query(models.Archive)
            .filter(
                models.Archive.author_id == self.email,
                models.Archive.group_id == group_id,
                func.extract("month", models.Archive.created_at)
                == current_month,
                func.extract("year", models.Archive.created_at) == current_year,
            )
            .count()
        )

        return user_urls < quota

    def has_quota_max_monthly_mbs(self, group_id: str) -> bool:
        """
        checks if a user has reached their monthly MBs quota for a group, if global then group should be empty string
        """
        quota = 0
        if not group_id:
            quota = self.max_monthly_mbs
        else:
            if group_id not in self.permissions:
                return False
            quota = self.permissions[group_id].max_monthly_mbs

        if quota == -1:
            return True

        current_month = datetime.now().month
        current_year = datetime.now().year

        # find and sum all user bytes over this month
        user_bytes = (
            self.db.query(models.Archive)
            .filter(
                models.Archive.author_id == self.email,
                models.Archive.group_id == group_id,
                func.extract("month", models.Archive.created_at)
                == current_month,
                func.extract("year", models.Archive.created_at) == current_year,
            )
            .with_entities(
                func.coalesce(
                    func.sum(
                        func.coalesce(
                            func.cast(
                                func.json_extract(
                                    models.Archive.result,
                                    "$.metadata.total_bytes",
                                ),
                                sqlalchemy.Integer,
                            ),
                            0,
                        )
                    ),
                    0,
                ).label("total")
            )
            .scalar()
        )

        # convert bytes to mb
        user_mbs = int(user_bytes / 1024 / 1024)
        return user_mbs < quota

    def can_manually_trigger(self, group_id: str) -> bool:
        """
        checks if a user is allowed to manually trigger a sheet
        """
        if group_id not in self.permissions:
            return False

        return self.permissions[group_id].manually_trigger_sheet

    def is_sheet_frequency_allowed(self, group_id: str, frequency: str) -> bool:
        """
        checks if a user is allowed to create a sheet with this frequency for this group
        """
        if group_id not in self.permissions:
            return False

        return frequency in self.permissions[group_id].sheet_frequency

    def priority_group(self, group_id: str) -> str:
        priority = "low"
        for group in self.user_groups:
            if group.id != group_id:
                continue
            if not group.permissions:
                continue
            priority = group.permissions.get("priority", priority)
            break
        return convert_priority_to_queue_dict(priority)
