"""
Student module router
Includes all student-facing endpoints
"""
from fastapi import APIRouter
from .routers.student_cohorts import router as student_cohorts_router

# Main router - no prefix here since sub-routers define their own prefixes
router = APIRouter(tags=["Student"])

# Include sub-routers
router.include_router(student_cohorts_router)
