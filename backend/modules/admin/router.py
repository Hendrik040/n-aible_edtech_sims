"""
Admin module router.
Includes all admin-facing endpoints.
"""
from fastapi import APIRouter
from .traces_router import router as traces_router

router = APIRouter(tags=["Admin"])
router.include_router(traces_router)
