"""
OAuth utilities for Google authentication using google-auth-oauthlib
"""
import logging
from typing import Optional, Dict, Any
from database.connection import settings
from database.models import User
from sqlalchemy.orm import Session
from common.utils.auth import create_access_token
import secrets
import hmac
from google.auth.transport import requests
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from fastapi import HTTPException, status

# Set up logger
logger = logging.getLogger(__name__)

# Google OAuth configuration
GOOGLE_CLIENT_ID = settings.google_client_id
GOOGLE_CLIENT_SECRET = settings.google_client_secret
GOOGLE_REDIRECT_URI = settings.google_redirect_uri

def generate_state() -> str:
    """Generate a random state parameter for OAuth security"""
    return secrets.token_urlsafe(32)

def verify_state(state: str, stored_state: str) -> bool:
    """Verify the OAuth state parameter"""
    return hmac.compare_digest(state or "", stored_state or "")

def get_google_auth_url(state: str) -> str:
    """Generate Google OAuth authorization URL using google-auth-oauthlib"""
    # Validate required OAuth configuration
    if not GOOGLE_CLIENT_ID or not GOOGLE_REDIRECT_URI:
        raise ValueError("Google OAuth is not configured. Missing GOOGLE_CLIENT_ID or GOOGLE_REDIRECT_URI")
    
    # Create OAuth flow using Google's library
    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [GOOGLE_REDIRECT_URI]
        }
    }
    
    flow = Flow.from_client_config(
        client_config,
        scopes=["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"],
        state=state
    )
    flow.redirect_uri = GOOGLE_REDIRECT_URI
    
    return flow.authorization_url(
        access_type="offline",
        prompt="select_account"
    )[0]

def exchange_code_for_token(code: str, state: str) -> Optional[Dict[str, Any]]:
    """Exchange authorization code for access token and id_token using google-auth-oauthlib"""
    
    logger.info(f"🔄 Attempting to exchange authorization code: {code[:10]}..." if code else "No code provided")
    
    # Validate OAuth configuration
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET or not GOOGLE_REDIRECT_URI:
        logger.error("Google OAuth configuration is incomplete")
        logger.error(f"CLIENT_ID: {'SET' if GOOGLE_CLIENT_ID else 'NOT SET'}")
        logger.error(f"CLIENT_SECRET: {'SET' if GOOGLE_CLIENT_SECRET else 'NOT SET'}")
        logger.error(f"REDIRECT_URI: {'SET' if GOOGLE_REDIRECT_URI else 'NOT SET'}")
        return None
    
    try:
        # Create OAuth flow using Google's library
        client_config = {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [GOOGLE_REDIRECT_URI]
            }
        }
        
        flow = Flow.from_client_config(
            client_config,
            scopes=["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"],
            state=state
        )
        flow.redirect_uri = GOOGLE_REDIRECT_URI
        
        # Exchange the authorization code for tokens
        flow.fetch_token(code=code)
        
        # Get the credentials
        credentials = flow.credentials
        
        # Return token information
        return {
            "access_token": credentials.token,
            "id_token": credentials.id_token,
            "refresh_token": credentials.refresh_token,
            "token_type": "Bearer",
            "expires_in": 3600  # Default expiration
        }
        
    except Exception as e:
        logger.error(f"Error exchanging code for token: {e}")
        return None

def verify_google_id_token(id_token_str: str) -> Dict[str, Any]:
    """
    Verify Google ID token and return validated claims
    
    Args:
        id_token_str: The ID token string from Google
        
    Returns:
        Dict containing validated claims
        
    Raises:
        HTTPException: If token verification fails
    """
    try:
        # Verify the ID token
        idinfo = id_token.verify_oauth2_token(
            id_token_str, 
            requests.Request(), 
            GOOGLE_CLIENT_ID
        )
        
        # Validate issuer
        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token issuer"
            )
        
        # Validate audience
        if idinfo['aud'] != GOOGLE_CLIENT_ID:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token audience"
            )
        
        # Check email verification
        if not idinfo.get('email_verified', False):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email not verified"
            )
        
        # Return validated claims
        return {
            "email": idinfo.get("email"),
            "name": idinfo.get("name"),
            "picture": idinfo.get("picture"),
            "sub": idinfo.get("sub"),
            "id": idinfo.get("sub"),
            "email_verified": idinfo.get("email_verified", False)
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ID token: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Token verification failed: {str(e)}"
        )

def get_google_user_info_from_id_token(id_token_str: str) -> Optional[Dict[str, Any]]:
    """Get user information from Google ID token (preferred method)"""
    try:
        # Verify and decode the ID token
        claims = verify_google_id_token(id_token_str)
        return claims
    except Exception as e:
        logger.error(f"Error getting user info from ID token: {e}")
        return None

def find_existing_user_by_email(db: Session, email: str) -> Optional[User]:
    """Find existing user by email"""
    return db.query(User).filter(User.email == email).first()

def find_existing_user_by_google_id(db: Session, google_id: str) -> Optional[User]:
    """Find existing user by Google ID"""
    return db.query(User).filter(User.google_id == google_id).first()

def find_oauth_user_by_original_email(db: Session, original_email: str) -> Optional[User]:
    """Find OAuth user by their original email (before +google suffix)"""
    # First try exact match
    user = db.query(User).filter(User.email == original_email).first()
    if user:
        return user
    
    # If not found, try to find OAuth user with modified email
    # Split email robustly with rsplit to handle multiple @ symbols
    email_parts = original_email.rsplit('@', 1)
    if len(email_parts) != 2:
        return None
    
    base_email, domain = email_parts
    
    # Escape special regex characters in base_email and domain
    import re
    escaped_base = re.escape(base_email)
    escaped_domain = re.escape(domain)
    
    # Create precise regex pattern: base_email+google followed by one or more digits
    pattern = f"^{escaped_base}\\+google\\d+@{escaped_domain}$"
    
    # Use dialect-aware regex matching
    from sqlalchemy import text
    from database.connection import engine
    
    # Detect database dialect and use appropriate regex operator
    dialect_name = engine.dialect.name
    if dialect_name == 'postgresql':
        # PostgreSQL uses ~ operator
        return db.query(User).filter(
            User.email.op('~')(pattern),
            User.provider == "google"
        ).first()
    elif dialect_name in ['mysql', 'mariadb']:
        # MySQL uses REGEXP operator
        return db.query(User).filter(
            User.email.op('REGEXP')(pattern),
            User.provider == "google"
        ).first()
    elif dialect_name == 'sqlite':
        # SQLite uses REGEXP operator (if extension is loaded) or fallback to LIKE
        try:
            return db.query(User).filter(
                User.email.op('REGEXP')(pattern),
                User.provider == "google"
            ).first()
        except Exception:
            # Fallback to LIKE-based pattern matching for SQLite
            like_pattern = f"{base_email}+google%@{domain}"
            return db.query(User).filter(
                User.email.like(like_pattern),
                User.provider == "google"
            ).first()
    else:
        # Fallback to LIKE-based pattern matching for unsupported dialects
        like_pattern = f"{base_email}+google%@{domain}"
        return db.query(User).filter(
            User.email.like(like_pattern),
            User.provider == "google"
        ).first()

def create_oauth_user(db: Session, google_data: Dict[str, Any], force_create: bool = False, role: str = "student") -> User:
    """Create a new user from Google OAuth data with role-based ID"""
    from common.utils.id_generator import generate_unique_user_id
    
    # Generate username from email
    username = google_data["email"].split("@")[0]
    
    # Ensure username is unique
    original_username = username
    counter = 1
    while db.query(User).filter(User.username == username).first():
        username = f"{original_username}{counter}"
        counter += 1
    
    # Check if user already exists with this Google ID
    google_id_value = google_data.get("sub") or google_data.get("id")
    existing_user = db.query(User).filter(User.google_id == google_id_value).first()
    if existing_user:
        # User already exists, update their information and role
        existing_user.full_name = google_data.get("name", existing_user.full_name)
        existing_user.avatar_url = google_data.get("picture", existing_user.avatar_url)
        existing_user.provider = "google"
        existing_user.is_verified = True
        existing_user.role = role  # Update the role with the selected role
        db.commit()
        db.refresh(existing_user)
        return existing_user
    
    # Check if user exists with this email (only if not forcing creation)
    if not force_create:
        existing_email_user = db.query(User).filter(User.email == google_data["email"]).first()
        if existing_email_user:
            # Link the OAuth provider to the existing user
            return link_google_to_existing_user(db, existing_email_user, google_data)
    
    # Create new user with original email (or modified email if forcing creation)
    user_email = google_data["email"]
    if force_create:
        # For separate accounts, modify the email to avoid conflicts
        # Extract the local part and domain
        local_part, domain = user_email.split('@', 1)
        # Add a suffix to make it unique
        user_email = f"{local_part}+google@{domain}"
        
        # Ensure the modified email is also unique
        counter = 1
        while db.query(User).filter(User.email == user_email).first():
            user_email = f"{local_part}+google{counter}@{domain}"
            counter += 1
    
    # Generate role-based user ID
    try:
        user_id = generate_unique_user_id(db, role)
    except Exception as e:
        raise ValueError(f"Failed to generate user ID: {str(e)}")
    
    user = User(
        user_id=user_id,
        email=user_email,
        full_name=google_data.get("name", ""),
        username=username,
        password_hash=None,  # OAuth users don't have passwords
        avatar_url=google_data.get("picture"),
        google_id=google_data.get("sub") or google_data.get("id"),
        provider="google",
        role=role,  # Set the role
        is_verified=True,  # Google accounts are considered verified
    )
    
    print(f"DEBUG: Creating user with email: {user_email}, role: {role}, google_id: {user.google_id}")
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f"DEBUG: User created successfully with ID: {user.id}")
    return user

def link_google_to_existing_user(db: Session, user: User, google_data: Dict[str, Any]) -> User:
    """Link Google OAuth to existing user account"""
    user.google_id = google_data.get("sub") or google_data.get("id")
    user.provider = "google"  # Update provider to google
    
    # Update profile data from Google if not already set
    if not user.avatar_url and google_data.get("picture"):
        user.avatar_url = google_data["picture"]
    
    db.commit()
    db.refresh(user)
    return user

def create_oauth_access_token(user: User) -> str:
    """Create access token for OAuth user"""
    return create_access_token(data={"sub": str(user.id)})

def create_user_login_response(user: User):
    """Create login response for OAuth user (HttpOnly cookie only)"""
    from database.schemas import UserLoginResponse, UserResponse
    
    return UserLoginResponse(
        access_token="",  # Empty token - authentication via HttpOnly cookie only
        token_type="cookie",
        user=UserResponse(
            id=user.id,
            user_id=user.user_id,
            email=user.email,
            full_name=user.full_name,
            username=user.username,
            bio=user.bio,
            avatar_url=user.avatar_url,
            role=user.role,
            published_scenarios=user.published_scenarios,
            total_simulations=user.total_simulations,
            reputation_score=user.reputation_score,
            profile_public=user.profile_public,
            allow_contact=user.allow_contact,
            is_active=user.is_active,
            is_verified=user.is_verified,
            provider=user.provider,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
    )
