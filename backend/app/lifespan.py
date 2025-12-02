from contextlib import asynccontextmanager
import logging
from sqlalchemy import text
from fastapi import FastAPI
from common.db.connection import engine

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.
    Handles startup and shutdown events.
    """
    # Startup: Test database connection (non-blocking)
    # Note: We use migrations for schema, so we don't auto-create tables here
    # Don't fail startup if DB is temporarily unavailable - let requests handle it
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection verified successfully")
    except Exception as e:
        logger.warning(f"Database connection check failed during startup (non-critical): {e}")
        # Don't crash the app - it will handle DB errors at request time
        # This allows the server to start even if DB is temporarily unavailable
    
    yield
    
    # Shutdown: Clean up resources if needed
    # e.g. close DB connections, http clients, etc.
    logger.info("Application shutting down")
