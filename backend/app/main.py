"""FastAPI application entrypoint (auth-only slice)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router as api_router
from common.db.core import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    # Startup
    Base.metadata.create_all(bind=engine)
    yield
    # Shutdown (if needed in the future)


app = FastAPI(title="Develop V2 Backend", version="0.1.0", lifespan=lifespan)
app.include_router(api_router)


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}

