"""Database engine and session helpers."""

import logging
import os
from typing import Iterator

from sqlalchemy import create_engine, event, Engine
from sqlalchemy.orm import sessionmaker

from common.config import get_settings
from common.db.base import Base

settings = get_settings()
logger = logging.getLogger(__name__)

# Read SQLALCHEMY_ECHO env var to enable SQL query logging
# Treat "1", "true", "yes", "on" (case-insensitive) as True, anything else as False
_sqlalchemy_echo_env = os.getenv("SQLALCHEMY_ECHO", "").lower()
sqlalchemy_echo = _sqlalchemy_echo_env in ("1", "true", "yes", "on")

# Build engine kwargs based on database type
# Disable echo to reduce SQL logging verbosity (can be enabled via SQLALCHEMY_ECHO env var if needed)
_engine_kwargs = {
    "future": True,
    "echo": sqlalchemy_echo,  # Controlled by SQLALCHEMY_ECHO env var (default: False)
    "pool_pre_ping": True,  # Verify connections before use
}

# PostgreSQL-specific settings for connection pooling
if settings.database_url.startswith("postgresql"):
    # Neon + PgBouncer guidance:
    # - Prefer small client-side pools (5–10 connections)
    # - Or NullPool when using a pooled connection string
    #
    # To avoid exhausting Neon connection limits, we default to a conservative pool.
    pool_size = int(os.getenv("DB_POOL_SIZE", "10"))
    max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "10"))

    _engine_kwargs.update(
        {
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_recycle": 300,  # Recycle connections every 5 minutes
            "pool_timeout": pool_timeout,
            "connect_args": {
                "connect_timeout": 10,
                "application_name": "n-aible_Backend",
            },
        }
    )
else:
    # SQLite requires check_same_thread=False
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **_engine_kwargs)


def _get_pool_capacity() -> int | None:
    """Best-effort calculation of configured pool capacity for logging."""
    try:
        pool = engine.pool
        # For QueuePool, size() and _max_overflow are available
        size = getattr(pool, "size", lambda: 0)()
        max_overflow = getattr(pool, "_max_overflow", 0)
        total_capacity = size + max_overflow
        return total_capacity or None
    except Exception:
        return None


# Connection pool monitoring for production/demo environments
@event.listens_for(Engine, "connect")
def log_connect(dbapi_conn, connection_record):
    """Log when new database connections are established."""
    logger.info("Database connection pool: New connection established")


@event.listens_for(Engine, "checkout")
def log_checkout(dbapi_conn, connection_record, connection_proxy):
    """Monitor pool usage and warn when approaching capacity."""
    try:
        pool = engine.pool
        # Only QueuePool-like pools support these methods
        checked_out = getattr(pool, "checkedout", lambda: 0)()
        overflow = getattr(pool, "overflow", lambda: 0)()
        total_in_use = checked_out + overflow

        total_capacity = _get_pool_capacity()

        # Log current pool stats at debug level
        if total_capacity:
            logger.debug(
                "Pool stats: checked_out=%s, overflow=%s, total_in_use=%s/%s",
                checked_out,
                overflow,
                total_in_use,
                total_capacity,
            )

            # Alert if getting close to limit (80% capacity)
            high_water_mark = int(total_capacity * 0.8)
            if total_in_use >= high_water_mark:
                logger.warning(
                    "Database connection pool usage HIGH: %s/%s connections in use "
                    "(checked_out=%s, overflow=%s)",
                    total_in_use,
                    total_capacity,
                    checked_out,
                    overflow,
                )
        else:
            # Fallback logging when capacity cannot be determined (e.g., NullPool)
            logger.debug(
                "Pool stats: checked_out=%s, overflow=%s, total_in_use=%s",
                checked_out,
                overflow,
                total_in_use,
            )
    except Exception as e:
        # Don't let monitoring break the app
        logger.debug("Could not log pool stats: %s", e)


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


__all__ = ["Base", "engine", "SessionLocal", "get_db"]
