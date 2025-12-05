"""Standard authentication router - Login, register, logout, profile endpoints."""
import logging
from fastapi import APIRouter, HTTPException, Depends, status, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from common.db.connection import get_db
from common.db.models import User
from common.db.schemas import UserResponse
from modules.auth.schemas import (
    UserRegister, UserLogin, UserLoginResponse, PasswordResetRequest
)
from modules.auth.service import auth_service
from modules.auth.oauth_router import router as oauth_router

logger = logging.getLogger(__name__)

router = APIRouter(tags=["authentication"])

# Include OAuth router
router.include_router(oauth_router)


@router.post("/register", response_model=UserResponse)
async def register_user(user: UserRegister, response: Response, db: Session = Depends(get_db)):
    """Register a new user"""
    logger.info(f"Registration request received for role: {user.role}")
    
    db_user = auth_service.register_user(
        db=db,
        email=user.email,
        full_name=user.full_name,
        username=user.username,
        password=user.password,
        role=user.role,
        bio=user.bio,
        avatar_url=user.avatar_url,
        profile_public=user.profile_public,
        allow_contact=user.allow_contact
    )
    
    access_token = auth_service.create_access_token(data={"sub": str(db_user.id)})
    auth_service.set_auth_cookie(response, access_token)
    
    return db_user


@router.post("/login", response_model=UserLoginResponse)
async def login_user(user: UserLogin, response: Response, db: Session = Depends(get_db)):
    """Login user and return access token"""
    logger.info(f"Login attempt for: {user.email}")
    
    check_user = db.query(User).filter(User.email == user.email).first()
    if not check_user:
        logger.warning(f"Login failed - User not found: {user.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    
    if not check_user.password_hash:
        logger.warning(f"Login failed - No password hash (OAuth user?): {user.email}, provider: {check_user.provider}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please login with Google" if check_user.provider == "google" else "Incorrect email or password",
        )
    
    db_user = auth_service.authenticate_user(db, user.email, user.password)
    if not db_user:
        logger.warning(f"Login failed - Password incorrect: {user.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    
    logger.info(f"Login successful: {user.email}")
    
    access_token = auth_service.create_access_token(data={"sub": str(db_user.id)})
    auth_service.set_auth_cookie(response, access_token)
    
    return UserLoginResponse(
        access_token="",
        token_type="cookie",
        user=UserResponse(
            id=db_user.id,
            email=db_user.email,
            full_name=db_user.full_name,
            username=db_user.username,
            bio=db_user.bio,
            avatar_url=db_user.avatar_url,
            role=db_user.role,
            published_scenarios=db_user.published_scenarios,
            total_simulations=db_user.total_simulations,
            reputation_score=db_user.reputation_score,
            profile_public=db_user.profile_public,
            allow_contact=db_user.allow_contact,
            is_active=db_user.is_active,
            is_verified=db_user.is_verified,
            created_at=db_user.created_at,
            updated_at=db_user.updated_at
        )
    )


@router.post("/logout")
async def logout_user(response: Response):
    """Logout user by clearing HttpOnly cookie"""
    auth_service.clear_auth_cookie(response)
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get current user profile"""
    from app.dependencies import get_current_user
    current_user = await get_current_user(request, db)
    return current_user


@router.post("/forgot-password")
async def forgot_password(request: PasswordResetRequest, db: Session = Depends(get_db)):
    """Reset a user's password after confirming email"""
    normalized_email = request.email.strip().lower()

    user = db.query(User).filter(func.lower(User.email) == normalized_email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found with that email address"
        )

    if user.provider and user.provider != "password":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account uses Google sign-in. Please login with Google to manage your password."
        )

    user.password_hash = auth_service.get_password_hash(request.new_password)
    user.updated_at = datetime.utcnow()

    db.add(user)
    db.commit()

    return {"message": "Password updated successfully"}


@router.post("/check-email")
async def check_email_exists(request: dict, db: Session = Depends(get_db)):
    """Check if an email already exists in the database"""
    email = request.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    
    existing_user = db.query(User).filter(User.email == email).first()
    return {"exists": existing_user is not None}


@router.get("/status")
async def get_auth_status(
    request: Request,
    db: Session = Depends(get_db)
):
    """Check current authentication status"""
    try:
        from app.dependencies import get_current_user
        user = await get_current_user(request, db)
        return {
            "authenticated": True,
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "provider": user.provider,
                "google_id": user.google_id,
                "is_active": user.is_active,
                "is_verified": user.is_verified
            }
        }
    except HTTPException as e:
        return {
            "authenticated": False,
            "error": e.detail,
            "status_code": e.status_code
        }
    except Exception as e:
        return {
            "authenticated": False,
            "error": str(e),
            "status_code": 500
        }
