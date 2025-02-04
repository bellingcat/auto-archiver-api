import yaml
from loguru import logger
from pydantic import BaseModel, field_validator, Field, model_validator
from typing import Dict, List, Set
from typing_extensions import Self


class UserGroups:
    def __init__(self, filename):
        user_groups = self.read_yaml(filename)
        self.validate_and_load(user_groups)

    def read_yaml(self, user_groups_filename):
        # read yaml safely
        with open(user_groups_filename) as inf:
            try:
                return yaml.safe_load(inf)
            except yaml.YAMLError as e:
                logger.error(f"could not open user groups filename {user_groups_filename}: {e}")
                raise e

    def validate_and_load(self, user_groups):
        try:
            configs = UserGroupModel(**user_groups)
            self.users = configs.users
            self.domains = configs.domains
            self.groups = configs.groups
        except Exception as e:
            logger.error(f"Validation error: {e}")
            raise e


class GroupPermissions(BaseModel):
    read: Set[str] | bool = Field(default_factory=list)
    read_public: bool = False
    archive_url: bool = False
    archive_sheet: bool = False
    manually_trigger_sheet: bool = False
    sheet_frequency: Set[str] = Field(default_factory=list)
    max_sheets: int = 0
    max_archive_lifespan_months: int = 12
    max_monthly_urls: int = 0
    max_monthly_mbs: int = 0
    priority: str = "low"

    @field_validator('max_sheets', 'max_archive_lifespan_months', 'max_monthly_urls', 'max_monthly_mbs', mode='before')
    def validate_max_values(cls, v):
        if v < -1:
            raise ValueError("max_* values should be positive integers or -1 (for no limit).")
        return v

    @field_validator('sheet_frequency', mode='before')
    def validate_sheet_frequency(cls, v):
        if not v: return []
        allowed = ["daily", "hourly"]
        for k in v:
            if k not in allowed:
                raise ValueError(f"Invalid sheet frequency: '{k}', expected one of {allowed}")
        return v

    @field_validator('priority', mode='before')
    def validate_priority(cls, v):
        v = v.lower()
        if v not in ["low", "high"]:
            raise ValueError("priority must be either 'low' or 'high'.")
        return v


class GroupModel(BaseModel):
    description: str
    orchestrator: str
    orchestrator_sheet: str
    permissions: GroupPermissions


class UserGroupModel(BaseModel):
    users: Dict[str, List[str]] = Field(default_factory=dict)
    domains: Dict[str, List[str]] = Field(default_factory=dict)
    groups: Dict[str, GroupModel] = Field(default_factory=dict)

    @field_validator('users', mode='before')
    @classmethod
    def validate_emails(cls, v):
        for email in v.keys():
            if '@' not in email:
                raise ValueError(f"Invalid user, it should be an address: {email}")
            if not v[email]:
                raise ValueError(f"User {email} has no explicitly listed groups, only include them here if they should be in a group.")
        # all users belong to the default group
        return {k.lower().strip(): list(set(["default"] + [g.lower().strip() for g in v])) for k, v in v.items()}

    @field_validator('domains', mode='before')
    @classmethod
    def validate_domains(cls, v):
        for domain, members in v.items():
            if '.' not in domain:
                raise ValueError(f"Invalid domain, it should contain a dot: {domain}")
            if not members:
                raise ValueError(f"Domain {domain} should have at least one member.")
        return {k.lower().strip(): list(set([g.lower().strip() for g in v])) for k, v in v.items()}

    @field_validator('groups', mode='before')
    @classmethod
    def validate_groups(cls, v):
        if "default" not in v.keys():
            raise ValueError("Please include a 'default' group.")
        if "all" in v.keys():
            raise ValueError("'all' is a reserved group name.")
        for group in v.keys():
            if not group == group.lower():
                raise ValueError(f"Group names should be lowercase: {group}")
        return v

    @model_validator(mode='after')
    def check_groups_consistency(self) -> Self:
        groups_in_domains = set([g for domain in self.domains for g in self.domains[domain]])
        groups_in_users = set([g for user in self.users for g in self.users[user]])
        configured_groups = set(self.groups.keys())

        # groups mentioned in domains and users should be defined, but this is not a ValueError since historical DB data may require it
        if groups_in_domains - configured_groups:
            logger.warning(f"These groups are associated to DOMAINS but not defined in the GROUPS section, the domains settings may not work as expected: {groups_in_domains - configured_groups}")
        if groups_in_users - configured_groups:
            logger.warning(f"These groups are associated to USERS but not defined in the GROUPS section, the users settings may not work as expected: {groups_in_users - configured_groups}")

        return self
