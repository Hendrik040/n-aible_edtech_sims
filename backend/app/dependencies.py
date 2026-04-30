"""Reusable FastAPI dependencies."""

from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, OAuth2PasswordBearer
from sqlalchemy.orm import Session

from common.db.core import get_db
from common.db.models import User
from modules.auth.service import auth_service

# OAuth2 scheme for Swagger UI support
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
oauth2_scheme_optional = HTTPBearer(auto_error=False)

# Scope claim → roles that are valid for that scope.
# Tokens are issued with a scope; the scope must match the user's DB role.
_SCOPE_ROLES: dict[str, set[str]] = {
    "admin":     {"admin"},
    "professor": {"admin", "professor"},
    "student":   {"admin", "professor", "student"},
}

async def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """Authenticate via HttpOnly cookie; rejects tokens missing a valid scope claim."""

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

    # Tokens without a recognised scope claim are rejected outright.
    # Scope is stamped at login time and must match the user's current role.
    token_scope = payload.get("scope")
    if token_scope not in _SCOPE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing or has an invalid scope claim",
        )

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

    # Guard against role changes that haven't caused a re-login yet.
    if user.role not in _SCOPE_ROLES[token_scope]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token scope does not match current user role — please log in again",
        )

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


def require_role(*roles: str):
    """Dependency factory: accept any of the given roles."""
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access requires one of: {', '.join(roles)}",
            )
        return current_user
    return _check


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require admin role; token scope must be 'admin'."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user


def require_professor(current_user: User = Depends(get_current_user)) -> User:
    """Require professor or admin role; token scope must cover 'professor'."""
    if current_user.role not in ("professor", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions. Professor role required.",
        )
    return current_user


def require_student(current_user: User = Depends(get_current_user)) -> User:
    """Require student role; token scope must be 'student'."""
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions. Student role required.",
        )
    return current_user
