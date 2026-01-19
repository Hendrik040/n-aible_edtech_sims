# Password Reset Implementation Plan

**Created:** 2025-12-26  
**Status:** Planning  
**Priority:** High (Security)  
**Estimated Effort:** 3-4 hours  

---

## Problem Statement

The current password reset implementation is **INSECURE**:

```
Current Flow (DANGEROUS):
POST /forgot-password { email, confirm_email, new_password }
→ Directly changes password if email exists
→ No email verification
→ Anyone who knows an email can reset that user's password!
```

This must be replaced with a secure, token-based flow.

---

## Current State Analysis

### Backend (`modules/auth/router.py`)

```python
@router.post("/forgot-password")
async def forgot_password(request: PasswordResetRequest, db: Session = Depends(get_db)):
    # INSECURE: Directly updates password without verification
    user.password_hash = await auth_service.get_password_hash_async(request.new_password)
    db.commit()
```

### Frontend (`app/forgot-password/page.tsx`)

Current form collects:
- Email
- Confirm Email  
- New Password

Then directly calls the backend to change the password.

### Schema (`modules/auth/schemas.py`)

```python
class PasswordResetRequest(BaseModel):
    email: str
    confirm_email: str
    new_password: str  # ← Password sent in initial request (INSECURE)
```

---

## Secure Password Reset Flow

### New Flow (3 Steps)

```
Step 1: Request Reset
────────────────────
User: Enters email
Frontend: POST /forgot-password { email }
Backend: 
  1. Find user by email
  2. Generate secure token (32 bytes)
  3. Store SHA-256 hash of token in database
  4. Send email with reset link containing raw token
  5. Return success (always, to prevent email enumeration)

Step 2: Validate Token (Optional - for UX)
──────────────────────────────────────────
User: Clicks link in email → /reset-password?token=xxx
Frontend: GET /reset-password/validate?token=xxx
Backend: Check if token exists and not expired
Response: { valid: true, email: "user@..." } or { valid: false }

Step 3: Complete Reset
──────────────────────
User: Enters new password
Frontend: POST /reset-password { token, new_password }
Backend:
  1. Find token by hash
  2. Verify not expired (1 hour)
  3. Verify not already used
  4. Update user's password
  5. Mark token as used
  6. Send confirmation email (optional)
  7. Return success
```

---

## Implementation Plan

### Phase 1: Database Model (Est. 30 min)

#### 1.1 Create PasswordResetToken Model

**File:** `backend/common/db/models/auth/password_reset_token.py`

```python
"""Password reset token model."""
from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from common.db.connection import Base


class PasswordResetToken(Base):
    """
    Stores password reset tokens.
    
    Security notes:
    - Only the SHA-256 hash of the token is stored (not the raw token)
    - Tokens expire after 1 hour
    - Tokens are single-use (marked as used after password change)
    """
    __tablename__ = "password_reset_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Store SHA-256 hash of token, not the raw token
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    
    # Expiration and usage tracking
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)  # NULL until used
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String(45), nullable=True)  # IPv6 max length
    user_agent = Column(String(500), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="password_reset_tokens")
    
    @property
    def is_expired(self) -> bool:
        """Check if token has expired."""
        return datetime.utcnow() > self.expires_at
    
    @property
    def is_used(self) -> bool:
        """Check if token has been used."""
        return self.used_at is not None
    
    @property
    def is_valid(self) -> bool:
        """Check if token is valid (not expired and not used)."""
        return not self.is_expired and not self.is_used
```

#### 1.2 Update User Model

**File:** `backend/common/db/models/user.py`

Add relationship:

```python
# In User class
password_reset_tokens = relationship(
    "PasswordResetToken", 
    back_populates="user",
    cascade="all, delete-orphan"
)
```

#### 1.3 Create Migration

```bash
uv run alembic revision --autogenerate -m "add_password_reset_tokens_table"
uv run alembic upgrade head
```

---

### Phase 2: Backend Service & Endpoints (Est. 1.5 hours)

#### 2.1 Create Password Reset Service

**File:** `backend/modules/auth/password_reset_service.py`

```python
"""Password reset service."""
import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from common.db.models import User, PasswordResetToken
from common.security.passwords import hash_password_async

logger = logging.getLogger(__name__)

# Configuration
TOKEN_EXPIRY_HOURS = 1
TOKEN_BYTES = 32  # 256 bits
MAX_REQUESTS_PER_HOUR = 3  # Rate limiting


class PasswordResetService:
    """Service for handling password reset operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def generate_token(self) -> Tuple[str, str]:
        """
        Generate a secure reset token.
        
        Returns:
            Tuple of (raw_token, token_hash)
            - raw_token: Send this in the email link
            - token_hash: Store this in the database
        """
        raw_token = secrets.token_urlsafe(TOKEN_BYTES)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        return raw_token, token_hash
    
    def create_reset_token(
        self, 
        user: User,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Optional[str]:
        """
        Create a password reset token for a user.
        
        Args:
            user: The user requesting password reset
            ip_address: Client IP address (for audit)
            user_agent: Client user agent (for audit)
            
        Returns:
            The raw token to send in email, or None if rate limited
        """
        # Rate limiting: Check recent requests
        recent_requests = self.db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.created_at > datetime.utcnow() - timedelta(hours=1)
        ).count()
        
        if recent_requests >= MAX_REQUESTS_PER_HOUR:
            logger.warning(f"Rate limit exceeded for password reset: user_id={user.id}")
            return None
        
        # Invalidate any existing unused tokens for this user
        self.db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None)
        ).delete()
        
        # Generate new token
        raw_token, token_hash = self.generate_token()
        
        # Create token record
        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS),
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        self.db.add(reset_token)
        self.db.commit()
        
        logger.info(f"Password reset token created for user_id={user.id}")
        return raw_token
    
    def validate_token(self, raw_token: str) -> Optional[PasswordResetToken]:
        """
        Validate a password reset token.
        
        Args:
            raw_token: The raw token from the email link
            
        Returns:
            The PasswordResetToken if valid, None otherwise
        """
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        
        reset_token = self.db.query(PasswordResetToken).filter(
            PasswordResetToken.token_hash == token_hash
        ).first()
        
        if not reset_token:
            logger.warning("Invalid password reset token attempted")
            return None
        
        if not reset_token.is_valid:
            if reset_token.is_expired:
                logger.warning(f"Expired password reset token: user_id={reset_token.user_id}")
            elif reset_token.is_used:
                logger.warning(f"Already used password reset token: user_id={reset_token.user_id}")
            return None
        
        return reset_token
    
    async def reset_password(
        self, 
        raw_token: str, 
        new_password: str
    ) -> Tuple[bool, str]:
        """
        Reset a user's password using a valid token.
        
        Args:
            raw_token: The raw token from the email link
            new_password: The new password
            
        Returns:
            Tuple of (success, message)
        """
        reset_token = self.validate_token(raw_token)
        
        if not reset_token:
            return False, "Invalid or expired reset token"
        
        # Get the user
        user = self.db.query(User).filter(User.id == reset_token.user_id).first()
        if not user:
            return False, "User not found"
        
        # Check if user is OAuth-only
        if user.provider and user.provider != "password" and not user.password_hash:
            return False, "This account uses Google sign-in. Password cannot be reset."
        
        # Update password
        user.password_hash = await hash_password_async(new_password)
        user.updated_at = datetime.utcnow()
        
        # Mark token as used
        reset_token.used_at = datetime.utcnow()
        
        self.db.commit()
        
        logger.info(f"Password reset completed for user_id={user.id}")
        return True, "Password reset successfully"
    
    def cleanup_expired_tokens(self, days_old: int = 7) -> int:
        """
        Clean up expired tokens older than specified days.
        
        Args:
            days_old: Delete tokens older than this many days
            
        Returns:
            Number of tokens deleted
        """
        cutoff = datetime.utcnow() - timedelta(days=days_old)
        
        deleted = self.db.query(PasswordResetToken).filter(
            PasswordResetToken.created_at < cutoff
        ).delete()
        
        self.db.commit()
        logger.info(f"Cleaned up {deleted} expired password reset tokens")
        return deleted
```

#### 2.2 Update Auth Router

**File:** `backend/modules/auth/router.py`

Replace the existing `/forgot-password` endpoint and add new endpoints:

```python
from modules.auth.password_reset_service import PasswordResetService

# New schemas needed
class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    
    @model_validator(mode="after")
    def validate_password(self):
        if len(self.new_password) < 8:
            raise ValueError("Password must be at least 8 characters")
        return self

class ValidateTokenResponse(BaseModel):
    valid: bool
    email: Optional[str] = None
    expires_in_minutes: Optional[int] = None


@router.post("/forgot-password")
async def request_password_reset(
    request: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    req: Request,
    db: Session = Depends(get_db)
):
    """
    Request a password reset email.
    
    Always returns success to prevent email enumeration attacks.
    """
    normalized_email = request.email.strip().lower()
    
    user = db.query(User).filter(func.lower(User.email) == normalized_email).first()
    
    # Always return success (prevent email enumeration)
    if not user:
        logger.info(f"Password reset requested for non-existent email: {normalized_email}")
        return {"message": "If an account exists with this email, you will receive a password reset link."}
    
    # Check if OAuth user without password
    if user.provider and user.provider != "password":
        logger.info(f"Password reset requested for OAuth user: {normalized_email}")
        return {"message": "If an account exists with this email, you will receive a password reset link."}
    
    # Create reset token
    reset_service = PasswordResetService(db)
    raw_token = reset_service.create_reset_token(
        user=user,
        ip_address=req.client.host if req.client else None,
        user_agent=req.headers.get("user-agent")
    )
    
    if raw_token:
        # TODO: Queue email with reset link
        # For now, log the token (REMOVE IN PRODUCTION!)
        reset_link = f"{FRONTEND_URL}/reset-password?token={raw_token}"
        logger.info(f"Password reset link generated: {reset_link}")
        
        # background_tasks.add_task(send_password_reset_email, user.email, reset_link)
    else:
        logger.warning(f"Rate limit hit for password reset: {normalized_email}")
    
    return {"message": "If an account exists with this email, you will receive a password reset link."}


@router.get("/reset-password/validate")
async def validate_reset_token(
    token: str,
    db: Session = Depends(get_db)
):
    """
    Validate a password reset token.
    
    Used by frontend to check if token is valid before showing password form.
    """
    reset_service = PasswordResetService(db)
    reset_token = reset_service.validate_token(token)
    
    if not reset_token:
        return ValidateTokenResponse(valid=False)
    
    # Get user email (masked for privacy)
    user = db.query(User).filter(User.id == reset_token.user_id).first()
    email_parts = user.email.split("@")
    masked_email = f"{email_parts[0][:2]}***@{email_parts[1]}" if user else None
    
    # Calculate time remaining
    expires_in = (reset_token.expires_at - datetime.utcnow()).total_seconds() / 60
    
    return ValidateTokenResponse(
        valid=True,
        email=masked_email,
        expires_in_minutes=int(expires_in)
    )


@router.post("/reset-password")
async def complete_password_reset(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Complete password reset with token and new password.
    """
    reset_service = PasswordResetService(db)
    success, message = await reset_service.reset_password(
        raw_token=request.token,
        new_password=request.new_password
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message
        )
    
    return {"message": message}
```

---

### Phase 3: Frontend Updates (Est. 1 hour)

#### 3.1 Update Forgot Password Page (Step 1)

**File:** `frontend/app/forgot-password/page.tsx`

Simplify to only collect email:

```tsx
"use client"

import { useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { toast } from "sonner"

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("")
  const [loading, setLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    if (!email.trim()) {
      toast.error("Please enter your email address")
      return
    }

    setLoading(true)
    try {
      const response = await fetch("/api/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      })

      // Always show success (backend returns success regardless)
      setSubmitted(true)
      toast.success("Check your email for reset instructions")
    } catch (err) {
      toast.error("Something went wrong. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  if (submitted) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white flex items-center justify-center p-4">
        <div className="w-full max-w-md text-center">
          <div className="mb-6">
            <div className="w-16 h-16 mx-auto bg-green-500/20 rounded-full flex items-center justify-center">
              <svg className="w-8 h-8 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>
          </div>
          <h1 className="text-2xl font-bold mb-2">Check your email</h1>
          <p className="text-gray-400 mb-6">
            If an account exists for <span className="text-white">{email}</span>, 
            you will receive a password reset link shortly.
          </p>
          <p className="text-gray-500 text-sm mb-6">
            Didn't receive an email? Check your spam folder or try again.
          </p>
          <Link href="/login">
            <Button variant="outline" className="w-full">
              Back to Login
            </Button>
          </Link>
        </div>
      </div>
    )
  }

  return (
    // ... existing UI with only email field
  )
}
```

#### 3.2 Create Reset Password Page (Step 2)

**File:** `frontend/app/reset-password/page.tsx` (NEW)

```tsx
"use client"

import { useState, useEffect } from "react"
import { useSearchParams, useRouter } from "next/navigation"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { toast } from "sonner"

export default function ResetPasswordPage() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const token = searchParams.get("token")
  
  const [loading, setLoading] = useState(true)
  const [validating, setValidating] = useState(true)
  const [tokenValid, setTokenValid] = useState(false)
  const [maskedEmail, setMaskedEmail] = useState("")
  const [expiresIn, setExpiresIn] = useState(0)
  
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState("")

  // Validate token on mount
  useEffect(() => {
    if (!token) {
      setValidating(false)
      return
    }

    const validateToken = async () => {
      try {
        const response = await fetch(`/api/auth/reset-password/validate?token=${token}`)
        const data = await response.json()
        
        setTokenValid(data.valid)
        if (data.valid) {
          setMaskedEmail(data.email || "")
          setExpiresIn(data.expires_in_minutes || 0)
        }
      } catch (err) {
        setTokenValid(false)
      } finally {
        setValidating(false)
        setLoading(false)
      }
    }

    validateToken()
  }, [token])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")

    if (password !== confirmPassword) {
      setError("Passwords do not match")
      return
    }

    if (password.length < 8) {
      setError("Password must be at least 8 characters")
      return
    }

    setLoading(true)
    try {
      const response = await fetch("/api/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: password }),
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || "Failed to reset password")
      }

      setSuccess(true)
      toast.success("Password reset successfully!")
      setTimeout(() => router.push("/login"), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reset password")
    } finally {
      setLoading(false)
    }
  }

  // No token provided
  if (!token) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white flex items-center justify-center p-4">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-red-400 mb-4">Invalid Link</h1>
          <p className="text-gray-400 mb-6">No reset token provided.</p>
          <Link href="/forgot-password">
            <Button>Request New Reset Link</Button>
          </Link>
        </div>
      </div>
    )
  }

  // Validating token
  if (validating) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-white mx-auto mb-4"></div>
          <p>Validating reset link...</p>
        </div>
      </div>
    )
  }

  // Invalid/expired token
  if (!tokenValid) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white flex items-center justify-center p-4">
        <div className="text-center">
          <div className="w-16 h-16 mx-auto bg-red-500/20 rounded-full flex items-center justify-center mb-4">
            <svg className="w-8 h-8 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-red-400 mb-2">Link Expired or Invalid</h1>
          <p className="text-gray-400 mb-6">
            This password reset link has expired or is invalid.<br />
            Please request a new one.
          </p>
          <Link href="/forgot-password">
            <Button>Request New Reset Link</Button>
          </Link>
        </div>
      </div>
    )
  }

  // Success state
  if (success) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white flex items-center justify-center p-4">
        <div className="text-center">
          <div className="w-16 h-16 mx-auto bg-green-500/20 rounded-full flex items-center justify-center mb-4">
            <svg className="w-8 h-8 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold mb-2">Password Reset!</h1>
          <p className="text-gray-400 mb-6">
            Your password has been updated successfully.<br />
            Redirecting to login...
          </p>
        </div>
      </div>
    )
  }

  // Password reset form
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 text-white flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <img src="/n-aiblelogo.png" alt="Logo" className="h-16 w-auto mx-auto mb-6" />
          <h1 className="text-3xl font-bold mb-2">Reset Password</h1>
          <p className="text-gray-400">
            Enter a new password for <span className="text-white">{maskedEmail}</span>
          </p>
          {expiresIn > 0 && (
            <p className="text-yellow-400 text-sm mt-2">
              Link expires in {expiresIn} minute{expiresIn !== 1 ? "s" : ""}
            </p>
          )}
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="password">New Password</Label>
            <Input
              id="password"
              type="password"
              placeholder="Enter new password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="bg-gray-900/50 border-gray-700 text-white"
              required
              minLength={8}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="confirmPassword">Confirm Password</Label>
            <Input
              id="confirmPassword"
              type="password"
              placeholder="Confirm new password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="bg-gray-900/50 border-gray-700 text-white"
              required
            />
          </div>

          {error && (
            <div className="bg-red-900/20 border border-red-500/50 rounded-md p-3">
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}

          <Button
            type="submit"
            className="w-full btn-gradient"
            disabled={loading}
          >
            {loading ? "Resetting..." : "Reset Password"}
          </Button>
        </form>
      </div>
    </div>
  )
}
```

#### 3.3 Add API Route Proxies

**File:** `frontend/app/api/auth/forgot-password/route.ts`

```typescript
import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  const body = await request.json()
  
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL}/api/auth/users/forgot-password`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }
  )
  
  const data = await response.json()
  return NextResponse.json(data, { status: response.status })
}
```

**File:** `frontend/app/api/auth/reset-password/route.ts`

```typescript
import { NextRequest, NextResponse } from 'next/server'

export async function POST(request: NextRequest) {
  const body = await request.json()
  
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL}/api/auth/users/reset-password`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }
  )
  
  const data = await response.json()
  return NextResponse.json(data, { status: response.status })
}
```

**File:** `frontend/app/api/auth/reset-password/validate/route.ts`

```typescript
import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  const token = request.nextUrl.searchParams.get('token')
  
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL}/api/auth/users/reset-password/validate?token=${token}`,
    { method: 'GET' }
  )
  
  const data = await response.json()
  return NextResponse.json(data, { status: response.status })
}
```

---

### Phase 4: Email Integration (Est. 30 min)

This depends on Phase 5 of EMAIL_INTEGRATION_PLAN.md. For now, we'll log the reset link.

#### 4.1 Email Template

**File:** `backend/common/services/email_templates.py` (add to existing)

```python
PASSWORD_RESET_TEMPLATE = {
    "subject": "Reset Your Password - n-aible",
    "html": """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
            .container { max-width: 600px; margin: 0 auto; padding: 20px; }
            .header { text-align: center; margin-bottom: 30px; }
            .button { 
                display: inline-block; 
                background: #3b82f6; 
                color: white; 
                padding: 12px 24px; 
                text-decoration: none; 
                border-radius: 6px;
                font-weight: bold;
            }
            .footer { margin-top: 30px; font-size: 12px; color: #666; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Password Reset Request</h1>
            </div>
            
            <p>Hello,</p>
            
            <p>We received a request to reset your password for your n-aible account.</p>
            
            <p>Click the button below to reset your password:</p>
            
            <p style="text-align: center; margin: 30px 0;">
                <a href="{reset_link}" class="button">Reset Password</a>
            </p>
            
            <p>Or copy and paste this link into your browser:</p>
            <p style="word-break: break-all; color: #3b82f6;">{reset_link}</p>
            
            <p><strong>This link will expire in 1 hour.</strong></p>
            
            <p>If you didn't request this password reset, you can safely ignore this email. 
            Your password will remain unchanged.</p>
            
            <div class="footer">
                <p>This is an automated message from n-aible Education Platform.</p>
                <p>If you have questions, please contact support.</p>
            </div>
        </div>
    </body>
    </html>
    """,
    "text": """
    Password Reset Request
    
    Hello,
    
    We received a request to reset your password for your n-aible account.
    
    Click the link below to reset your password:
    {reset_link}
    
    This link will expire in 1 hour.
    
    If you didn't request this password reset, you can safely ignore this email.
    
    - n-aible Education Platform
    """
}
```

---

## Implementation Checklist

### Phase 1: Database
- [ ] Create `PasswordResetToken` model
- [ ] Add relationship to `User` model
- [ ] Create and run migration
- [ ] Export model in `__init__.py`

### Phase 2: Backend
- [ ] Create `PasswordResetService`
- [ ] Add `ForgotPasswordRequest` schema
- [ ] Add `ResetPasswordRequest` schema
- [ ] Add `ValidateTokenResponse` schema
- [ ] Update `POST /forgot-password` endpoint
- [ ] Add `GET /reset-password/validate` endpoint
- [ ] Add `POST /reset-password` endpoint

### Phase 3: Frontend
- [ ] Update `forgot-password/page.tsx` (email only)
- [ ] Create `reset-password/page.tsx` (new page)
- [ ] Add API route proxies
- [ ] Add "Forgot password?" link to login page

### Phase 4: Email (Later)
- [ ] Add email template
- [ ] Integrate with email service when ready

### Phase 5: Testing
- [ ] Test rate limiting (max 3 requests/hour)
- [ ] Test token expiration (1 hour)
- [ ] Test token single-use
- [ ] Test invalid token handling
- [ ] Test OAuth user rejection
- [ ] Test email enumeration protection

---

## Security Considerations

1. **Never reveal if email exists** - Always return same message
2. **Store only token hashes** - Never store raw tokens
3. **Token expiration** - 1 hour max
4. **Single use tokens** - Mark as used after password change
5. **Rate limiting** - Max 3 requests per email per hour
6. **Audit logging** - Log IP and user agent for each request
7. **HTTPS only** - Never send reset links over HTTP
8. **Invalidate old tokens** - When new token created, invalidate old ones

---

## Timeline Estimate

| Phase | Description | Time |
|-------|-------------|------|
| Phase 1 | Database model & migration | 30 min |
| Phase 2 | Backend service & endpoints | 1.5 hours |
| Phase 3 | Frontend pages & API routes | 1 hour |
| Phase 4 | Email integration | 30 min (later) |
| Phase 5 | Testing | 30 min |

**Total: 3-4 hours**

---

## Dependencies

- Email service (Phase 5 from EMAIL_INTEGRATION_PLAN.md) - Optional for MVP
- For MVP: Log reset links to console (development only)

---

## References

- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
- [NIST Password Guidelines](https://pages.nist.gov/800-63-3/sp800-63b.html)

