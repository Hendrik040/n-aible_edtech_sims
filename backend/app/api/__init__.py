"""Top-level API router for the backend."""

from fastapi import APIRouter

from modules.auth.router import router as auth_router

router = APIRouter()
router.include_router(auth_router, prefix="/api/auth", tags=["Auth"])

__all__ = ["router"]
