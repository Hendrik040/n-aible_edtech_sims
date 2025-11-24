"""Professor domain API aggregation."""

from fastapi import APIRouter

from modules.professor.routers.cohorts import router as cohorts_router
from modules.professor.routers.grading import router as grading_router
from modules.professor.routers.grading_materials import router as grading_materials_router
from modules.professor.routers.invitations import (
    public_router as invite_links_router,
    router as invitations_router,
)
from modules.professor.routers.messages import router as messages_router
from modules.professor.routers.notifications import router as notifications_router

router = APIRouter()
router.include_router(cohorts_router)
router.include_router(invitations_router)
router.include_router(grading_router)
router.include_router(grading_materials_router)
router.include_router(messages_router)
router.include_router(notifications_router)
router.include_router(invite_links_router, tags=["Invite Links"])

__all__ = ["router"]

