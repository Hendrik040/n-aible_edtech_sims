"""Business logic for user registration and authentication."""

from fastapi import HTTPException, Response, status

from common.config import get_settings
from common.security.passwords import hash_password, verify_password
from common.security.tokens import create_access_token
from common.utils.id_generator import generate_unique_user_id
from modules.auth import models
from modules.auth.repository import UserRepository
from modules.auth.schemas import UserCreate, UserLogin


class AuthService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    def register(self, payload: UserCreate, response: Response) -> models.User:
        """Register new user with role-based ID and set authentication cookie."""
        if self.repository.get_by_email(payload.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
        
        # Check username uniqueness if provided
        if payload.username and self.repository.get_by_username(payload.username):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken",
            )
        
        # Generate role-based user ID
        user_id = generate_unique_user_id(self.repository.db, payload.role)
        
        password_hash = hash_password(payload.password)
        user = self.repository.create(
            user_id=user_id,
            email=payload.email,
            password_hash=password_hash,
            full_name=payload.full_name,
            username=payload.username,
            role=payload.role,
        )
        
        # Set HttpOnly cookie
        self._set_auth_cookie(response, user)
        return user

    def login(self, payload: UserLogin, response: Response) -> models.User:
        """Login user and set authentication cookie."""
        user = self.repository.get_by_email(payload.email)
        if not user or user.password_hash is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User account is inactive",
            )
        
        # Set HttpOnly cookie
        self._set_auth_cookie(response, user)
        return user

    def logout(self, response: Response):
        """Clear authentication cookie."""
        settings = get_settings()
        response.delete_cookie(
            key="access_token",
            httponly=True,
            secure=settings.is_production,
            samesite="lax",
            path="/",
        )

    def _set_auth_cookie(self, response: Response, user: models.User):
        """Set secure HttpOnly cookie with authentication token."""
        settings = get_settings()
        token = create_access_token(subject=str(user.id))
        
        response.set_cookie(
            key="access_token",
            value=token,
            httponly=True,
            secure=settings.is_production,
            samesite="lax",
            path="/",
            max_age=settings.access_token_exp_minutes * 60,
        )


__all__ = ["AuthService"]
