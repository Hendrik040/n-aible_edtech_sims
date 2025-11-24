"""Student domain API aggregation."""

from fastapi import APIRouter

from modules.student.routers.cohorts import router as cohorts_router
from modules.student.routers.messages import router as messages_router
from modules.student.routers.notifications import router as notifications_router
from modules.student.routers.simulation_instances import (
    router as simulation_instances_router,
)

router = APIRouter()
router.include_router(cohorts_router)
router.include_router(simulation_instances_router)
router.include_router(messages_router)
router.include_router(notifications_router)

__all__ = ["router"]

