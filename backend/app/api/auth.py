"""
Auth router - Wires the auth module router to the main app
"""
from fastapi import APIRouter
from modules.auth.router import router as auth_router

# Create router that will be included in main app
# The auth_router already has prefix="/auth", so we include it directly
router = auth_router

