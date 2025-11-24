"""
Authentication service - Business logic for authentication
"""
from datetime import datetime, timedelta
from typing import Optional
import os
from passlib.context import CryptContext
from jose import JWTError, jwt
from fastapi import HTTPException, status, Request
from sqlalchemy.orm import Session
from database.connection import settings
from database.models import User
from common.utilities.id_generator import generate_unique_user_id

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = settings.secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1000  # Token expiry

# Validate SECRET_KEY
if not SECRET_KEY or not SECRET_KEY.strip():
    raise RuntimeError("SECRET_KEY is required and cannot be empty. Please set it in your environment variables.")
if len(SECRET_KEY) < 32:
    raise RuntimeError("SECRET_KEY must be at least 32 characters long for security.")


class AuthService:
    """Authentication service for password validation, token management, and user operations"""
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """Hash a password"""
        return pwd_context.hash(password)
    
    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def verify_token(token: str) -> Optional[dict]:
        """Verify and decode a JWT token"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except JWTError as e:
            # Only log in development to reduce log volume
            if os.getenv("ENVIRONMENT", "development") != "production":
                print(f"❌ JWT Verification Failed: {type(e).__name__}")
            return None
    
    @staticmethod
    def extract_token_from_request(request: Request) -> Optional[str]:
        """Extract JWT token from HttpOnly cookie only"""
        token_cookie = request.cookies.get("access_token")
        if token_cookie:
            return token_cookie
        return None
    
    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
        """Authenticate a user with email and password"""
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return None
        if not user.password_hash:
            return None
        if not AuthService.verify_password(password, user.password_hash):
            return None
        return user
    
    @staticmethod
    def register_user(db: Session, email: str, full_name: str, username: str, 
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
        hashed_password = AuthService.get_password_hash(password)
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
    
    @staticmethod
    def set_auth_cookie(response, access_token: str):
        """Set authentication cookie with proper security settings"""
        from fastapi import Response
        
        is_production = settings.environment == "production"
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
    
    @staticmethod
    def clear_auth_cookie(response):
        """Clear authentication cookie"""
        from fastapi import Response
        
        is_production = settings.environment == "production"
        
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

