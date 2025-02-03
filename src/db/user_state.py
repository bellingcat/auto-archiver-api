
import sqlalchemy
from sqlalchemy.orm import Session
from sqlalchemy import func
from db import crud, models
from datetime import datetime


class UserState:
    """
    Manage a user's state and permissions
    """

    def __init__(self, db: Session, email: str, active=False):
        self.db = db
        self.email = email
        self.active = active

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
    def allowed_frequencies(self):
        if not hasattr(self, '_sheet_frequency'):
            self._sheet_frequency = set()
            for group in self.user_groups:
                if not group.permissions: continue
                self._sheet_frequency.update(group.permissions.get("sheet_frequency", None))
        return self._sheet_frequency

    @property
    def sheet_quota(self):
        """
        infer the user's sheet quota from the groups
        -1 means unlimited
        """
        if not hasattr(self, '_sheet_quota'):
            self._sheet_quota = 0
            for group in self.user_groups:
                if not group.permissions: continue
                max_sheets = group.permissions.get("max_sheets", 0)
                if max_sheets == -1:
                    self._sheet_quota = -1
                    return self._sheet_quota
                self._sheet_quota = max(self._sheet_quota, max_sheets)

        return self._sheet_quota

    def in_group(self, group_id: str) -> bool:
        return group_id in self.user_groups_names

    def has_quota_monthly_sheets(self) -> bool:
        """
        checks if a user has reached their sheet quota
        """
        if self.sheet_quota == -1: return True

        user_sheets = self.db.query(models.Sheet).filter(models.Sheet.author_id == self.email).count()

        return user_sheets < self.sheet_quota

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

    # def can_manually_trigger(self) -> bool:
    #     """
    #     checks if a user is allowed to manually trigger a sheet
    #     """
    #     for group in self.user_groups:
    #         if not group.permissions: continue
    #         if group.permissions.get("manual_trigger", False):
    #             return True
    #     return False

    def is_sheet_frequency_allowed(self, frequency: str) -> bool:
        """
        checks if a user is allowed to create a sheet with this frequency
        """
        return frequency in self.allowed_frequencies
