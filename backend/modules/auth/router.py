"""Auth HTTP endpoints."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from common.db.core import get_db
from modules.auth import models
from modules.auth.dependencies import get_current_user
from modules.auth.repository import UserRepository
from modules.auth.schemas import (
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)
from modules.auth.service import AuthService

router = APIRouter()


def get_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(UserRepository(db))


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(
    payload: UserCreate,
    response: Response,
    service: AuthService = Depends(get_service),
):
    """Register a new user and set authentication cookie."""
    user = service.register(payload, response)
    return user


@router.post("/login", response_model=TokenResponse)
def login(
    payload: UserLogin,
    response: Response,
    service: AuthService = Depends(get_service),
):
    """Login user and set authentication cookie."""
    user = service.login(payload, response)
    return TokenResponse(
        access_token="",  # Empty - token in HttpOnly cookie
        token_type="cookie",
        user=user,
    )


@router.post("/logout")
def logout(
    response: Response,
    service: AuthService = Depends(get_service),
):
    """Logout user by clearing authentication cookie."""
    service.logout(response)
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
def get_current_user_info(
    current_user: models.User = Depends(get_current_user),
):
    """Get current authenticated user information."""
    return current_user

