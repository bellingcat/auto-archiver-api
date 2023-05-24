from pydantic import BaseModel
from datetime import datetime


class ArchiveCreate(BaseModel):
    id: str | None = None
    url: str
    result: dict | None = None
    public: bool = True
    author_id: str | None = None
    group_id: str | None = None
    tags: set = set()
    # urls: list = []


class Archive(ArchiveCreate):
    created_at: datetime
    updated_at: datetime | None
    deleted: bool

    class Config:
        orm_mode = True


class SubmitSheet(BaseModel):
    sheet_name: str | None = None
    sheet_id: str | None = None
    header: int = 1
    public: bool = False
    author_id: str | None = None
    group_id: str | None = None
    tags: set | None = set()
    columns: dict | None = {} # TODO: implement

class SubmitManual(BaseModel):
    result: str # should be a Metadata.to_json()
    public: bool = False
    author_id: str | None = None
    group_id: str | None = None
    tags: set | None = set()
