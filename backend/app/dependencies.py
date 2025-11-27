"""Reusable FastAPI dependencies."""

from fastapi import Depends
from sqlalchemy.orm import Session

from common.db.core import get_db
from modules.auth.dependencies import (
    get_current_user,
    require_admin,
    require_professor,
    require_student,
)
from modules.auth.repository import UserRepository
from modules.auth.service import AuthService


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    """Get authentication service instance."""
    return AuthService(UserRepository(db))


# Re-export auth dependencies for convenience
__all__ = [
    "get_auth_service",
    "get_current_user",
    "require_admin",
    "require_student",
    "require_professor",
]

