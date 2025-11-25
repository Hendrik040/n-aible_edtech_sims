"""Auth HTTP endpoints."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from common.db.core import get_db
from modules.auth.repository import UserRepository
from modules.auth.schemas import (
    TokenResponse,
    UserCreate,
    UserLogin,
    UserRead,
)
from modules.auth.service import AuthService

router = APIRouter()


def get_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(UserRepository(db))


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register_user(payload: UserCreate, service: AuthService = Depends(get_service)):
    user = service.register(payload)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, service: AuthService = Depends(get_service)):
    token = service.login(payload)
    return TokenResponse(access_token=token)

