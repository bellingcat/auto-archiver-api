from pydantic import BaseModel
from datetime import datetime

class ArchiveCreate(BaseModel):
    id: str | None = None
    url: str
    result: dict | None = None
    public: bool = True
    author_id: str | None = None
    group_id: str | None = None
    tags: list = []
    # urls: list = []



class Archive(ArchiveCreate):
    created_at: datetime
    updated_at: datetime | None
    deleted: bool

    class Config:
        orm_mode = True


# class TagCreate(BaseModel):
#     id: str
    
# class Tag(TagCreate):
#     created_at: datetime
#     # class Config:
#     #     orm_mode = True