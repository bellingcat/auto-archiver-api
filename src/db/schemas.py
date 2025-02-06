from typing import Annotated
from annotated_types import Len
from pydantic import BaseModel
from datetime import datetime


class Tag(BaseModel):
    id: str
    created_at: datetime

    model_config = {"from_attributes": True}
    __hash__ = object.__hash__


class ArchiveCreate(BaseModel):
    id: str | None = None
    url: str
    result: dict | None = None
    public: bool = True
    author_id: str | None = None
    group_id: str | None = None
    tags: set[Tag] | None = set()
    rearchive: bool = True
    sheet_id: str | None = None
    # urls: list = []


class Archive(ArchiveCreate):
    created_at: datetime
    updated_at: datetime | None
    deleted: bool

    model_config = {"from_attributes": True}


class SubmitSheet(BaseModel):
    sheet_name: str | None = None
    sheet_id: str | None = None
    header: int = 1
    public: bool = False
    author_id: str | None = None
    group_id: str | None = None
    tags: set[str] | None = set()
    columns: dict | None = {}  # TODO: implement


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
    url: Annotated[str, Len(min_length=5)]
    public: bool = True
    group_id: Annotated[str, Len(min_length=1)] | None = None
    tags: set[Tag] | None = set()
