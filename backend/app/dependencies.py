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

async def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """Get the current authenticated user from HttpOnly cookie only"""
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    
    # Extract token from HttpOnly cookie using the service
    token = auth_service.extract_token_from_request(request)
    if token is None:
        raise credentials_exception
    
    # Validate token using the service
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
    
    # Ideally this should use the repository via the service
    # For now we query directly to match existing patterns until full refactor
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    return user

async def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Get the current authenticated user if available, otherwise return None"""
    try:
        return await get_current_user(request, db)
    except HTTPException:
        return None

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require admin role for access"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user


def require_professor(current_user: User = Depends(get_current_user)) -> User:
    """Require professor role for access"""
    if current_user.role not in ['professor', 'admin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Professor or admin role required."
        )
    return current_user


def require_student(current_user: User = Depends(get_current_user)) -> User:
    """Require student role for access"""
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions. Student role required."
        )
    return current_user


def require_student_or_professor(current_user: User = Depends(get_current_user)) -> User:
    """Require student or professor role for access (limited mixed-role endpoints)"""
    if current_user.role not in ['student', 'professor', 'admin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Student, professor, or admin role required."
        )
    return current_user