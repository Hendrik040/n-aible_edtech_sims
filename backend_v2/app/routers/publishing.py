"""Publishing router wiring."""
from fastapi import APIRouter
from modules.publishing.router import router as publishing_router

router = APIRouter()

# Include the publishing module router
# The module router already has its own prefix (/api/publishing/simulations)
router.include_router(publishing_router)
