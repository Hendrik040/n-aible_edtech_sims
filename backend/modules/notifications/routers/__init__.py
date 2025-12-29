"""Notification routers package."""
from .professor_notifications import router as professor_notifications_router
from .student_notifications import router as student_notifications_router

__all__ = [
    "professor_notifications_router",
    "student_notifications_router",
]

