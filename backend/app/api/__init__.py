"""
Top-level API router composition.
"""

from fastapi import APIRouter

from . import (
    auth,
    notifications,
    pdf_processing,
    professor,
    publishing,
    simulation,
    student,
)

router = APIRouter()
router.include_router(auth.router)
router.include_router(pdf_processing.router)
router.include_router(simulation.router)
router.include_router(student.router)
router.include_router(professor.router)
router.include_router(publishing.router)
router.include_router(notifications.router)

__all__ = ["router"]

