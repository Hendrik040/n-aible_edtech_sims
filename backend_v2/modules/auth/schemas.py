"""
Authentication request/response schemas
"""
from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, Literal
from common.db.schemas import UserResponse

# --- USER AUTHENTICATION SCHEMAS ---
class UserRegister(BaseModel):
    email: str
    full_name: str
    username: str
    password: str
    role: Literal["student", "professor"]  # Required role selection
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    profile_public: bool = True
    allow_contact: bool = True

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

class UserLogin(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

class UserLoginResponse(BaseModel):
    access_token: str
    token_type: str = "cookie"  # HttpOnly cookie authentication
    user: UserResponse

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    username: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    profile_public: Optional[bool] = None
    allow_contact: Optional[bool] = None

class PasswordReset(BaseModel):
    """Request a password reset email for the given address."""
    email: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        value = (v or "").strip().lower()
        if not value or "@" not in value:
            raise ValueError("A valid email address is required")
        return value

class PasswordResetConfirm(BaseModel):
    """Confirm a password reset using a token delivered via email."""
    token: str
    new_password: str

    @field_validator("token")
    @classmethod
    def validate_token(cls, v: str) -> str:
        value = (v or "").strip()
        if not value:
            raise ValueError("Reset token is required")
        return value

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if not v or len(v) < 6:
            raise ValueError("New password must be at least 6 characters long")
        return v


class PasswordResetResponse(BaseModel):
    """Generic response for password reset endpoints."""
    message: str

# OAuth schemas
class GoogleOAuthRequest(BaseModel):
    code: str
    state: Optional[str] = None

class OAuthUserData(BaseModel):
    google_id: str
    email: str
    full_name: str
    avatar_url: Optional[str] = None

class AccountLinkingRequest(BaseModel):
    action: Literal["link", "create_separate"]
    existing_user_id: Optional[int] = None  # Required when action == "link"
    state: str  # OAuth state for verification - server will fetch google_data from this
    role: Optional[Literal["student", "professor"]] = None  # Required when action == "create_separate"
    
    @model_validator(mode='after')
    def validate_required_fields(self):
        if self.action == "link" and self.existing_user_id is None:
            raise ValueError("existing_user_id is required when action == 'link'")
        
        if self.action == "link" and self.existing_user_id is not None and self.existing_user_id <= 0:
            raise ValueError("existing_user_id must be a positive integer")
        
        if self.action == "create_separate" and self.role is None:
            raise ValueError("role is required when action == 'create_separate'")
        
        return self

class RoleSelectionRequest(BaseModel):
    role: Literal["student", "professor"]
    state: str  # OAuth state for verification

