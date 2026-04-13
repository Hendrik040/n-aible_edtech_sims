"""
Professor module routers
"""
from .professor_cohorts import router as professor_cohorts_router
from .professor_grading import router as professor_grading_router

__all__ = ["professor_cohorts_router", "professor_grading_router"]

