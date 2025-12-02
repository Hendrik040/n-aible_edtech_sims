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
    # Startup: Test database connection
    # Note: We use migrations for schema, so we don't auto-create tables here
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection verified successfully")
    except Exception as e:
        logger.error(f"Database connection failed during startup: {e}", exc_info=True)
        # Log the database URL (masked for security)
        from common.config import get_settings
        settings = get_settings()
        db_url = settings.database_url
        if len(db_url) > 20:
            masked_url = db_url[:10] + "..." + db_url[-10:]
        else:
            masked_url = "***"
        logger.error(f"Database URL (masked): {masked_url}")
        # Don't crash - let the app start and handle DB errors at request time
        # But log it prominently so we can see it in Railway logs
    
    yield
    
    # Shutdown: Clean up resources if needed
    # e.g. close DB connections, http clients, etc.
    logger.info("Application shutting down")
