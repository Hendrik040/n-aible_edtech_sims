"""
Authentication utilities for the CrewAI Agent Builder Platform
"""
from datetime import datetime, timedelta
from typing import Optional, Union
import os
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import HTTPException, status, Depends, Request
from sqlalchemy.orm import Session
from database.connection import get_db, settings
from database.models import User

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = settings.secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30  # 30 minutes token expiry

# Validate SECRET_KEY
if not SECRET_KEY or not SECRET_KEY.strip():
    raise RuntimeError("SECRET_KEY is required and cannot be empty. Please set it in your environment variables.")
if len(SECRET_KEY) < 32:
    raise RuntimeError("SECRET_KEY must be at least 32 characters long for security.")

# HttpOnly cookie-based authentication only

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[dict]:
    """Verify and decode a JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

def extract_token_from_request(request: Request) -> Optional[str]:
    """Extract JWT token from HttpOnly cookie only"""
    # Only get token from HttpOnly cookie for maximum security
    token_cookie = request.cookies.get("access_token")
    if token_cookie:
        return token_cookie
    
    return None

def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """Authenticate a user with email and password"""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user

async def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """Get the current authenticated user from HttpOnly cookie only"""
    import logging
    logger = logging.getLogger(__name__)
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    
    # Extract token from HttpOnly cookie only
    token = extract_token_from_request(request)
    if token is None:
        logger.warning("Authentication failed: No token found in cookies")
        raise credentials_exception
    
    payload = verify_token(token)
    if payload is None:
        logger.warning("Authentication failed: Invalid or expired token")
        raise credentials_exception
    
    user_id_str: str = payload.get("sub")
    if user_id_str is None:
        logger.warning("Authentication failed: No user ID in token payload")
        raise credentials_exception
    
    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        logger.warning(f"Authentication failed: Invalid user ID format: {user_id_str}")
        raise credentials_exception
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        logger.warning(f"Authentication failed: User not found with ID: {user_id}")
        raise credentials_exception
    
    if not user.is_active:
        logger.warning(f"Authentication failed: User {user.email} (ID: {user_id}) is inactive")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
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

# Optional authentication (for endpoints that work with or without auth)
async def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Get current user if authenticated, None otherwise"""
    try:
        # Extract token from HttpOnly cookie only
        token = extract_token_from_request(request)
        if token is None:
            return None
        
        payload = verify_token(token)
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