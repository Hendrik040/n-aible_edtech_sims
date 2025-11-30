"""Authentication dependencies for the auth module."""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from common.db.core import get_db
from common.security.tokens import decode_token
from modules.auth import models
from modules.auth.repository import UserRepository


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> models.User:
    """Get current authenticated user from HttpOnly cookie."""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub"))
    except (ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    repository = UserRepository(db)
    user = repository.get_by_id(user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


def require_role(*allowed_roles: str):
    """Dependency factory for role-based access control."""
    def role_checker(
        current_user: models.User = Depends(get_current_user),
    ) -> models.User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user
    return role_checker


# Convenience dependencies
require_admin = require_role("admin")
require_student = require_role("student", "admin")
require_professor = require_role("professor", "admin")


__all__ = [
    "get_current_user",
    "require_role",
    "require_admin",
    "require_student",
    "require_professor",
]

