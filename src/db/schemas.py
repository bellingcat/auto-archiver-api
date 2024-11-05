from pydantic import BaseModel, field_validator
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

    @field_validator('frequency')
    def validate_frequency(cls, v):
        valid_frequencies = {"hourly", "daily"}
        if v not in {"hourly", "daily"}:
            raise ValueError(f"Invalid frequency: {v}. Must be one of {valid_frequencies}.")
        return v


class SheetResponse(SheetAdd):
    author_id: str
    stats: dict | None
    last_archived_at: datetime | None
    created_at: datetime
