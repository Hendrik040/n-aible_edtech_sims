"""
Professor module router
Includes all professor-facing endpoints
"""
from fastapi import APIRouter
from .routers.professor_cohorts import router as professor_cohorts_router
from .routers.professor_grading import router as professor_grading_router
from .routers.professor_grade_export import router as professor_grade_export_router

# Main router - no prefix here since sub-routers define their own prefixes
router = APIRouter(tags=["Professor"])

# Include sub-routers
router.include_router(professor_cohorts_router)
router.include_router(professor_grading_router)
router.include_router(professor_grade_export_router)
