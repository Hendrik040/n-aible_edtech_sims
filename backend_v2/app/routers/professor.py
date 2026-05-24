"""Professor router wiring."""
from fastapi import APIRouter

router = APIRouter(prefix="/api/professor", tags=["Professor"])

# Note: Professor module endpoints will be added here when implemented
# Removing placeholders so real 404 errors show up for missing implementations
