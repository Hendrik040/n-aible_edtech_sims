"""FastAPI application entrypoint (auth-only slice)."""

from fastapi import FastAPI

from backend.app.api import router as api_router
from backend.common.db.core import Base, engine

app = FastAPI(title="Develop V2 Backend", version="0.1.0")
app.include_router(api_router)


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.on_event("startup")
def create_schema() -> None:
    Base.metadata.create_all(bind=engine)

