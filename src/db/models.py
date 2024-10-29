from sqlalchemy import Column, String, JSON, DateTime, Boolean, Table, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, declarative_base
import uuid


Base = declarative_base()

def generate_uuid():
    return str(uuid.uuid4())

# many to many association tables
association_table_archive_tags = Table(
    "mtm_archives_tags",
    Base.metadata,
    Column("archive_id", ForeignKey("archives.id")),
    Column("tag_id", ForeignKey("tags.id")),
)
association_table_user_groups = Table(
    "mtm_users_groups",
    Base.metadata,
    Column("user_id", ForeignKey("users.email")),
    Column("group_id", ForeignKey("groups.id")),
)

# data model tables
class Archive(Base):
    __tablename__ = "archives"

    id = Column(String, primary_key=True, index=True)
    url = Column(String, index=True)
    result = Column(JSON, default=None)
    public = Column(Boolean, default=True) # if public=false, access to group and author
    deleted = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    group_id = Column(String, ForeignKey("groups.id"), default=None)
    author_id = Column(String, ForeignKey("users.email"))

    tags = relationship("Tag", back_populates="archives", secondary=association_table_archive_tags)
    group = relationship("Group", back_populates="archives")
    author = relationship("User", back_populates="archives")
    urls = relationship("ArchiveUrl", back_populates="archive")

class ArchiveUrl(Base):
    __tablename__ = "archive_urls"

    url = Column(String, primary_key=True, index=True)
    archive_id = Column(String, ForeignKey("archives.id"), primary_key=True)
    key = Column(String, default=None)

    archive = relationship("Archive", back_populates="urls")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(String, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    archives = relationship("Archive", back_populates="tags", secondary=association_table_archive_tags)

class User(Base):
    __tablename__ = "users"

    email = Column(String, primary_key=True, index=True)
    is_active = Column(Boolean, default=False)

    archives = relationship("Archive", back_populates="author")
    groups = relationship("Group", back_populates="users", secondary=association_table_user_groups)

class Group(Base):
    __tablename__ = "groups"

    id = Column(String, primary_key=True, index=True)

    archives = relationship("Archive", back_populates="group")
    users = relationship("User", back_populates="groups", secondary=association_table_user_groups)