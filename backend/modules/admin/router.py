"""
Admin module router.
Includes all admin-facing endpoints.
"""
from fastapi import APIRouter
from .traces_router import router as traces_router
from .dashboard_router import router as dashboard_router
from .ralph_pipeline_router import router as ralph_pipeline_router

router = APIRouter(tags=["Admin"])
router.include_router(traces_router)
router.include_router(dashboard_router)
router.include_router(ralph_pipeline_router)
