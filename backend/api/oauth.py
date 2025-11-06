"""
Google OAuth API endpoints - Cleaned Version
"""
from fastapi import APIRouter, HTTPException, Depends, status, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
import json
import time
import asyncio
import logging
import os
import base64
from contextlib import asynccontextmanager
from cryptography.fernet import Fernet

from database.connection import get_db
from database.models import User
from database.schemas import (
    AccountLinkingRequest, 
    OAuthUserData,
    UserLoginResponse,
    RoleSelectionRequest
)
from utilities.oauth import (
    generate_state,
    verify_state,
    get_google_auth_url,
    exchange_code_for_token,
    verify_google_id_token,
    get_google_user_info_from_id_token,
    find_existing_user_by_email,
    find_existing_user_by_google_id,
    find_oauth_user_by_original_email,
    create_oauth_user,
    link_google_to_existing_user,
    create_user_login_response
)
from utilities.auth import create_access_token

# Logger for OAuth operations
logger = logging.getLogger(__name__)

# Configuration from environment variables
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')
COOKIE_DOMAIN = os.getenv('COOKIE_DOMAIN', 'localhost')
IS_PRODUCTION = os.getenv('ENVIRONMENT', '').lower() in ['production', 'prod']

class OAuthStateStore:
    """Persistent OAuth state storage using Redis"""
    
    def __init__(self):
        from utilities.redis_manager import redis_manager
        self.redis = redis_manager
        self._init_encryption()
    
    def _init_encryption(self):
        """Initialize encryption cipher for state payloads"""
        encryption_key = os.getenv('OAUTH_ENCRYPTION_KEY')
        if not encryption_key:
            if IS_PRODUCTION:
                logger.warning("⚠️  OAUTH_ENCRYPTION_KEY not found in production - OAuth state encryption disabled. Set OAUTH_ENCRYPTION_KEY for secure OAuth flows.")
                self.cipher = None
            else:
                # Development mode: use or generate persistent key
                try:
                    dev_key_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.oauth_encryption_key')
                    key = self._get_or_create_dev_key(dev_key_file)
                    logger.warning("No OAUTH_ENCRYPTION_KEY found, using development key from file. Set OAUTH_ENCRYPTION_KEY in production!")
                    self.cipher = Fernet(key)
                except Exception as e:
                    logger.error(f"Failed to initialize development encryption: {e}")
                    # Fallback to no encryption for development
                    self.cipher = None
        else:
            # Validate and use provided key - Fernet keys should be base64-encoded
            try:
                # First try to use the key as-is (assuming it's already base64-encoded)
                self.cipher = Fernet(encryption_key.encode('utf-8'))
            except Exception as e:
                logger.error(f"Invalid OAUTH_ENCRYPTION_KEY: {e}. OAuth state encryption disabled. Generate a key with: Fernet.generate_key().decode()")
                self.cipher = None
    
    def _get_or_create_dev_key(self, key_file_path: str) -> bytes:
        """Get existing dev key or create and persist a new one"""
        try:
            # Try to read existing key
            if os.path.exists(key_file_path):
                with open(key_file_path, 'rb') as f:
                    key = f.read()
                # Validate the key by trying to create a Fernet instance
                Fernet(key)  # This will raise an exception if invalid
                return key
        except Exception as e:
            logger.warning(f"Invalid or corrupted dev key file, generating new one: {e}")
        
        # Generate new key and persist it
        key = Fernet.generate_key()
        try:
            with open(key_file_path, 'wb') as f:
                f.write(key)
            # Set restrictive permissions (owner read/write only)
            os.chmod(key_file_path, 0o600)
        except Exception as e:
            logger.error(f"Failed to persist dev encryption key: {e}")
            # Continue with the generated key even if we can't persist it
        
        return key
    
    def set_state(self, state: str, data: Dict[str, Any], ttl: int = 600) -> bool:
        """Store OAuth state with TTL (default 10 minutes)"""
        try:
            # Add created_at timestamp
            data['created_at'] = time.time()
            
            # Encrypt the payload if cipher is available
            if self.cipher:
                try:
                    json_payload = json.dumps(data)
                    encrypted_payload = self.cipher.encrypt(json_payload.encode())
                    encrypted_data = base64.b64encode(encrypted_payload).decode('utf-8')
                except Exception as e:
                    logger.error(f"Failed to encrypt state data: {e}")
                    return False
            else:
                # No encryption available, store as JSON
                encrypted_data = json.dumps(data)
            
            # Use Redis manager to store the state
            return self.redis.set(state, encrypted_data, ttl)
        except Exception as e:
            logger.error(f"Failed to store OAuth state: {e}")
            return False
    
    def get_state(self, state: str) -> Optional[Dict[str, Any]]:
        """Retrieve OAuth state data"""
        try:
            encrypted_data = self.redis.get(state)
            if not encrypted_data:
                return None
            
            # Decrypt the payload if cipher is available
            if self.cipher:
                try:
                    # Redis returns strings with decode_responses=True, so use directly
                    encrypted_payload = base64.b64decode(encrypted_data)
                    decrypted_payload = self.cipher.decrypt(encrypted_payload)
                    return json.loads(decrypted_payload.decode('utf-8'))
                except Exception as e:
                    logger.error(f"Failed to decrypt state data: {e}")
                    return None
            else:
                # No encryption, parse as JSON
                return json.loads(encrypted_data)
        except Exception as e:
            logger.error(f"Failed to retrieve OAuth state: {e}")
            return None
    
    def delete_state(self, state: str) -> bool:
        """Delete OAuth state"""
        try:
            return self.redis.delete(state)
        except Exception as e:
            logger.error(f"Failed to delete OAuth state: {e}")
            return False

# Create the OAuth router
router = APIRouter(prefix="/auth", tags=["oauth"])

# Initialize OAuth state store
oauth_state_store = OAuthStateStore()

# Global cache to track used authorization codes (in-memory, will reset on restart)
used_authorization_codes = set()

# Global cleanup task reference
cleanup_task = None

def validate_oauth_state(state: str) -> Dict[str, Any]:
    """Validate OAuth state and return state data if valid"""
    if not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or missing OAuth state"
        )
    
    # Get state data from store
    state_data = oauth_state_store.get_state(state)
    if not state_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state"
        )
    
    # SECURITY: Verify the state parameter using hmac comparison
    stored_state = state_data.get("original_state")
    if stored_state and not verify_state(state, stored_state):
        logger.error(f"State mismatch: received={state}, stored={stored_state}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state - state parameter mismatch"
        )
    
    return state_data

def add_cors_headers(response: Response):
    """Add CORS headers for cookie support"""
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Origin"] = FRONTEND_URL

def create_oauth_success_redirect(user_login_response, access_token: str) -> RedirectResponse:
    """Create proper HTTP redirect for successful OAuth"""
    # Encode the user data and token for the redirect URL
    import urllib.parse
    
    # Use Pydantic's built-in JSON serialization to handle datetime objects
    if hasattr(user_login_response, 'model_dump_json'):
        # Pydantic v2 - use model_dump_json for proper datetime serialization
        user_data_json = user_login_response.model_dump_json()
    elif hasattr(user_login_response, 'json'):
        # Pydantic v1 - use json() method for proper datetime serialization
        user_data_json = user_login_response.json()
    else:
        # Fallback for regular dictionaries
        user_data_json = json.dumps(user_login_response)
    
    user_data_encoded = urllib.parse.quote(user_data_json)
    token_encoded = urllib.parse.quote(access_token)
    
    redirect_url = f"{FRONTEND_URL}/auth/google/callback?token={token_encoded}&user={user_data_encoded}"
    return RedirectResponse(url=redirect_url, status_code=302)

def create_account_linking_redirect(account_linking_data: dict) -> RedirectResponse:
    """Create proper HTTP redirect for account linking"""
    import urllib.parse
    data_encoded = urllib.parse.quote(json.dumps(account_linking_data))
    redirect_url = f"{FRONTEND_URL}/auth/google/account-linking?data={data_encoded}"
    return RedirectResponse(url=redirect_url, status_code=302)

def create_role_selection_redirect(role_selection_data: dict) -> RedirectResponse:
    """Create proper HTTP redirect for role selection"""
    import urllib.parse
    data_encoded = urllib.parse.quote(json.dumps(role_selection_data))
    redirect_url = f"{FRONTEND_URL}/auth/google/role-selection?data={data_encoded}"
    return RedirectResponse(url=redirect_url, status_code=302)

def set_auth_cookie(response: Response, access_token: str):
    """Set authentication cookie with proper security settings"""
    # In production, use samesite="none" for cross-origin cookies
    # In development, use samesite="lax" for local testing
    
    # Cookie expiry matches JWT token expiry (30 minutes)
    from utilities.auth import ACCESS_TOKEN_EXPIRE_MINUTES
    cookie_max_age = ACCESS_TOKEN_EXPIRE_MINUTES * 60  # Convert minutes to seconds
    
    cookie_params = {
        "key": "access_token",
        "value": access_token,
        "httponly": True,  # HttpOnly cookie - not accessible via JavaScript
        "secure": IS_PRODUCTION,  # Secure flag for HTTPS in production
        "samesite": "none" if IS_PRODUCTION else "lax",  # Cross-origin support in production
        "path": "/",
        "max_age": cookie_max_age  # Matches token expiry
    }
    
    # Only set domain if explicitly configured and in production
    # Setting domain incorrectly can prevent cookies from working
    if IS_PRODUCTION and COOKIE_DOMAIN and COOKIE_DOMAIN != 'localhost':
        cookie_params["domain"] = COOKIE_DOMAIN
    
    response.set_cookie(**cookie_params)

async def periodic_cleanup():
    """Periodic cleanup task that runs every 5 minutes"""
    while True:
        try:
            await asyncio.sleep(300)  # 5 minutes
            # Clear old authorization codes (keep only last 1000 to prevent memory bloat)
            global used_authorization_codes
            if len(used_authorization_codes) > 1000:
                # Keep only the most recent 500 codes
                used_authorization_codes = set(list(used_authorization_codes)[-500:])
                logger.info("Cleaned up old authorization codes")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Periodic cleanup failed: {e}")

@asynccontextmanager
async def lifespan(app):
    """FastAPI lifespan handler for startup and shutdown"""
    global cleanup_task
    # Startup
    cleanup_task = asyncio.create_task(periodic_cleanup())
    logger.info("Started OAuth state cleanup task")
    yield
    # Shutdown
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        logger.info("Stopped OAuth state cleanup task")

# Route definitions (removing duplicates)

@router.post("/clear-cache")
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
        state = generate_state()
        auth_url = get_google_auth_url(state)
        
        # Store initial state with original state for verification
        oauth_state_store.set_state(state, {
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
    
    # Validate OAuth state
    state_data = validate_oauth_state(state)
    
    # Check if this callback has already been processed
    if state_data.get("status") == "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth callback has already been processed. Please try logging in again."
        )
    
    # Check if this authorization code has already been used globally
    if code in used_authorization_codes:
        logger.warning(f"Authorization code already used: {code[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization code has already been used. Please try logging in again."
        )
    
    # Check if this authorization code is already being processed
    if state_data.get("status") == "processing":
        logger.warning(f"Authorization code already being processed for state: {state}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth callback is already being processed. Please wait."
        )
    
    # Mark state as being processed to prevent duplicate calls
    oauth_state_store.set_state(state, {
        **state_data,
        "status": "processing",
        "authorization_code": code
    })
    
    try:
        # Exchange code for token
        token_data = exchange_code_for_token(code, state)
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to exchange code for token. The authorization code may have expired or been used already. Please try logging in again."
            )
        
        # Verify id_token for secure user authentication
        if not token_data.get("id_token"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing ID token in OAuth response"
            )
        
        try:
            # Verify the ID token and get validated claims
            user_info = verify_google_id_token(token_data["id_token"])
        except HTTPException:
            # Re-raise HTTP exceptions from verification
            raise
        except Exception as e:
            logger.error(f"ID token verification failed: {e}")
            # Fallback to userinfo endpoint if id_token verification fails
            logger.warning("Falling back to userinfo endpoint")
            user_info = get_google_user_info_from_id_token(token_data["id_token"])
            if not user_info:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to get user information from Google"
                )
        
        # Extract Google ID using OIDC 'sub' claim with 'id' fallback
        google_id = user_info.get("sub") or user_info.get("id")
        if not google_id:
            raise HTTPException(status_code=400, detail="Invalid Google user info (missing subject)")
        
        # Validate OAuth user data using schema
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
        
        # Mark authorization code as used (only after successful token exchange)
        used_authorization_codes.add(code)
        
        # Check if user already exists with this Google ID
        logger.info(f"Looking for existing user with Google ID: {google_id}")
        existing_google_user = find_existing_user_by_google_id(db, google_id)
        if existing_google_user:
            logger.info(f"Found existing user by Google ID: {existing_google_user.email} (ID: {existing_google_user.id})")
            
            # Create access token and set cookie
            access_token = create_access_token(data={"sub": str(existing_google_user.id)})
            set_auth_cookie(response, access_token)
            add_cors_headers(response)
            
            # Clean up state
            oauth_state_store.delete_state(state)
            
            user_login_response = create_user_login_response(existing_google_user)
            return create_oauth_success_redirect(user_login_response, access_token)
        # Check if user exists with this email (simple lookup first)
        existing_email_user = find_existing_user_by_email(db, oauth_user_data.email)
        logger.info(f"Email lookup for {oauth_user_data.email} found: {existing_email_user.email if existing_email_user else 'None'}")
        
        # If not found with simple lookup, try complex OAuth email lookup
        if not existing_email_user:
            existing_email_user = find_oauth_user_by_original_email(db, oauth_user_data.email)
            logger.info(f"OAuth email lookup for {oauth_user_data.email} found: {existing_email_user.email if existing_email_user else 'None'}")
        
        if existing_email_user:
            # Check if the existing user is already an OAuth user
            if existing_email_user.provider == "google":
                logger.info(f"Found existing Google user by email: {existing_email_user.email} (ID: {existing_email_user.id})")
                
                # Update Google ID if it's missing (fix for existing users)
                if not existing_email_user.google_id:
                    logger.info(f"Updating missing Google ID for user {existing_email_user.email}")
                    existing_email_user.google_id = google_id
                    db.commit()
                    db.refresh(existing_email_user)
                
                # Create access token and set cookie
                access_token = create_access_token(data={"sub": str(existing_email_user.id)})
                set_auth_cookie(response, access_token)
                add_cors_headers(response)
                
                # Clean up state
                oauth_state_store.delete_state(state)
                
                user_login_response = create_user_login_response(existing_email_user)
                return create_oauth_success_redirect(user_login_response, access_token)
            else:
                # Account linking scenario for non-OAuth users
                oauth_state_store.set_state(state, {
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
        
        # No existing user found by email - this is a completely new user
        logger.info(f"No existing user found with email: {oauth_user_data.email}")
        # Create new user and redirect to role selection
        oauth_state_store.set_state(state, {
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
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"OAuth callback processing failed: {e}")
        logger.error(f"OAuth callback error details: {type(e).__name__}: {str(e)}")
        import traceback
        logger.error(f"OAuth callback traceback: {traceback.format_exc()}")
        # Clean up state on failure
        oauth_state_store.delete_state(state)
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
    
    # Validate OAuth state
    state_data = validate_oauth_state(role_data.state)
    
    # Check if this is a role selection request
    if state_data.get("status") != "role_selection_required":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role selection not required for this OAuth flow"
        )
    
    # Get user info from state
    user_info = state_data.get("user_info")
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing user information in OAuth state"
        )
    
    # Create new user with selected role
    logger.info(f"Creating new user with role: {role_data.role}")
    logger.info(f"User info: {user_info}")
    
    # Format user_info for create_oauth_user
    google_data = {
        "sub": user_info.get("google_id"),
        "id": user_info.get("google_id"),
        "email": user_info.get("email"),
        "name": user_info.get("name"),
        "picture": user_info.get("picture")
    }
    
    new_user = create_oauth_user(db, google_data, role=role_data.role)
    logger.info(f"Created user: {new_user.email} with role: {new_user.role} (ID: {new_user.id})")
    
    # Create access token and set cookie
    access_token = create_access_token(data={"sub": str(new_user.id)})
    set_auth_cookie(response, access_token)
    add_cors_headers(response)
    
    # Clean up state
    oauth_state_store.delete_state(role_data.state)
    
    return create_user_login_response(new_user)

@router.post("/google/link", response_model=UserLoginResponse)
async def link_google_account(
    request: AccountLinkingRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    """Link Google account to existing user or create separate account"""
    
    # Validate OAuth state and get server-stored google_data
    state_data = validate_oauth_state(request.state)
    
    # Extract google_data from server-stored state (not client-supplied)
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
    
    # Use server-stored google_data (prevents account takeover)
    server_google_data = payload["google_data"]
    
    # Get existing user
    existing_user = db.query(User).filter(User.id == request.existing_user_id).first()
    if not existing_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Convert server-stored google_data to format expected by utility functions
    google_user_data = {
        "email": server_google_data["email"],
        "name": server_google_data["name"],
        "picture": server_google_data["picture"],
        "sub": server_google_data["id"],
        "id": server_google_data["id"]
    }
    
    if request.action == "link":
        # Link Google account to existing user
        linked_user = link_google_to_existing_user(db, existing_user, google_user_data)
        
        # Create access token and set cookie
        access_token = create_access_token(data={"sub": str(linked_user.id)})
        set_auth_cookie(response, access_token)
        
        oauth_state_store.delete_state(request.state)  # Clean up state
        return create_user_login_response(linked_user)
    
    elif request.action == "create_separate":
        # Create separate account with Google OAuth using selected role
        new_user = create_oauth_user(db, google_user_data, force_create=True, role=request.role)
        
        # Create access token and set cookie
        access_token = create_access_token(data={"sub": str(new_user.id)})
        set_auth_cookie(response, access_token)
        
        oauth_state_store.delete_state(request.state)  # Clean up state
        return create_user_login_response(new_user)
    
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid action. Must be 'link' or 'create_separate'"
        )

@router.get("/google/status/{state}")
async def get_oauth_status(state: str):
    """Get OAuth status for a given state"""
    state_data = oauth_state_store.get_state(state)
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
        # Handle legacy string format
        if state_data == "pending":
            return {"status": "pending", "link_required": False}
        
        try:
            parsed = json.loads(state_data)
            link_required = parsed.get("status") == "link_required"
            return {"status": "completed", "data": parsed, "link_required": link_required}
        except json.JSONDecodeError:
            return {"status": "completed", "data": state_data, "link_required": False}

@router.get("/auth/status")
async def get_auth_status(
    request: Request,
    db: Session = Depends(get_db)
):
    """Check current authentication status"""
    try:
        from utilities.auth import get_current_user
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