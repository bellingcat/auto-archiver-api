from typing import Annotated
from annotated_types import Len
from pydantic import BaseModel
from datetime import datetime


class SubmitSheet(BaseModel):
    sheet_id: str | None
    author_id: str | None = None
    group_id: str | None
    tags: set[str] | None = set()
    columns: dict | None = {}  # TODO: implement/remove


class SubmitManual(BaseModel):
    result: str  # should be a Metadata.to_json()
    public: bool = False
    author_id: str | None = None
    group_id: str | None = None
    tags: set[str] | None = set()

# API REQUESTS BELOW
# TODO: replace existing schemas with these


class ArchiveUrl(BaseModel):
    url: str
    public: bool = False
    author_id: str | None
    group_id: str | None
    tags: set[str] | None = set()

# API RESPONSES BELOW


class ArchiveResult(BaseModel):
    id: str
    url: str
    result: dict
    created_at: datetime


class Task(BaseModel):
    id: str


class TaskResult(Task):
    status: str
    result: str


class TaskDelete(Task):
    deleted: bool


class ActiveUser(BaseModel):    
    active: bool


class SheetAdd(BaseModel):
    id: str
    name: str
    group_id: str
    frequency: str


class SheetResponse(SheetAdd):
    author_id: str
    created_at: datetime
    last_url_archived_at: datetime | None


class ArchiveTrigger(BaseModel):
    author_id: str | None = None
    url: Annotated[str, Len(min_length=5)]
    public: bool = False
    group_id: Annotated[str, Len(min_length=1)] = "default"
    tags: set[str] | None = None

class ArchiveCreate(ArchiveTrigger):
    id: str | None = None
    result: dict | None = None
    sheet_id: str | None = None
    urls: list | None = None

class Archive(ArchiveCreate):
    created_at: datetime
    updated_at: datetime | None
    deleted: bool

    model_config = {"from_attributes": True}


class Usage(BaseModel):
    monthly_urls: int = 0
    monthly_mbs: int = 0
    total_sheets: int = 0

class UsageResponse(Usage):
    groups: dict[str, Usage]

class CelerySheetTask(BaseModel):
    success: bool
    sheet_id: str
    time: datetime
    stats: dict