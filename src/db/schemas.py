from pydantic import BaseModel
from datetime import datetime

class TaskCreate(BaseModel):
    id: str
    url: str
    author: str
    result: dict


class Task(TaskCreate):
    created_at: datetime

    class Config:
        orm_mode = True