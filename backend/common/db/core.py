"""Database engine and session helpers."""

from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.common.config import get_settings
from backend.common.db.base import Base

settings = get_settings()
engine = create_engine(settings.database_url, future=True, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator:
    """FastAPI dependency that yields a database session."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


__all__ = ["Base", "engine", "SessionLocal", "get_db"]
"""Database engine and session helpers."""

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.common.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Iterator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

__all__ = ["engine", "SessionLocal", "get_db", "get_db_session"]
