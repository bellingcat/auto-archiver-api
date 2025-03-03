from contextlib import asynccontextmanager, contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

from app.shared.settings import get_settings


@lru_cache
def make_engine(database_url: str):
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        pool_size=15,  # Increase pool size
        max_overflow=20,  # Allow more temporary connections
        pool_recycle=1800,  # Recycle connections every 30 minutes
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(conn, _) -> None:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


def make_session_local(engine: Engine):
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return session_local


@contextmanager
def get_db():
    session = make_session_local(make_engine(get_settings().DATABASE_PATH))()
    try:
        yield session
    finally:
        session.close()


def get_db_dependency():
    # to use with Depends and ensure proper session closing
    with get_db() as db:
        yield db


def wal_checkpoint():
    # WAL checkpointing, make sure the .sqlite file receives the latest changes
    # to be called at startup as it halts writes
    with get_db() as db:
        db.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))


# ASYNC connections
async def make_async_engine(database_url: str) -> AsyncEngine:
    engine = create_async_engine(
        database_url, connect_args={"check_same_thread": False}
    )

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: sync_conn.execute(
                text("PRAGMA journal_mode=WAL;")
            )
        )

    return engine


async def make_async_session_local(engine: AsyncEngine) -> AsyncSession:
    return async_sessionmaker(
        engine, expire_on_commit=False, autoflush=False, autocommit=False
    )


@asynccontextmanager
async def get_db_async():
    engine = await make_async_engine(get_settings().async_database_path)
    async_session = await make_async_session_local(engine)
    async with async_session() as session:
        try:
            yield session
        finally:
            await engine.dispose()
