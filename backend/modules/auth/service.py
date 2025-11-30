"""
Authentication service - Business logic for authentication
"""
from datetime import timedelta
from typing import Optional
import os
from fastapi import HTTPException, status, Request, Response
from sqlalchemy.orm import Session
from common.config import get_settings
from common.db.models import User
from common.utils.id_generator import generate_unique_user_id
from common.security.passwords import hash_password, verify_password
from common.security.tokens import create_access_token, decode_token

# JWT settings
settings = get_settings()
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_exp_minutes  # Use setting from config

class AuthService:
    """Authentication service for password validation, token management, and user operations"""
    
    def __init__(self, user_repository=None):
         # Optional repository injection for testability/future use
         self.user_repository = user_repository

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return verify_password(plain_password, hashed_password)
    
    def get_password_hash(self, password: str) -> str:
        """Hash a password"""
        return hash_password(password)
    
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token"""
        # The common utility expects 'subject' as a string, but our legacy code passes a dict
        # We adapt it here
        subject = data.get("sub")
        if not subject:
             raise ValueError("Token data must contain 'sub'")
        return create_access_token(subject=subject, expires_delta=expires_delta)
    
    def verify_token(self, token: str) -> Optional[dict]:
        """Verify and decode a JWT token"""
        try:
            return decode_token(token)
        except ValueError:
            return None
    
    def extract_token_from_request(self, request: Request) -> Optional[str]:
        """Extract JWT token from HttpOnly cookie only"""
        token_cookie = request.cookies.get("access_token")
        if token_cookie:
            return token_cookie
        return None
    
    def authenticate_user(self, db: Session, email: str, password: str) -> Optional[User]:
        """Authenticate a user with email and password"""
        # Note: Ideally use repository here
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return None
        if not user.password_hash:
            return None
        if not self.verify_password(password, user.password_hash):
            return None
        return user
    
    def register_user(self, db: Session, email: str, full_name: str, username: str, 
                     password: str, role: str, bio: Optional[str] = None,
                     avatar_url: Optional[str] = None, profile_public: bool = True,
                     allow_contact: bool = True) -> User:
        """Register a new user"""
        # Check if user already exists
        existing_user = db.query(User).filter(
            (User.email == email) | (User.username == username)
        ).first()
        
        if existing_user:
            if existing_user.email == email:
                raise HTTPException(status_code=400, detail="Email already registered")
            else:
                raise HTTPException(status_code=400, detail="Username already taken")
        
        # Generate role-based user ID
        try:
            user_id = generate_unique_user_id(db, role)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to generate user ID: {str(e)}")
        
        # Create new user
        hashed_password = self.get_password_hash(password)
        db_user = User(
            user_id=user_id,
            email=email,
            full_name=full_name,
            username=username,
            password_hash=hashed_password,
            role=role,
            bio=bio,
            avatar_url=avatar_url,
            profile_public=profile_public,
            allow_contact=allow_contact
        )
        
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        return db_user
    
    def set_auth_cookie(self, response: Response, access_token: str):
        """Set authentication cookie with proper security settings"""
        
        is_production = settings.environment == "production" if hasattr(settings, 'environment') else False
        cookie_max_age = ACCESS_TOKEN_EXPIRE_MINUTES * 60  # Convert minutes to seconds
        
        cookie_params = {
            "key": "access_token",
            "value": access_token,
            "httponly": True,  # HttpOnly cookie - not accessible via JavaScript
            "secure": is_production,  # Secure flag for HTTPS in production
            "samesite": "none" if is_production else "lax",  # Cross-origin support in production
            "path": "/",
            "max_age": cookie_max_age  # Matches token expiry
        }
        
        # Only set domain if explicitly configured and in production
        cookie_domain = os.getenv('COOKIE_DOMAIN', 'localhost')
        if is_production and cookie_domain and cookie_domain != 'localhost':
            cookie_params["domain"] = cookie_domain
        
        response.set_cookie(**cookie_params)
    
    def clear_auth_cookie(self, response: Response):
        """Clear authentication cookie"""
        
        is_production = settings.environment == "production" if hasattr(settings, 'environment') else False
        
        cookie_params = {
            "key": "access_token",
            "httponly": True,
            "secure": is_production,
            "samesite": "none" if is_production else "lax",
            "path": "/"
        }
        
        # Include domain if it was set during login (must match exactly)
        cookie_domain = os.getenv('COOKIE_DOMAIN', 'localhost')
        if is_production and cookie_domain and cookie_domain != 'localhost':
            cookie_params["domain"] = cookie_domain
        
        response.delete_cookie(**cookie_params)


# Export singleton instance
auth_service = AuthService()

