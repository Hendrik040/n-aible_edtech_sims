from fastapi import APIRouter
from modules.auth.router import router as auth_router

router = APIRouter()

# Include the auth module router with the API prefix
# The module router handles specific sub-paths (e.g. /users)
router.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])

