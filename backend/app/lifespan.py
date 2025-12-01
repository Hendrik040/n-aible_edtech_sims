from contextlib import asynccontextmanager
from fastapi import FastAPI
from common.db.base import Base
from common.db.connection import engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.
    Handles startup and shutdown events.
    """
    # Startup: Initialize database tables
    # Note: In production with migrations, we might not want to auto-create tables here
    Base.metadata.create_all(bind=engine)
    
    yield
    
    # Shutdown: Clean up resources if needed
    # e.g. close DB connections, http clients, etc.
