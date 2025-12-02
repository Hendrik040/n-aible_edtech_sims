"""Top-level API router for the backend."""

from fastapi import APIRouter

from modules.auth.router import router as auth_router
from modules.pdf_processing.router import router as pdf_router

router = APIRouter()
router.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
router.include_router(pdf_router, tags=["PDF Processing"])

__all__ = ["router"]
