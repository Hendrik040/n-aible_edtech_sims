"""
Notifications module router
Includes all notification-related endpoints for professors and students
"""
from fastapi import APIRouter
from .routers.professor_notifications import router as professor_notifications_router
from .routers.student_notifications import router as student_notifications_router

# Main router - no prefix here since sub-routers define their own prefixes
router = APIRouter(tags=["Notifications"])

# Include sub-routers
router.include_router(professor_notifications_router)
router.include_router(student_notifications_router)
