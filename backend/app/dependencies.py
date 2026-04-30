"""Reusable FastAPI dependencies."""

from typing import Optional, Callable
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, OAuth2PasswordBearer
from sqlalchemy.orm import Session

from common.db.core import get_db
from common.db.models import User
from modules.auth.service import auth_service

# OAuth2 scheme for Swagger UI support
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
oauth2_scheme_optional = HTTPBearer(auto_error=False)

# Declarative permission map — single source of truth for what each role can do.
# Downstream guards use named permissions rather than raw role strings.
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin":     frozenset({"manage_users", "manage_cohorts", "grade", "simulate", "publish"}),
    "professor": frozenset({"manage_cohorts", "grade", "simulate", "publish"}),
    "student":   frozenset({"simulate"}),
}

async def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """Authenticate via HttpOnly cookie and attach resolved permissions to the user object."""

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )

    token = auth_service.extract_token_from_request(request)
    if token is None:
        raise credentials_exception

    payload = auth_service.verify_token(token)
    if payload is None:
        raise credentials_exception

    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )

    # Attach the resolved permission set for this request.
    # Downstream dependencies check named permissions, never raw role strings.
    user.permissions = ROLE_PERMISSIONS.get(user.role, frozenset())

    return user


async def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Return the authenticated user if available, otherwise None."""
    try:
        return await get_current_user(request, db)
    except HTTPException:
        return None


def require_permission(permission: str) -> Callable:
    """Dependency factory: require a specific named permission."""
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if permission not in getattr(current_user, "permissions", frozenset()):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: '{permission}'",
            )
        return current_user
    return _check


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require admin role (holds all permissions)."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user


def require_professor(current_user: User = Depends(get_current_user)) -> User:
    """Require grade permission (professor or admin)."""
    if "grade" not in getattr(current_user, "permissions", frozenset()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions. Professor role required.",
        )
    return current_user


def require_student(current_user: User = Depends(get_current_user)) -> User:
    """Require simulate permission (any authenticated role)."""
    if "simulate" not in getattr(current_user, "permissions", frozenset()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions. Student role required.",
        )
    return current_user
