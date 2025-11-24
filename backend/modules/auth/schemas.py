"""
Authentication request/response schemas
"""
from pydantic import BaseModel, model_validator
from typing import Optional, Literal
from database.schemas import UserResponse

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

class UserLogin(BaseModel):
    email: str
    password: str

class UserLoginResponse(BaseModel):
    access_token: str
    token_type: str = "cookie"  # HttpOnly cookie authentication
    user: UserResponse

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class PasswordResetRequest(BaseModel):
    email: str
    confirm_email: str
    new_password: str

    @model_validator(mode="after")
    def validate_emails(self):
        if self.email.strip().lower() != self.confirm_email.strip().lower():
            raise ValueError("Emails must match")
        if len(self.new_password) < 6:
            raise ValueError("New password must be at least 6 characters long")
        return self

class PasswordReset(BaseModel):
    email: str

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

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

