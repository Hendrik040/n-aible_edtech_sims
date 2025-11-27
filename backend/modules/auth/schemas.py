"""Pydantic schemas for authentication endpoints."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str | None = None
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str | None = None
    username: str | None = None
    role: str = "student"  # student, professor, admin


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Complete user response with all fields."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str | None = None
    email: EmailStr
    full_name: str | None = None
    username: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    """Token response for cookie-based authentication."""
    access_token: str = ""  # Empty for cookie-based auth
    token_type: str = "cookie"
    user: UserResponse


__all__ = ["UserRead", "UserCreate", "UserLogin", "UserResponse", "TokenResponse"]

