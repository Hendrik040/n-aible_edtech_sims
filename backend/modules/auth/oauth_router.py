"""OAuth authentication router for Google OAuth."""
import logging
import time
from fastapi import APIRouter, HTTPException, Depends, status, Response
from sqlalchemy.orm import Session

from common.db.connection import get_db
from common.db.models import User
from modules.auth.schemas import (
    AccountLinkingRequest, RoleSelectionRequest, OAuthUserData, UserLoginResponse
)
from modules.auth.service import auth_service
from modules.auth.provider import google_oauth_provider
from modules.auth.helpers import (
    add_cors_headers, create_oauth_success_redirect,
    create_account_linking_redirect, create_role_selection_redirect,
    validate_oauth_state
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/google", tags=["oauth"])

# Global cache to track used authorization codes
used_authorization_codes = set()


@router.post("/clear-cache")
async def clear_oauth_cache():
    """Clear the OAuth authorization code cache (for debugging)"""
    global used_authorization_codes
    cleared_count = len(used_authorization_codes)
    used_authorization_codes.clear()
    logger.info(f"Cleared {cleared_count} authorization codes from cache")
    return {"message": f"Cleared {cleared_count} authorization codes from cache"}


@router.get("/login")
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


@router.get("/callback")
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
        import traceback
        logger.error(f"OAuth callback traceback: {traceback.format_exc()}")
        google_oauth_provider.state_store.delete_state(state)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process OAuth callback: {str(e)}"
        )


@router.post("/select-role", response_model=UserLoginResponse)
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


@router.post("/link", response_model=UserLoginResponse)
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


@router.get("/status/{state}")
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
            import json
            parsed = json.loads(state_data)
            link_required = parsed.get("status") == "link_required"
            return {"status": "completed", "data": parsed, "link_required": link_required}
        except json.JSONDecodeError:
            return {"status": "completed", "data": state_data, "link_required": False}




