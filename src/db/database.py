from functools import lru_cache
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import sessionmaker
from shared.settings import get_settings
from contextlib import contextmanager


@lru_cache
def make_engine(database_url: str):
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

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
    try: yield session
    finally: session.close()


def get_db_dependency():
    # to use with Depends and ensure proper session closing
    with get_db() as db:
        yield db
