"""Business logic for user registration and authentication."""

from fastapi import HTTPException, status

from common.security.passwords import hash_password, verify_password
from common.security.tokens import create_access_token, decode_token
from modules.auth import models
from modules.auth.repository import UserRepository
from modules.auth.schemas import UserCreate, UserLogin


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
