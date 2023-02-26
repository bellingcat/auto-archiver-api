from sqlalchemy import Column, String, JSON, DateTime
from sqlalchemy.sql import func
from .database import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, index=True)
    url = Column(String, index=True)
    author = Column(String, index=True)
    result = Column(JSON, default=None)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # items = relationship("Item", back_populates="owner")
