"""Pydantic schemas for authentication endpoints."""

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class UserRead(BaseModel):
    id: int
    email: EmailStr
    full_name: str | None = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


__all__ = ["UserRead", "UserCreate", "UserLogin", "TokenResponse"]

