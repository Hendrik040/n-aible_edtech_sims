"""
Student module routers
"""
from .student_cohorts import router as student_cohorts_router
from .student_instances import router as student_instances_router

__all__ = ["student_cohorts_router", "student_instances_router"]

