"""
OAuth provider integrations (Google, etc.)
"""
import os
import logging
import secrets
import hmac
import time
import json
import base64
import asyncio
import re
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet

from sqlalchemy import func, text
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from google.auth.transport import requests

from common.config import get_settings
from common.db.models import User
from common.db.connection import engine
from common.db.schemas import UserResponse
from common.services.cache_service import redis_manager
from common.utils.id_generator import generate_unique_user_id
from modules.auth.schemas import UserLoginResponse

logger = logging.getLogger(__name__)
settings = get_settings()

# Google OAuth configuration
GOOGLE_CLIENT_ID = settings.google_client_id
GOOGLE_CLIENT_SECRET = settings.google_client_secret
GOOGLE_REDIRECT_URI = settings.google_redirect_uri

IS_PRODUCTION = os.getenv('ENVIRONMENT', '').lower() in ['production', 'prod']


class OAuthStateStore:
    """Persistent OAuth state storage using Redis"""
    
    def __init__(self):
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
                    # Go up 3 levels from backend/modules/auth/provider.py -> backend/
                    dev_key_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.oauth_encryption_key')
                    key = self._get_or_create_dev_key(dev_key_file)
                    logger.warning("No OAUTH_ENCRYPTION_KEY found, using development key from file. Set OAUTH_ENCRYPTION_KEY in production!")
                    self.cipher = Fernet(key)
                except Exception as e:
                    logger.error(f"Failed to initialize development encryption: {e}")
                    self.cipher = None
        else:
            try:
                self.cipher = Fernet(encryption_key.encode('utf-8'))
            except Exception as e:
                logger.error(f"Invalid OAUTH_ENCRYPTION_KEY: {e}. OAuth state encryption disabled.")
                self.cipher = None
    
    def _get_or_create_dev_key(self, key_file_path: str) -> bytes:
        """Get existing dev key or create and persist a new one"""
        try:
            if os.path.exists(key_file_path):
                with open(key_file_path, 'rb') as f:
                    key = f.read()
                Fernet(key)  # Validate
                return key
        except Exception as e:
            logger.warning(f"Invalid or corrupted dev key file, generating new one: {e}")
        
        key = Fernet.generate_key()
        try:
            with open(key_file_path, 'wb') as f:
                f.write(key)
            os.chmod(key_file_path, 0o600)
        except Exception as e:
            logger.error(f"Failed to persist dev encryption key: {e}")
        
        return key
    
    def set_state(self, state: str, data: Dict[str, Any], ttl: int = 600) -> bool:
        """Store OAuth state with TTL (default 10 minutes)"""
        try:
            data['created_at'] = time.time()
            
            if self.cipher:
                try:
                    json_payload = json.dumps(data)
                    encrypted_payload = self.cipher.encrypt(json_payload.encode())
                    encrypted_data = base64.b64encode(encrypted_payload).decode('utf-8')
                except Exception as e:
                    logger.error(f"Failed to encrypt state data: {e}")
                    return False
            else:
                encrypted_data = json.dumps(data)
            
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
            
            if self.cipher:
                try:
                    encrypted_payload = base64.b64decode(encrypted_data)
                    decrypted_payload = self.cipher.decrypt(encrypted_payload)
                    return json.loads(decrypted_payload.decode('utf-8'))
                except Exception as e:
                    logger.error(f"Failed to decrypt state data: {e}")
                    return None
            else:
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


class GoogleOAuthProvider:
    """Google OAuth provider implementation"""
    
    def __init__(self):
        self.state_store = OAuthStateStore()
        # Global cache to track used authorization codes
        self.used_authorization_codes = set()
        self.cleanup_task = None
    
    def generate_state(self) -> str:
        """Generate a random state parameter for OAuth security"""
        return secrets.token_urlsafe(32)
    
    def verify_state(self, state: str, stored_state: str) -> bool:
        """Verify the OAuth state parameter"""
        return hmac.compare_digest(state or "", stored_state or "")
    
    def get_auth_url(self, state: str) -> str:
        """Generate Google OAuth authorization URL"""
        if not GOOGLE_CLIENT_ID or not GOOGLE_REDIRECT_URI:
            raise ValueError("Google OAuth is not configured. Missing GOOGLE_CLIENT_ID or GOOGLE_REDIRECT_URI")
        
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
    
    def exchange_code_for_token(self, code: str, state: str) -> Optional[Dict[str, Any]]:
        """Exchange authorization code for access token and id_token"""
        logger.info(f"🔄 Attempting to exchange authorization code: {code[:10]}..." if code else "No code provided")
        
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET or not GOOGLE_REDIRECT_URI:
            logger.error("Google OAuth configuration is incomplete")
            return None
        
        try:
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
            
            flow.fetch_token(code=code)
            credentials = flow.credentials
            
            return {
                "access_token": credentials.token,
                "id_token": credentials.id_token,
                "refresh_token": credentials.refresh_token,
                "token_type": "Bearer",
                "expires_in": 3600
            }
        except Exception as e:
            logger.error(f"Error exchanging code for token: {e}")
            return None
    
    def verify_id_token(self, id_token_str: str) -> Dict[str, Any]:
        """Verify Google ID token and return validated claims"""
        try:
            idinfo = id_token.verify_oauth2_token(
                id_token_str, 
                requests.Request(), 
                GOOGLE_CLIENT_ID
            )
            
            if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid token issuer"
                )
            
            if idinfo['aud'] != GOOGLE_CLIENT_ID:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid token audience"
                )
            
            if not idinfo.get('email_verified', False):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email not verified"
                )
            
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
    
    def get_user_info_from_id_token(self, id_token_str: str) -> Optional[Dict[str, Any]]:
        """Get user information from Google ID token"""
        try:
            return self.verify_id_token(id_token_str)
        except Exception as e:
            logger.error(f"Error getting user info from ID token: {e}")
            return None
    
    def find_existing_user_by_email(self, db: Session, email: str) -> Optional[User]:
        """Find existing user by email (case-insensitive)"""
        return db.query(User).filter(func.lower(User.email) == email.lower()).first()
    
    def find_existing_user_by_google_id(self, db: Session, google_id: str) -> Optional[User]:
        """Find existing user by Google ID"""
        return db.query(User).filter(User.google_id == google_id).first()
    
    def find_oauth_user_by_original_email(self, db: Session, original_email: str) -> Optional[User]:
        """Find OAuth user by their original email (before +google suffix)"""
        user = db.query(User).filter(func.lower(User.email) == original_email.lower()).first()
        if user:
            return user
        
        email_parts = original_email.rsplit('@', 1)
        if len(email_parts) != 2:
            return None
        
        base_email, domain = email_parts
        
        escaped_base = re.escape(base_email)
        escaped_domain = re.escape(domain)
        pattern = f"^{escaped_base}\\+google\\d+@{escaped_domain}$"
        
        dialect_name = engine.dialect.name
        if dialect_name == 'postgresql':
            return db.query(User).filter(
                User.email.op('~')(pattern),
                User.provider == "google"
            ).first()
        elif dialect_name in ['mysql', 'mariadb']:
            return db.query(User).filter(
                User.email.op('REGEXP')(pattern),
                User.provider == "google"
            ).first()
        elif dialect_name == 'sqlite':
            try:
                return db.query(User).filter(
                    User.email.op('REGEXP')(pattern),
                    User.provider == "google"
                ).first()
            except Exception:
                like_pattern = f"{base_email}+google%@{domain}"
                return db.query(User).filter(
                    User.email.like(like_pattern),
                    User.provider == "google"
                ).first()
        else:
            like_pattern = f"{base_email}+google%@{domain}"
            return db.query(User).filter(
                User.email.like(like_pattern),
                User.provider == "google"
            ).first()
    
    def create_oauth_user(self, db: Session, google_data: Dict[str, Any], force_create: bool = False, role: str = "student") -> User:
        """Create a new user from Google OAuth data with role-based ID"""
        
        username = google_data["email"].split("@")[0]
        original_username = username
        counter = 1
        while db.query(User).filter(User.username == username).first():
            username = f"{original_username}{counter}"
            counter += 1
        
        google_id_value = google_data.get("sub") or google_data.get("id")
        existing_user = db.query(User).filter(User.google_id == google_id_value).first()
        if existing_user:
            existing_user.full_name = google_data.get("name", existing_user.full_name)
            existing_user.avatar_url = google_data.get("picture", existing_user.avatar_url)
            existing_user.provider = "google"
            existing_user.is_verified = True
            existing_user.role = role
            db.commit()
            db.refresh(existing_user)
            return existing_user
        
        if not force_create:
            existing_email_user = db.query(User).filter(func.lower(User.email) == google_data["email"].lower()).first()
            if existing_email_user:
                return self.link_google_to_existing_user(db, existing_email_user, google_data)
        
        user_email = google_data["email"]
        if force_create:
            local_part, domain = user_email.split('@', 1)
            user_email = f"{local_part}+google@{domain}"
            counter = 1
            while db.query(User).filter(func.lower(User.email) == user_email.lower()).first():
                user_email = f"{local_part}+google{counter}@{domain}"
                counter += 1
        
        try:
            user_id = generate_unique_user_id(db, role)
        except Exception as e:
            raise ValueError(f"Failed to generate user ID: {str(e)}")
        
        user = User(
            user_id=user_id,
            email=user_email,
            full_name=google_data.get("name", ""),
            username=username,
            password_hash=None,
            avatar_url=google_data.get("picture"),
            google_id=google_data.get("sub") or google_data.get("id"),
            provider="google",
            role=role,
            is_verified=True,
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    
    def link_google_to_existing_user(self, db: Session, user: User, google_data: Dict[str, Any]) -> User:
        """Link Google OAuth to existing user account"""
        user.google_id = google_data.get("sub") or google_data.get("id")
        user.provider = "google"
        
        if not user.avatar_url and google_data.get("picture"):
            user.avatar_url = google_data["picture"]
        
        db.commit()
        db.refresh(user)
        return user
    
    def create_user_login_response(self, user: User):
        """Create login response for OAuth user"""
        return UserLoginResponse(
            access_token="",
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
                published_simulations=user.published_simulations,
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
    
    async def periodic_cleanup(self):
        """Periodic cleanup task that runs every 5 minutes"""
        while True:
            try:
                await asyncio.sleep(300)  # 5 minutes
                if len(self.used_authorization_codes) > 1000:
                    self.used_authorization_codes = set(list(self.used_authorization_codes)[-500:])
                    logger.info("Cleaned up old authorization codes")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Periodic cleanup failed: {e}")


# Export singleton instance
google_oauth_provider = GoogleOAuthProvider()
