"""
Database engine, sessions, and helpers shared across modules.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.config import get_settings
from common.db.base import Base

settings = get_settings()


def _create_engine():
    if settings.database_url.startswith("postgresql"):
        return create_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=70,
            max_overflow=80,
            pool_timeout=60,
            connect_args={
                "connect_timeout": 30,
                "application_name": "AOM_2025_Backend",
            },
        )

    if settings.database_url.startswith("sqlite"):
        return create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},
        )

    raise ValueError(
        "Unsupported database URL format. Only PostgreSQL and SQLite are supported."
    )


engine = _create_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Iterator:
    """FastAPI dependency that yields a SQLAlchemy session."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session():
    """Context-manager-friendly session usage outside FastAPI DI."""

    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


__all__ = ["Base", "engine", "SessionLocal", "get_db", "get_db_session"]

