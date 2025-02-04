
from typing import Dict, Set
import sqlalchemy
from sqlalchemy.orm import Session
from sqlalchemy import func
from db import crud, models
from datetime import datetime
from shared.user_groups import GroupPermissions


class UserState:
    """
    Manage a user's state and permissions
    """

    def __init__(self, db: Session, email: str):
        self.db = db
        self.email = email.lower()

    @property
    def permissions(self) -> Dict[str, GroupPermissions]:
        """
        Returns a dict of all group permissions and a special {"all": read/archive_url/archive_sheet} key
        """
        if not hasattr(self, '_permissions'):
            self._permissions = {}
            self._permissions["all"] = GroupPermissions(
                read=self.read,
                read_public=self.read_public,
                archive_url=self.archive_url,
                archive_sheet=self.archive_sheet,
            )
            for group in self.user_groups:
                if not group.permissions: continue
                self._permissions[group.id] = GroupPermissions(**group.permissions)
        return self._permissions

    @property
    def user_groups_names(self):
        if not hasattr(self, '_user_groups_names'):
            self._user_groups_names = crud.get_user_groups(self.email)
        return self._user_groups_names

    @property
    def user_groups(self):
        if not hasattr(self, '_user_groups'):
            self._user_groups = self.db.query(models.Group).filter(
                models.Group.id.in_(self.user_groups_names)
            ).all()
        return self._user_groups

    @property
    def read(self) -> Set[str] | bool:
        """
        Read can be a list of group names or True, if all can be read.
        """
        if not hasattr(self, '_read'):
            self._read = set()
            for group in self.user_groups:
                if not group.permissions: continue
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
        if not hasattr(self, '_read_public'):
            self._read_public = False
            for group in self.user_groups:
                if not group.permissions: continue
                if group.permissions.get("read_public", False):
                    self._read_public = True
                    return self._read_public
        return self._read_public

    @property
    def archive_url(self) -> bool:
        """
        Archive URL permission
        """
        if not hasattr(self, '_archive_url'):
            self._archive_url = False
            for group in self.user_groups:
                if not group.permissions: continue
                if group.permissions.get("archive_url", False):
                    self._archive_url = True
                    return self._archive_url
        return self._archive_url

    @property
    def archive_sheet(self) -> bool:
        """
        Archive sheet permission
        """
        if not hasattr(self, '_archive_sheet'):
            self._archive_sheet = False
            for group in self.user_groups:
                if not group.permissions: continue
                if group.permissions.get("archive_sheet", False):
                    self._archive_sheet = True
                    return self._archive_sheet
        return self._archive_sheet

    @property
    def sheet_frequency(self):
        if not hasattr(self, '_sheet_frequency'):
            self._sheet_frequency = set()
            for group in self.user_groups:
                if not group.permissions: continue
                self._sheet_frequency.update(group.permissions.get("sheet_frequency", None))
        return self._sheet_frequency

    @property
    def active(self) -> bool:
        """
        A user is active if they can read/archive anything
        """
        if not hasattr(self, '_active'):
            self._active = bool(self.read or self.read_public or self.archive_url or self.archive_sheet)
        return self._active

    def in_group(self, group_id: str) -> bool:
        return group_id in self.user_groups_names

    def has_quota_monthly_sheets(self, group_id: str) -> bool:
        """
        checks if a user has reached their sheet quota for a given group
        """
        if group_id not in self.permissions: 
            return False

        user_sheets = self.db.query(models.Sheet).filter(models.Sheet.author_id == self.email, models.Sheet.group_id == group_id).count()
        
        sheet_quota = self.permissions[group_id].max_sheets
        if sheet_quota == -1: 
            return True
        return user_sheets < sheet_quota

    def has_quota_max_monthly_urls(self) -> bool:
        """
        checks if a user has reached their monthly url quota
        """
        quota = 0
        for group in self.user_groups:
            if not group.permissions: continue
            max_monthly_urls = group.permissions.get("max_monthly_urls", 0)
            if max_monthly_urls == -1: return True
            quota = max(quota, max_monthly_urls)

        current_month = datetime.now().month
        current_year = datetime.now().year
        user_urls = self.db.query(models.Archive).filter(
            models.Archive.author_id == self.email,
            func.extract('month', models.Archive.created_at) == current_month,
            func.extract('year', models.Archive.created_at) == current_year
        ).count()

        return user_urls < quota

    def has_quota_max_monthly_mbs(self) -> bool:
        """
        checks if a user has reached their monthly mb quota
        """
        quota = 0
        for group in self.user_groups:
            if not group.permissions: continue
            max_monthly_mbs = group.permissions.get("max_monthly_mbs", 0)
            if max_monthly_mbs == -1: return True
            quota = max(quota, max_monthly_mbs)

        current_month = datetime.now().month
        current_year = datetime.now().year

        # find and sum all user bytes over this month
        user_bytes = self.db.query(models.Archive).filter(
            models.Archive.author_id == self.email,
            func.extract('month', models.Archive.created_at) == current_month,
            func.extract('year', models.Archive.created_at) == current_year
        ).with_entities(func.coalesce(func.sum(
            func.coalesce(
                func.cast(
                    func.json_extract(models.Archive.result, '$.metadata.total_bytes'),
                    sqlalchemy.Integer
                ), 0
            )
        ), 0).label('total')).scalar()

        # convert bytes to mb
        user_mbs = int(user_bytes / 1024 / 1024)
        return user_mbs < quota

    def can_manually_trigger(self, group_id:str) -> bool:
        """
        checks if a user is allowed to manually trigger a sheet
        """
        if group_id not in self.permissions: 
            return False
        
        return self.permissions[group_id].manually_trigger_sheet

    def is_sheet_frequency_allowed(self, group_id:str, frequency: str) -> bool:
        """
        checks if a user is allowed to create a sheet with this frequency for this group
        """
        if group_id not in self.permissions: 
            return False
        
        return frequency in self.permissions[group_id].sheet_frequency
