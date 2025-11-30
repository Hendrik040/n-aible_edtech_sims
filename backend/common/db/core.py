"""Database engine and session helpers."""

from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.config import get_settings
from common.db.base import Base

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
