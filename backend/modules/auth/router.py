"""
Authentication router - Login, register, token refresh, OAuth endpoints
"""
import os
import logging
import urllib.parse
import time
import json
import traceback
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, status, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from app.dependencies import get_current_user
from common.db.core import get_db
from common.config import get_settings
from common.db.models import User
from common.db.schemas import UserResponse
from modules.auth.schemas import (
    UserRegister, UserLogin, UserLoginResponse, PasswordResetRequest,
    AccountLinkingRequest, RoleSelectionRequest, OAuthUserData
)
from modules.auth.service import auth_service
from modules.auth.provider import google_oauth_provider

logger = logging.getLogger(__name__)
settings = get_settings()

# Configuration
FRONTEND_URL = os.getenv('FRONTEND_BASE_URL', 'http://localhost:3000')
COOKIE_DOMAIN = os.getenv('COOKIE_DOMAIN', 'localhost')
IS_PRODUCTION = os.getenv('ENVIRONMENT', '').lower() in ['production', 'prod']

# Create the auth router
# Using /users prefix for backward compatibility with frontend
router = APIRouter(prefix="/users", tags=["authentication"])

# Global cache to track used authorization codes
used_authorization_codes = set()


def add_cors_headers(response: Response):
    """Add CORS headers for cookie support"""
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Origin"] = FRONTEND_URL


def create_oauth_success_redirect(user_login_response, access_token: str) -> RedirectResponse:
    """Create proper HTTP redirect for successful OAuth"""
    if hasattr(user_login_response, 'model_dump_json'):
        user_data_json = user_login_response.model_dump_json()
    elif hasattr(user_login_response, 'json'):
        user_data_json = user_login_response.json()
    else:
        user_data_json = json.dumps(user_login_response)
    
    user_data_encoded = urllib.parse.quote(user_data_json)
    token_encoded = urllib.parse.quote(access_token)
    
    redirect_url = f"{FRONTEND_URL}/auth/google/callback?token={token_encoded}&user={user_data_encoded}"
    return RedirectResponse(url=redirect_url, status_code=302)


def create_account_linking_redirect(account_linking_data: dict) -> RedirectResponse:
    """Create proper HTTP redirect for account linking"""
    data_encoded = urllib.parse.quote(json.dumps(account_linking_data))
    redirect_url = f"{FRONTEND_URL}/auth/google/account-linking?data={data_encoded}"
    return RedirectResponse(url=redirect_url, status_code=302)


def create_role_selection_redirect(role_selection_data: dict) -> RedirectResponse:
    """Create proper HTTP redirect for role selection"""
    data_encoded = urllib.parse.quote(json.dumps(role_selection_data))
    redirect_url = f"{FRONTEND_URL}/auth/google/role-selection?data={data_encoded}"
    return RedirectResponse(url=redirect_url, status_code=302)


def validate_oauth_state(state: str) -> dict:
    """Validate OAuth state and return state data if valid"""
    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or missing OAuth state"
        )
    
    state_data = google_oauth_provider.state_store.get_state(state)
    if not state_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state"
        )
    
    stored_state = state_data.get("original_state")
    if stored_state and not google_oauth_provider.verify_state(state, stored_state):
        logger.error(f"State mismatch: received={state}, stored={stored_state}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state - state parameter mismatch"
        )
    
    return state_data


# --- Standard Auth Endpoints ---

@router.post("/register", response_model=UserResponse)
async def register_user(user: UserRegister, response: Response, db: Session = Depends(get_db)):
    """Register a new user"""
    try:
        logger.info(f"🔍 Registration request received for role: {user.role}")
        
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
        
        # Create access token and set HttpOnly cookie
        access_token = auth_service.create_access_token(data={"sub": str(db_user.id)})
        auth_service.set_auth_cookie(response, access_token)
        
        return db_user
    except Exception as e:
        logger.error(f"Registration error: {e}", exc_info=True)
        raise


@router.post("/login", response_model=UserLoginResponse)
async def login_user(user: UserLogin, response: Response, db: Session = Depends(get_db)):
    """Login user and return access token"""
    logger.info(f"🔐 Login attempt for: {user.email}")
    
    check_user = db.query(User).filter(User.email == user.email).first()
    if not check_user:
        logger.warning(f"❌ Login failed - User not found: {user.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    
    if not check_user.password_hash:
        logger.warning(f"❌ Login failed - No password hash (OAuth user?): {user.email}, provider: {check_user.provider}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please login with Google" if check_user.provider == "google" else "Incorrect email or password",
        )
    
    db_user = auth_service.authenticate_user(db, user.email, user.password)
    if not db_user:
        logger.warning(f"❌ Login failed - Password incorrect: {user.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    
    logger.info(f"✅ Login successful: {user.email}")
    
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
            published_simulations=db_user.published_simulations,
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


# --- OAuth Endpoints ---

@router.post("/google/clear-cache")
async def clear_oauth_cache():
    """Clear the OAuth authorization code cache (for debugging)"""
    global used_authorization_codes
    cleared_count = len(used_authorization_codes)
    used_authorization_codes.clear()
    logger.info(f"Cleared {cleared_count} authorization codes from cache")
    return {"message": f"Cleared {cleared_count} authorization codes from cache"}


@router.get("/google/login")
async def google_login():
    """Initiate Google OAuth login"""
    try:
        state = google_oauth_provider.generate_state()
        auth_url = google_oauth_provider.get_auth_url(state)
        
        google_oauth_provider.state_store.set_state(state, {
            "status": "pending",
            "created_at": time.time(),
            "original_state": state
        })
        
        return {"auth_url": auth_url, "state": state}
    except Exception as e:
        logger.error(f"Google login initiation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate Google login"
        )


@router.get("/google/callback")
async def google_callback(
    code: str = None,
    state: str = None,
    error: str = None,
    response: Response = None,
    db: Session = Depends(get_db)
):
    """Handle Google OAuth callback"""
    logger.info(f"OAuth callback received: code={code[:10] if code else 'None'}..., state={state}, error={error}")
    
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth error: {error}"
        )
    
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code or state"
        )
    
    state_data = validate_oauth_state(state)
    
    if state_data.get("status") == "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth callback has already been processed. Please try logging in again."
        )
    
    if code in used_authorization_codes:
        logger.warning(f"Authorization code already used: {code[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization code has already been used. Please try logging in again."
        )
    
    if state_data.get("status") == "processing":
        logger.warning(f"Authorization code already being processed for state: {state}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth callback is already being processed. Please wait."
        )
    
    google_oauth_provider.state_store.set_state(state, {
        **state_data,
        "status": "processing",
        "authorization_code": code
    })
    
    try:
        token_data = google_oauth_provider.exchange_code_for_token(code, state)
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to exchange code for token. The authorization code may have expired or been used already. Please try logging in again."
            )
        
        if not token_data.get("id_token"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing ID token in OAuth response"
            )
        
        try:
            user_info = google_oauth_provider.verify_id_token(token_data["id_token"])
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"ID token verification failed: {e}")
            logger.warning("Falling back to userinfo endpoint")
            user_info = google_oauth_provider.get_user_info_from_id_token(token_data["id_token"])
            if not user_info:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to get user information from Google"
                )
        
        google_id = user_info.get("sub") or user_info.get("id")
        if not google_id:
            raise HTTPException(status_code=400, detail="Invalid Google user info (missing subject)")
        
        try:
            oauth_user_data = OAuthUserData(
                google_id=google_id,
                email=user_info.get("email", ""),
                full_name=user_info.get("name", ""),
                avatar_url=user_info.get("picture")
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid OAuth user data: {str(e)}"
            )
        
        used_authorization_codes.add(code)
        
        logger.info(f"Looking for existing user with Google ID: {google_id}")
        existing_google_user = google_oauth_provider.find_existing_user_by_google_id(db, google_id)
        if existing_google_user:
            logger.info(f"Found existing user by Google ID: {existing_google_user.email} (ID: {existing_google_user.id})")
            
            access_token = auth_service.create_access_token(data={"sub": str(existing_google_user.id)})
            auth_service.set_auth_cookie(response, access_token)
            add_cors_headers(response)
            
            google_oauth_provider.state_store.delete_state(state)
            
            user_login_response = google_oauth_provider.create_user_login_response(existing_google_user)
            return create_oauth_success_redirect(user_login_response, access_token)
        
        existing_email_user = google_oauth_provider.find_existing_user_by_email(db, oauth_user_data.email)
        logger.info(f"Email lookup for {oauth_user_data.email} found: {existing_email_user.email if existing_email_user else 'None'}")
        
        if not existing_email_user:
            existing_email_user = google_oauth_provider.find_oauth_user_by_original_email(db, oauth_user_data.email)
            logger.info(f"OAuth email lookup for {oauth_user_data.email} found: {existing_email_user.email if existing_email_user else 'None'}")
        
        if existing_email_user:
            if existing_email_user.provider == "google":
                logger.info(f"Found existing Google user by email: {existing_email_user.email} (ID: {existing_email_user.id})")
                
                if not existing_email_user.google_id:
                    logger.info(f"Updating missing Google ID for user {existing_email_user.email}")
                    existing_email_user.google_id = google_id
                    db.commit()
                    db.refresh(existing_email_user)
                
                access_token = auth_service.create_access_token(data={"sub": str(existing_email_user.id)})
                auth_service.set_auth_cookie(response, access_token)
                add_cors_headers(response)
                
                google_oauth_provider.state_store.delete_state(state)
                
                user_login_response = google_oauth_provider.create_user_login_response(existing_email_user)
                return create_oauth_success_redirect(user_login_response, access_token)
            else:
                google_oauth_provider.state_store.set_state(state, {
                    "status": "link_required",
                    "created_at": state_data.get("created_at"),
                    "payload": {
                        "google_data": {
                            "id": oauth_user_data.google_id,
                            "email": oauth_user_data.email,
                            "name": oauth_user_data.full_name,
                            "picture": oauth_user_data.avatar_url
                        },
                        "existing_user_id": existing_email_user.id
                    }
                })
                
                account_linking_data = {
                    "link_required": True,
                    "message": "An account with this email already exists. Would you like to link your Google account?",
                    "existing_user": {
                        "id": existing_email_user.id,
                        "email": existing_email_user.email,
                        "full_name": existing_email_user.full_name,
                        "provider": existing_email_user.provider
                    },
                    "google_data": {
                        "email": oauth_user_data.email,
                        "full_name": oauth_user_data.full_name,
                        "avatar_url": oauth_user_data.avatar_url,
                        "google_id": oauth_user_data.google_id
                    },
                    "state": state
                }
            
                return create_account_linking_redirect(account_linking_data)
        
        logger.info(f"No existing user found with email: {oauth_user_data.email}")
        google_oauth_provider.state_store.set_state(state, {
            "status": "role_selection_required",
            "created_at": state_data.get("created_at"),
            "user_info": {
                "google_id": google_id,
                "email": oauth_user_data.email,
                "name": oauth_user_data.full_name,
                "picture": oauth_user_data.avatar_url
            }
        })
        
        role_selection_data = {
            "requires_role_selection": True,
            "state": state,
            "user_info": {
                "google_id": google_id,
                "email": oauth_user_data.email,
                "name": oauth_user_data.full_name,
                "picture": oauth_user_data.avatar_url
            }
        }
        
        return create_role_selection_redirect(role_selection_data)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth callback processing failed: {e}")
        logger.error(f"OAuth callback error details: {type(e).__name__}: {str(e)}")
        logger.error(f"OAuth callback traceback: {traceback.format_exc()}")
        google_oauth_provider.state_store.delete_state(state)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process OAuth callback: {str(e)}"
        )


@router.post("/google/select-role", response_model=UserLoginResponse)
async def select_role_for_oauth(
    role_data: RoleSelectionRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    """Select role for OAuth user after Google authentication"""
    
    state_data = validate_oauth_state(role_data.state)
    
    if state_data.get("status") != "role_selection_required":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role selection not required for this OAuth flow"
        )
    
    user_info = state_data.get("user_info")
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing user information in OAuth state"
        )
    
    logger.info(f"Creating new user with role: {role_data.role}")
    
    google_data = {
        "sub": user_info.get("google_id"),
        "id": user_info.get("google_id"),
        "email": user_info.get("email"),
        "name": user_info.get("name"),
        "picture": user_info.get("picture")
    }
    
    new_user = google_oauth_provider.create_oauth_user(db, google_data, role=role_data.role)
    logger.info(f"Created user: {new_user.email} with role: {new_user.role} (ID: {new_user.id})")
    
    access_token = auth_service.create_access_token(data={"sub": str(new_user.id)})
    auth_service.set_auth_cookie(response, access_token)
    add_cors_headers(response)
    
    google_oauth_provider.state_store.delete_state(role_data.state)
    
    return google_oauth_provider.create_user_login_response(new_user)


@router.post("/google/link", response_model=UserLoginResponse)
async def link_google_account(
    request: AccountLinkingRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    """Link Google account to existing user or create separate account"""
    
    state_data = validate_oauth_state(request.state)
    
    if not isinstance(state_data, dict) or "payload" not in state_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state - missing payload data"
        )
    
    payload = state_data["payload"]
    if "google_data" not in payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state - missing Google user data"
        )
    
    server_google_data = payload["google_data"]
    
    existing_user = db.query(User).filter(User.id == request.existing_user_id).first()
    if not existing_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    google_user_data = {
        "email": server_google_data["email"],
        "name": server_google_data["name"],
        "picture": server_google_data["picture"],
        "sub": server_google_data["id"],
        "id": server_google_data["id"]
    }
    
    if request.action == "link":
        linked_user = google_oauth_provider.link_google_to_existing_user(db, existing_user, google_user_data)
        
        access_token = auth_service.create_access_token(data={"sub": str(linked_user.id)})
        auth_service.set_auth_cookie(response, access_token)
        
        google_oauth_provider.state_store.delete_state(request.state)
        return google_oauth_provider.create_user_login_response(linked_user)
    
    elif request.action == "create_separate":
        new_user = google_oauth_provider.create_oauth_user(db, google_user_data, force_create=True, role=request.role)
        
        access_token = auth_service.create_access_token(data={"sub": str(new_user.id)})
        auth_service.set_auth_cookie(response, access_token)
        
        google_oauth_provider.state_store.delete_state(request.state)
        return google_oauth_provider.create_user_login_response(new_user)
    
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid action. Must be 'link' or 'create_separate'"
        )


@router.get("/google/status/{state}")
async def get_oauth_status(state: str):
    """Get OAuth status for a given state"""
    state_data = google_oauth_provider.state_store.get_state(state)
    if not state_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OAuth state not found or expired"
        )
    
    if isinstance(state_data, dict):
        link_required = state_data.get("status") == "link_required"
        if state_data.get("status") == "pending":
            return {"status": "pending", "link_required": link_required}
        else:
            return {"status": "completed", "data": state_data, "link_required": link_required}
    else:
        if state_data == "pending":
            return {"status": "pending", "link_required": False}
        
        try:
            parsed = json.loads(state_data)
            link_required = parsed.get("status") == "link_required"
            return {"status": "completed", "data": parsed, "link_required": link_required}
        except json.JSONDecodeError:
            return {"status": "completed", "data": state_data, "link_required": False}


@router.get("/status")
async def get_auth_status(
    request: Request,
    db: Session = Depends(get_db)
):
    """Check current authentication status"""
    try:
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

