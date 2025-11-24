"""
FastAPI dependencies for authentication and authorization
"""
import logging
import os
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.orm import Session
from database.connection import get_db
from database.models import User
from modules.auth.service import auth_service

logger = logging.getLogger(__name__)


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """Get the current authenticated user from HttpOnly cookie only"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    
    # Extract token from HttpOnly cookie only
    token = auth_service.extract_token_from_request(request)
    if token is None:
        if os.getenv("ENVIRONMENT", "development") != "production":
            logger.warning("Authentication failed: No token found in cookies")
        raise credentials_exception
    
    payload = auth_service.verify_token(token)
    if payload is None:
        if os.getenv("ENVIRONMENT", "development") != "production":
            logger.warning("Authentication failed: Invalid or expired token")
        raise credentials_exception
    
    user_id_str: str = payload.get("sub")
    if user_id_str is None:
        if os.getenv("ENVIRONMENT", "development") != "production":
            logger.warning("Authentication failed: No user ID in token payload")
        raise credentials_exception
    
    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        if os.getenv("ENVIRONMENT", "development") != "production":
            logger.warning("Authentication failed: Invalid user ID format")
        raise credentials_exception
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        if os.getenv("ENVIRONMENT", "development") != "production":
            logger.warning(f"Authentication failed: User not found with ID: {user_id}")
        raise credentials_exception
    
    if not user.is_active:
        if os.getenv("ENVIRONMENT", "development") != "production":
            logger.warning(f"Authentication failed: User {user.email} (ID: {user_id}) is inactive")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    if os.getenv("ENVIRONMENT", "development") != "production":
        logger.info(f"Authentication successful: {user.email} (Role: {user.role})")
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current active user (alias for consistency)"""
    return current_user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require admin role for access"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user


async def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db)
) -> User | None:
    """Get current user if authenticated, None otherwise"""
    try:
        token = auth_service.extract_token_from_request(request)
        if token is None:
            return None
        
        payload = auth_service.verify_token(token)
        if payload is None:
            return None
        
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            return None
        
        try:
            user_id = int(user_id_str)
        except (ValueError, TypeError):
            return None
        
        user = db.query(User).filter(User.id == user_id).first()
        if user is None or not user.is_active:
            return None
        
        return user
    except:
        return None


def require_student(current_user: User = Depends(get_current_user)) -> User:
    """Require student role for access"""
    if current_user.role not in ["student", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student access required"
        )
    return current_user


def require_professor(current_user: User = Depends(get_current_user)) -> User:
    """Require professor role for access"""
    if current_user.role not in ["professor", "teacher", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Professor access required"
        )
    return current_user

