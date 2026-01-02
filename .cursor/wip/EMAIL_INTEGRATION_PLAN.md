# Email Integration Plan

**Created:** 2025-12-26  
**Status:** Planning  
**Priority:** High  
**Estimated Effort:** 6-8 hours  

---

## Overview

This document outlines a comprehensive plan to implement email functionality that serves three primary use cases:

1. **Notification Emails** - Cohort invitations, grade notifications, assignment reminders
2. **Password Reset** - Secure token-based password reset flow
3. **Google OAuth Enhancement** - Account linking and verification emails

Since n-aible runs on Google Cloud, we'll evaluate Google-native options alongside third-party services.

---

## Current State Analysis

### What Exists Now

| Component | Status | Notes |
|-----------|--------|-------|
| `env_template.txt` | ✅ Has SMTP config | `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `FROM_EMAIL` |
| `common/config.py` | ❌ Missing email settings | No email config in Settings class |
| Password Reset | ⚠️ Insecure | `/forgot-password` directly changes password without email verification |
| Google OAuth | ✅ Working | Full implementation in `modules/auth/provider.py` |
| Email Queue | ❌ Missing | No `EmailQueue` model or table |
| Notification Service | ✅ Ready | Phase 1-4 complete, ready for email integration |

### Previous Version Reference

The `prev/backend/services/email_service.py` had:
- SMTP-based sending
- HTML email templates
- Email queue with retry logic
- Templates: `cohort_invitation`, `invitation_accepted`, `invitation_declined`, `assignment_due`, `grade_posted`

---

## Email Provider Options

### Option 1: Gmail SMTP (Current in env_template)

**Pros:**
- Already configured in `env_template.txt`
- Free for up to 500 emails/day
- Works with Google Workspace accounts
- No additional vendor

**Cons:**
- Requires "App Password" (2FA must be enabled)
- Rate limits (500/day personal, 2000/day Workspace)
- Not designed for transactional email
- IP reputation issues possible
- Google may block "suspicious" sending patterns

**Best for:** Development/testing, very low volume

---

### Option 2: SendGrid ⭐ RECOMMENDED

**Pros:**
- Industry standard for transactional email
- 100 emails/day free forever
- Excellent deliverability
- Python SDK: `sendgrid`
- Detailed analytics and logging
- Railway has native integration
- Works seamlessly with Google Cloud

**Cons:**
- Free tier limited to 100/day
- Paid plans start at $19.95/month (50K emails)

**Pricing:**
| Plan | Emails/Month | Cost |
|------|--------------|------|
| Free | 100/day | $0 |
| Essentials | 50,000 | $19.95/month |
| Pro | 100,000 | $89.95/month |

**Best for:** Production use, scalability

---

### Option 3: Resend (Modern Alternative)

**Pros:**
- Developer-first API
- Simple Python SDK: `resend`
- 3,000 emails/month free
- Great documentation
- React Email templates support

**Cons:**
- Newer company (less track record)
- Smaller ecosystem than SendGrid

**Pricing:**
| Plan | Emails/Month | Cost |
|------|--------------|------|
| Free | 3,000 | $0 |
| Pro | 50,000 | $20/month |

**Best for:** Modern apps, developer experience

---

### Option 4: Google Cloud Email Options

#### 4a. Gmail API (OAuth-based)
- Requires OAuth consent for each sending account
- Complex setup
- Best for: Sending AS a specific user (not transactional)

#### 4b. Google Workspace + SMTP Relay
- Requires Google Workspace subscription
- Better reputation than personal Gmail
- Up to 10,000 emails/day

**Best for:** Enterprise Google Workspace customers

---

## Recommendation

For n-aible, I recommend a **hybrid approach**:

| Environment | Provider | Reason |
|-------------|----------|--------|
| Development | Gmail SMTP | Free, simple, already configured |
| Production | SendGrid | Reliable, scalable, Railway native |

This allows zero cost during development while ensuring deliverability in production.

---

## Implementation Plan

### Phase 5A: Email Infrastructure (Est. 2 hours)

#### Step 5A.1: Add Email Settings to Config

Add to `common/config.py`:

```python
# Email Configuration
smtp_server: str = "smtp.gmail.com"
smtp_port: int = 587
smtp_username: Optional[str] = None
smtp_password: Optional[str] = None
from_email: str = "noreply@n-aible.com"
from_name: str = "n-aible Education Platform"

# SendGrid (for production)
sendgrid_api_key: Optional[str] = None

# Email provider selection
email_provider: str = "smtp"  # "smtp" | "sendgrid" | "resend"
```

#### Step 5A.2: Create Email Service Module

Create new module: `backend/common/services/email_service.py`

```
common/services/
├── __init__.py
├── cache_service.py (existing)
├── email_service.py (NEW)
└── storage_service.py (existing)
```

Core components:
- `EmailProvider` abstract base class
- `SMTPProvider` - Gmail/standard SMTP
- `SendGridProvider` - SendGrid API
- `EmailService` - Main service with provider abstraction
- `EmailTemplate` - Template rendering

#### Step 5A.3: Create Email Queue Model

Create migration for `email_queue` table:

```python
class EmailQueue(Base):
    __tablename__ = "email_queue"
    
    id = Column(Integer, primary_key=True)
    to_email = Column(String(255), nullable=False, index=True)
    subject = Column(String(500), nullable=False)
    body_html = Column(Text, nullable=False)
    body_text = Column(Text)  # Plain text fallback
    email_type = Column(String(50), nullable=False, index=True)
    status = Column(String(20), default="pending", index=True)
    # pending | sent | failed | cancelled
    
    # Retry handling
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    error_message = Column(Text)
    
    # Scheduling
    scheduled_at = Column(DateTime, default=func.now())
    sent_at = Column(DateTime)
    
    # Tracking
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    # Optional reference to notification
    notification_id = Column(Integer, ForeignKey("notifications.id"))
```

---

### Phase 5B: Email Templates (Est. 1 hour)

#### Step 5B.1: Create Template System

Create `common/services/email_templates.py`:

```python
from enum import Enum
from typing import Dict, Any

class EmailTemplateType(str, Enum):
    # Authentication
    PASSWORD_RESET = "password_reset"
    EMAIL_VERIFICATION = "email_verification"
    ACCOUNT_LINKED = "account_linked"
    
    # Notifications (mirror notification types)
    COHORT_INVITATION = "cohort_invitation"
    INVITATION_ACCEPTED = "invitation_accepted"
    INVITATION_DECLINED = "invitation_declined"
    ASSIGNMENT_DUE = "assignment_due"
    ASSIGNMENT_OVERDUE = "assignment_overdue"
    GRADE_POSTED = "grade_posted"
    SIMULATION_ASSIGNED = "simulation_assigned"

EMAIL_TEMPLATES: Dict[str, Dict[str, str]] = {
    "password_reset": {
        "subject": "Reset Your Password - n-aible",
        "html": """...""",
        "text": """..."""
    },
    # ... more templates
}
```

#### Step 5B.2: Base HTML Template

Create a responsive HTML email base template with:
- n-aible branding
- Mobile-responsive design
- Dark mode support
- Unsubscribe link (for marketing emails)
- Footer with company info

---

### Phase 5C: Password Reset Flow (Est. 2 hours)

#### Current Flow (INSECURE):
```
POST /users/forgot-password { email, new_password }
→ Directly updates password if email exists
```

#### New Flow (SECURE):

**Step 1: Request Reset**
```
POST /users/forgot-password { email }
→ Generates token, queues email, returns success
```

**Step 2: Validate Token (for frontend)**
```
GET /users/reset-password/validate?token=xxx
→ Returns { valid: true, email: "user@..." }
```

**Step 3: Complete Reset**
```
POST /users/reset-password { token, new_password }
→ Validates token, updates password, invalidates token
```

#### Implementation Details:

1. **Create PasswordResetToken model:**

```python
class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime)  # NULL until used
    created_at = Column(DateTime, default=func.now())
    
    user = relationship("User", back_populates="reset_tokens")
```

2. **Token generation:**
   - Generate 32-byte random token
   - Store SHA-256 hash in database
   - Send raw token in email link
   - Expires in 1 hour

3. **Security measures:**
   - Rate limit: 3 requests per email per hour
   - Token single-use (mark as used after password change)
   - Log all password reset attempts
   - Notify user via email when password is changed

---

### Phase 5D: Integration with Notification Service (Est. 1 hour)

#### Step 5D.1: Add Email Option to Notifications

Update `NotificationService` to optionally send email:

```python
def create_templated_notification(
    self,
    user_id: int,
    notification_type: Union[NotificationType, str],
    context: Dict[str, Any],
    priority: NotificationPriority = NotificationPriority.MEDIUM,
    send_email: bool = False,  # NEW
    email_recipient: Optional[str] = None  # NEW - override user's email
) -> Optional[Notification]:
    """
    Create notification with optional email delivery.
    """
    # Create in-app notification
    notification = self._create_notification(...)
    
    # Queue email if requested
    if send_email:
        email_service.queue_email(
            to_email=email_recipient or user.email,
            template_type=notification_type,
            context=context,
            notification_id=notification.id
        )
    
    return notification
```

#### Step 5D.2: User Email Preferences

Add to User model:

```python
# Email preferences (JSON or separate columns)
email_notifications_enabled = Column(Boolean, default=True)
email_frequency = Column(String(20), default="immediate")
# "immediate" | "daily_digest" | "weekly_digest" | "none"
```

---

### Phase 5E: Email Queue Processing (Est. 1 hour)

#### Option A: Background Task (Simple)

Add endpoint for cron/scheduler to call:

```python
@router.post("/internal/process-email-queue")
async def process_email_queue(
    api_key: str = Header(...),
    db: Session = Depends(get_db)
):
    """Process pending emails - called by cron job"""
    if api_key != settings.internal_api_key:
        raise HTTPException(403, "Invalid API key")
    
    sent_count = await email_service.process_queue(db, batch_size=50)
    return {"processed": sent_count}
```

Set up Railway cron job to call every 1-5 minutes.

#### Option B: Redis Queue (Scalable)

Use existing Redis infrastructure with background workers:

```python
# Using existing redis_manager
async def queue_email(email_data: dict):
    await redis_manager.lpush("email_queue", json.dumps(email_data))

# Worker process
async def email_worker():
    while True:
        email_data = await redis_manager.brpop("email_queue", timeout=5)
        if email_data:
            await send_email(json.loads(email_data))
```

**Recommendation:** Start with Option A (simpler), migrate to Option B if needed.

---

### Phase 5F: Google OAuth Enhancements (Est. 1 hour)

#### Current State
- Google OAuth fully works for login/registration
- No email sent for account linking

#### Enhancements

1. **Account Linking Notification:**
   When a user links Google account to existing email account, send confirmation email.

2. **New Account Welcome Email:**
   When user signs up (via Google or password), send welcome email.

3. **Login from New Device:**
   Optional security feature - email when login detected from new IP/device.

---

## Environment Variables

Add to `env_template.txt`:

```bash
# Email Configuration
# Provider: "smtp" (default), "sendgrid", or "resend"
EMAIL_PROVIDER=smtp

# SMTP Configuration (for EMAIL_PROVIDER=smtp)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
FROM_EMAIL=noreply@n-aible.com
FROM_NAME=n-aible Education Platform

# SendGrid Configuration (for EMAIL_PROVIDER=sendgrid)
SENDGRID_API_KEY=SG.xxxxxxxxxxxxx

# Resend Configuration (for EMAIL_PROVIDER=resend)
RESEND_API_KEY=re_xxxxxxxxxxxxx

# Password Reset Configuration
PASSWORD_RESET_TOKEN_EXPIRE_HOURS=1
PASSWORD_RESET_RATE_LIMIT=3  # requests per email per hour

# Internal API Key (for cron jobs)
INTERNAL_API_KEY=your-secure-random-key
```

---

## Dependencies to Add

```toml
# In pyproject.toml [project.dependencies]
sendgrid = "^6.11.0"       # SendGrid API (production)
resend = "^0.7.0"          # Resend API (alternative)
# email-validator already included via pydantic[email]
```

---

## File Structure

```
backend/
├── common/
│   ├── config.py                    # Add email settings
│   ├── db/
│   │   └── models/
│   │       ├── auth/
│   │       │   └── password_reset_token.py  # NEW
│   │       └── notifications/
│   │           └── email_queue.py           # NEW
│   └── services/
│       ├── email_service.py         # NEW - Core email service
│       └── email_templates.py       # NEW - HTML templates
├── modules/
│   ├── auth/
│   │   ├── router.py               # Update password reset endpoints
│   │   └── service.py              # Add password reset logic
│   └── notifications/
│       └── service.py              # Add send_email parameter
```

---

## Implementation Checklist

### Phase 5A: Infrastructure
- [ ] Add email settings to `common/config.py`
- [ ] Create `common/services/email_service.py` with provider abstraction
- [ ] Create `EmailQueue` model
- [ ] Create database migration
- [ ] Add SendGrid/Resend dependencies to `pyproject.toml`

### Phase 5B: Templates
- [ ] Create `common/services/email_templates.py`
- [ ] Design base HTML email template
- [ ] Create templates for all notification types
- [ ] Create password reset email template

### Phase 5C: Password Reset
- [ ] Create `PasswordResetToken` model
- [ ] Create database migration
- [ ] Update `/forgot-password` endpoint to send email
- [ ] Add `/reset-password/validate` endpoint
- [ ] Add `/reset-password` endpoint for completing reset
- [ ] Add rate limiting

### Phase 5D: Integration
- [ ] Add `send_email` parameter to `create_templated_notification()`
- [ ] Add user email preferences to User model
- [ ] Create migration for email preferences

### Phase 5E: Queue Processing
- [ ] Create internal endpoint for queue processing
- [ ] Set up Railway cron job OR
- [ ] Implement Redis-based queue worker

### Phase 5F: OAuth Enhancements
- [ ] Account linking email notification
- [ ] Welcome email for new users
- [ ] (Optional) New device login notification

---

## Testing Plan

### Unit Tests
- [ ] Email template rendering
- [ ] Token generation and validation
- [ ] Rate limiting logic

### Integration Tests
- [ ] Full password reset flow
- [ ] Email queue processing
- [ ] Notification with email delivery

### Manual Testing
- [ ] Test with Gmail SMTP (development)
- [ ] Test with SendGrid (staging/production)
- [ ] Verify email rendering in multiple clients (Gmail, Outlook, Apple Mail)

---

## Security Considerations

1. **Never log email content or passwords**
2. **Store password reset tokens hashed** (like passwords)
3. **Rate limit all email-sending endpoints**
4. **Validate email addresses** before sending
5. **Use TLS** for all SMTP connections
6. **Sanitize all template variables** to prevent injection
7. **Implement SPF, DKIM, DMARC** for production domain

---

## Estimated Timeline

| Phase | Description | Time | Dependency |
|-------|-------------|------|------------|
| 5A | Infrastructure | 2 hours | None |
| 5B | Templates | 1 hour | 5A |
| 5C | Password Reset | 2 hours | 5A, 5B |
| 5D | Notification Integration | 1 hour | 5A |
| 5E | Queue Processing | 1 hour | 5A |
| 5F | OAuth Enhancements | 1 hour | 5A, 5B |

**Total: 6-8 hours**

---

## Next Steps

1. **Decide on email provider** for production (SendGrid recommended)
2. **Create SendGrid account** and get API key
3. **Begin Phase 5A** implementation
4. **Test in development** with Gmail SMTP
5. **Deploy to staging** with SendGrid

---

## References

- [SendGrid Python SDK](https://github.com/sendgrid/sendgrid-python)
- [Resend Python SDK](https://github.com/resend/resend-python)
- [Railway Cron Jobs](https://docs.railway.app/reference/cron-jobs)
- [Google App Passwords](https://support.google.com/accounts/answer/185833)
- [Email Security Best Practices (OWASP)](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)



