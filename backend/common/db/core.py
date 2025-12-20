"""Database engine and session helpers."""

import logging
import os
from typing import Iterator

from sqlalchemy import create_engine, event, Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import Pool, NullPool

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
    # Check if using Neon's pooled connection (PgBouncer)
    # Pooled connections have "-pooler" in the hostname
    url_lower = settings.database_url.lower()
    has_pooler_hyphen = "-pooler" in settings.database_url
    has_pooler_word = "pooler" in url_lower
    
    is_pooled_connection = has_pooler_hyphen or has_pooler_word
    
    # Debug logging to help diagnose connection type
    debug_msg = (
        f"[DB_CONNECTION_TYPE] Database URL connection type detection:\n"
        f"  URL (masked): {settings.database_url[:50]}...\n"
        f"  Contains '-pooler': {has_pooler_hyphen}\n"
        f"  Contains 'pooler' (case-insensitive): {has_pooler_word}\n"
        f"  Detected as pooled connection: {is_pooled_connection}"
    )
    logger.warning(debug_msg)  # Use warning level so it's visible in production logs
    
    if is_pooled_connection:
        # Use NullPool for pooled connections - let PgBouncer handle pooling
        # This eliminates connection cleanup errors and allows scaling to many replicas
        # Disable reset_on_return since NullPool doesn't reuse connections
        _engine_kwargs.update({
            "poolclass": NullPool,
            "pool_reset_on_return": None,  # Don't rollback - connections are closed immediately
            "connect_args": {
                "connect_timeout": 10,
                "application_name": "n-aible_Backend",
            },
        })
        logger.warning("✓ Using NullPool for Neon pooled connection (PgBouncer) - reset_on_return disabled")
    else:
        # Use small client-side pool for direct connections
        pool_size_env = os.getenv("DB_POOL_SIZE")
        max_overflow_env = os.getenv("DB_MAX_OVERFLOW")
        pool_timeout_env = os.getenv("DB_POOL_TIMEOUT")
        
        pool_size = int(pool_size_env) if pool_size_env else 10
        max_overflow = int(max_overflow_env) if max_overflow_env else 10
        pool_timeout = int(pool_timeout_env) if pool_timeout_env else 10
        
        # Debug logging to show what values are being read
        logger.warning(f"[DB_POOL_CONFIG] Database pool configuration - pool_size={pool_size}, max_overflow={max_overflow}, total_capacity={pool_size + max_overflow}")
        logger.warning(f"[DB_CONNECTION_TYPE] Using QueuePool (direct connection) - pool_size={pool_size}, max_overflow={max_overflow}")

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

# Verify which pool class was actually used (for debugging)
try:
    pool_class_name = type(engine.pool).__name__
    logger.warning(f"[DB_CONNECTION_TYPE] Engine created with pool class: {pool_class_name}")
    if pool_class_name == "NullPool":
        logger.warning("[DB_CONNECTION_TYPE] ✓ CONFIRMED: Using NullPool - PgBouncer pooling active")
    elif pool_class_name == "QueuePool":
        pool_size = getattr(engine.pool, "size", lambda: 0)()
        max_overflow = getattr(engine.pool, "_max_overflow", 0)
        logger.error(f"[DB_CONNECTION_TYPE] ✗ WARNING: Using QueuePool instead of NullPool! pool_size={pool_size}, max_overflow={max_overflow}")
except Exception as e:
    logger.warning(f"[DB_CONNECTION_TYPE] Could not verify pool class: {e}")


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
    # Log at DEBUG level - this is normal, especially with NullPool where each request gets a new connection
    pool_type = type(engine.pool).__name__
    logger.debug(f"Database connection pool: New connection established (pool_type={pool_type})")


@event.listens_for(Pool, "connect")
def handle_pool_connect(dbapi_conn, connection_record):
    """
    Handle new connection creation.
    This is called when a new connection is created for the pool.
    """
    pass


@event.listens_for(Pool, "checkout")
def handle_pool_checkout(dbapi_conn, connection_record, connection_proxy):
    """
    Handle connection checkout with error recovery and monitoring.
    
    If a connection fails during checkout (e.g., closed by server),
    SQLAlchemy will automatically invalidate it and try another connection.
    """
    try:
        pool = connection_record.info.get("pool")
        if pool is None:
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


@event.listens_for(Pool, "checkin")
def handle_pool_checkin(dbapi_conn, connection_record):
    """
    Handle connection return to pool with error recovery.
    
    This is called when a connection is returned to the pool.
    If there's an error during cleanup (like SSL connection closed),
    we catch it and invalidate the connection so it gets discarded.
    """
    # The connection cleanup (rollback) happens in _finalize_fairy
    # If it fails, SQLAlchemy will call invalidate() which we handle above
    pass


@event.listens_for(Pool, "invalidate")
def handle_pool_invalidate(dbapi_conn, connection_record, exception):
    """
    Handle connection invalidation gracefully.
    
    This is called when SQLAlchemy invalidates a connection (e.g., after a cleanup error).
    We log it but don't raise - SQLAlchemy will discard the bad connection and create a new one.
    """
    if exception:
        # Log connection errors but don't crash - these are expected when connections are closed
        # by the server (timeouts, connection limits, network issues)
        error_type = type(exception).__name__
        error_msg = str(exception)
        
        # Only log as warning for operational errors (connection closed, etc.)
        # These are expected in production with connection pooling
        if "SSL connection has been closed" in error_msg or "connection" in error_msg.lower():
            logger.debug(
                f"Connection invalidated (expected): {error_type}: {error_msg}",
                exc_info=False
            )
        else:
            logger.warning(
                f"Connection invalidated: {error_type}: {error_msg}",
                exc_info=False
            )


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


__all__ = ["Base", "engine", "SessionLocal", "get_db"]
