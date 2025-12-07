"""Database engine and session helpers."""

from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.config import get_settings
from common.db.base import Base

settings = get_settings()

# Build engine kwargs based on database type
_engine_kwargs = {
    "future": True,
    "echo": settings.environment == "development",
    "pool_pre_ping": True,  # Verify connections before use
}

# PostgreSQL-specific settings for connection pooling
if settings.database_url.startswith("postgresql"):
    _engine_kwargs.update({
        "pool_size": 5,
        "max_overflow": 10,
        "pool_recycle": 300,  # Recycle connections after 5 minutes
    })
else:
    # SQLite requires check_same_thread=False
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


__all__ = ["Base", "engine", "SessionLocal", "get_db"]
