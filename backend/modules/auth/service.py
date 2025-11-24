"""Business logic for user registration and authentication."""

from fastapi import HTTPException, status

from backend.common.security.passwords import hash_password, verify_password
from backend.common.security.tokens import create_access_token, decode_token
from backend.modules.auth import models
from backend.modules.auth.repository import UserRepository
from backend.modules.auth.schemas import UserCreate, UserLogin


class AuthService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    def register(self, payload: UserCreate):
        if self.repository.get_by_email(payload.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
        password_hash = hash_password(payload.password)
        return self.repository.create(
            email=payload.email, password_hash=password_hash, full_name=payload.full_name
        )

    def login(self, payload: UserLogin) -> str:
        user = self.repository.get_by_email(payload.email)
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )
        return create_access_token(subject=str(user.id))

    def validate_access_token(self, token: str):
        try:
            data = decode_token(token)
        except ValueError:
            return None
        user_id = data.get("sub")
        if not user_id:
            return None
        return self.repository.db.get(models.User, int(user_id))


__all__ = ["AuthService"]
"""Business logic for authentication."""

from datetime import datetime, timedelta
import secrets

from sqlalchemy.orm import Session

from backend.common.config import get_settings
from backend.common.security.passwords import hash_password, verify_password
from backend.modules.auth import repository
from backend.modules.auth.schemas.dto import LoginRequest, RegisterRequest
from backend.modules.auth.schemas.models import User

settings = get_settings()


def register_user(db: Session, payload: RegisterRequest) -> User:
    existing = repository.get_user_by_email(db, payload.email)
    if existing:
        raise ValueError("Email already registered")

    hashed = hash_password(payload.password)
    return repository.create_user(
        db,
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hashed,
    )


def authenticate_user(db: Session, payload: LoginRequest) -> User:
    user = repository.get_user_by_email(db, payload.email)
    if not user or not verify_password(payload.password, user.hashed_password):
        raise ValueError("Invalid credentials")
    return user


def create_access_token(user: User) -> str:
    expiry = datetime.utcnow() + timedelta(minutes=settings.access_token_exp_minutes)
    payload = f"{user.id}:{int(expiry.timestamp())}"
    return secrets.token_urlsafe(16) + payload
