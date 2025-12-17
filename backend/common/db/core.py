"""Database engine and session helpers."""

import logging
from typing import Iterator

from sqlalchemy import create_engine, event, Engine
from sqlalchemy.orm import sessionmaker

from common.config import get_settings
from common.db.base import Base

settings = get_settings()
logger = logging.getLogger(__name__)

# Build engine kwargs based on database type
# Disable echo to reduce SQL logging verbosity (can be enabled via SQLALCHEMY_ECHO env var if needed)
_engine_kwargs = {
    "future": True,
    "echo": False,  # Disabled by default - set SQLALCHEMY_ECHO=true in env if you need SQL query logging
    "pool_pre_ping": True,  # Verify connections before use
}

# PostgreSQL-specific settings for connection pooling
if settings.database_url.startswith("postgresql"):
    # Demo-ready configuration: Proven settings from production use
    # These settings handle burst traffic patterns (50-60 concurrent users)
    # pool_size: base connections maintained
    # max_overflow: additional connections beyond pool_size
    # Total max connections = pool_size + max_overflow = 70 + 80 = 150
    _engine_kwargs.update({
        "pool_size": 70,         # Number of connections to maintain (increased for demo)
        "max_overflow": 80,      # Maximum connections beyond pool_size
        "pool_recycle": 300,     # Recycle connections every 5 minutes
        "pool_timeout": 30,      # Timeout for getting connection from pool
        "connect_args": {
            "connect_timeout": 10,
            "application_name": "n-aible_Backend"
        }
    })
else:
    # SQLite requires check_same_thread=False
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url, **_engine_kwargs)


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
        checked_out = pool.checkedout()
        overflow = pool.overflow()
        total_in_use = checked_out + overflow

        # Log current pool stats at debug level
        logger.debug(
            f"Pool stats: checked_out={checked_out}, "
            f"overflow={overflow}, total_in_use={total_in_use}/150"
        )

        # Alert if getting close to limit (80% capacity)
        if total_in_use > 120:
            logger.warning(
                f"⚠️ Database connection pool usage HIGH: "
                f"{total_in_use}/150 connections in use "
                f"(checked_out={checked_out}, overflow={overflow})"
            )
    except Exception as e:
        # Don't let monitoring break the app
        logger.debug(f"Could not log pool stats: {e}")
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


__all__ = ["Base", "engine", "SessionLocal", "get_db"]
