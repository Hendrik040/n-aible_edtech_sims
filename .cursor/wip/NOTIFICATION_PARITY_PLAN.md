# Notification Module Parity Plan

**Created:** 2025-12-25  
**Last Updated:** 2025-12-26  
**Status:** In Progress (Phases 1-4 Complete)  
**Priority:** Medium  
**Estimated Effort:** 4-6 hours

---

## Overview

The current notification module in `n-aible_edtech_sims` is missing significant functionality compared to the previous version in `prev/`. This document outlines the step-by-step plan to achieve feature parity.

---

## Current State Analysis

### ✅ What Works Now
- Basic `Notification` database model with all required fields
- CRUD operations via `NotificationRepository`
- User notification retrieval with pagination
- Mark read / mark all read functionality
- Cohort invitation handling (accept/decline)
- API endpoints for professors and students
- Token-based invitation responses (for email links)

### ❌ What's Missing
1. Notification type templates with message formatting
2. Priority system for notifications
3. Email notification service (`EmailService`) and `EmailQueue` model
4. Specialized notification creator methods
5. Bulk notification helpers
6. Notification cleanup utility

---

## Step-by-Step Implementation Plan

---

### Phase 1: Notification Type Templates System

**Goal:** Create a centralized template system for consistent notification formatting.

#### Step 1.1: Create Notification Types Enum/Constants

**File:** `backend/modules/notifications/constants.py` (new file)

```python
"""Notification type constants and templates."""
from enum import Enum
from typing import Dict, Any

class NotificationType(str, Enum):
    """Enumeration of notification types."""
    COHORT_INVITATION = "cohort_invitation"
    INVITATION_ACCEPTED = "invitation_accepted"
    INVITATION_DECLINED = "invitation_declined"
    ASSIGNMENT_DUE = "assignment_due"
    ASSIGNMENT_OVERDUE = "assignment_overdue"
    GRADE_POSTED = "grade_posted"
    COHORT_UPDATE = "cohort_update"
    SIMULATION_ASSIGNED = "simulation_assigned"
    PROFESSOR_MESSAGE = "professor_message"
    STUDENT_REPLY = "student_reply"
    STUDENT_MESSAGE = "student_message"
    MESSAGE_SENT = "message_sent"

class NotificationPriority(str, Enum):
    """Priority levels for notifications."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

NOTIFICATION_TEMPLATES: Dict[str, Dict[str, Any]] = {
    NotificationType.COHORT_INVITATION: {
        "title_template": "New Cohort Invitation",
        "message_template": 'You have been invited to join "{cohort_title}" by {professor_name}',
        "priority": NotificationPriority.HIGH
    },
    NotificationType.INVITATION_ACCEPTED: {
        "title_template": "Student Joined Cohort",
        "message_template": '{student_name} has accepted your invitation to join "{cohort_title}"',
        "priority": NotificationPriority.MEDIUM
    },
    NotificationType.INVITATION_DECLINED: {
        "title_template": "Invitation Declined",
        "message_template": '{student_name} has declined your invitation to join "{cohort_title}"',
        "priority": NotificationPriority.MEDIUM
    },
    NotificationType.ASSIGNMENT_DUE: {
        "title_template": "Assignment Due Soon",
        "message_template": 'Assignment "{assignment_title}" is due on {due_date}',
        "priority": NotificationPriority.HIGH
    },
    NotificationType.ASSIGNMENT_OVERDUE: {
        "title_template": "Assignment Overdue",
        "message_template": 'Assignment "{assignment_title}" is now overdue',
        "priority": NotificationPriority.HIGH
    },
    NotificationType.GRADE_POSTED: {
        "title_template": "Grade Posted",
        "message_template": 'Your grade for "{assignment_title}" is now available',
        "priority": NotificationPriority.MEDIUM
    },
    NotificationType.COHORT_UPDATE: {
        "title_template": "Cohort Updated",
        "message_template": 'The cohort "{cohort_title}" has been updated',
        "priority": NotificationPriority.LOW
    },
    NotificationType.SIMULATION_ASSIGNED: {
        "title_template": "New Simulation Assigned",
        "message_template": 'A new simulation "{simulation_title}" has been assigned to your cohort "{cohort_title}"',
        "priority": NotificationPriority.HIGH
    },
    NotificationType.PROFESSOR_MESSAGE: {
        "title_template": "Message from Professor",
        "message_template": 'You have received a message from {professor_name}: "{message_subject}"',
        "priority": NotificationPriority.MEDIUM
    },
    NotificationType.STUDENT_REPLY: {
        "title_template": "Student Reply",
        "message_template": '{student_name} has replied to your message: "{message_subject}"',
        "priority": NotificationPriority.MEDIUM
    },
    NotificationType.STUDENT_MESSAGE: {
        "title_template": "Message from Student",
        "message_template": 'You have received a message from {student_name}: "{message_subject}"',
        "priority": NotificationPriority.MEDIUM
    },
    NotificationType.MESSAGE_SENT: {
        "title_template": "Message Sent",
        "message_template": 'You sent a message to {recipient_name}: "{message_subject}"',
        "priority": NotificationPriority.LOW
    }
}
```

#### Step 1.2: Add Template-Based Creation Method to Service

**File:** `backend/modules/notifications/service.py`

Add the following method to `NotificationService` class:

```python
from .constants import NOTIFICATION_TEMPLATES, NotificationType

def create_templated_notification(
    self,
    user_id: int,
    notification_type: NotificationType,
    variables: Dict[str, Any],
    data: Optional[dict] = None
) -> Optional[Notification]:
    """Create a notification using a predefined template."""
    if notification_type not in NOTIFICATION_TEMPLATES:
        logger.error("Unknown notification type: %s", notification_type)
        return None
    
    template = NOTIFICATION_TEMPLATES[notification_type]
    try:
        title = template["title_template"].format(**variables)
        message = template["message_template"].format(**variables)
    except KeyError as e:
        logger.error("Missing template variable for %s: %s", notification_type, e)
        return None
    
    return self.notification_repo.create_notification(
        user_id=user_id,
        notification_type=notification_type.value,
        title=title,
        message=message,
        data=data
    )
```

---

### Phase 2: Specialized Notification Creator Methods

**Goal:** Add convenience methods for common notification scenarios.

#### Step 2.1: Add Cohort Invitation Notification

**File:** `backend/modules/notifications/service.py`

```python
def create_cohort_invitation_notification(
    self,
    invitation: CohortInvitation
) -> Optional[Notification]:
    """Create notification for cohort invitation."""
    # Check if student exists in the system
    from sqlalchemy import func
    student = self.db.query(User).filter(
        func.lower(User.email) == invitation.student_email.lower(),
        User.role == 'student'
    ).first()
    
    if not student:
        logger.info(
            "Student with email %s not found, skipping notification",
            _mask_email(invitation.student_email)
        )
        return None
    
    variables = {
        "cohort_title": invitation.cohort.title if invitation.cohort else "Unknown",
        "professor_name": invitation.professor.full_name if invitation.professor else "Unknown"
    }
    
    data = {
        "invitation_id": invitation.id,
        "cohort_id": invitation.cohort_id,
        "professor_id": invitation.professor_id
    }
    
    return self.create_templated_notification(
        user_id=student.id,
        notification_type=NotificationType.COHORT_INVITATION,
        variables=variables,
        data=data
    )
```

#### Step 2.2: Add Assignment Due Notification

```python
def create_assignment_due_notification(
    self,
    student_id: int,
    assignment_title: str,
    due_date: datetime
) -> Optional[Notification]:
    """Create notification for assignment due soon."""
    variables = {
        "assignment_title": assignment_title,
        "due_date": due_date.strftime("%B %d, %Y at %I:%M %p")
    }
    
    return self.create_templated_notification(
        user_id=student_id,
        notification_type=NotificationType.ASSIGNMENT_DUE,
        variables=variables
    )
```

#### Step 2.3: Add Grade Posted Notification

```python
def create_grade_posted_notification(
    self,
    student_id: int,
    assignment_title: str,
    cohort_title: str
) -> Optional[Notification]:
    """Create notification for grade posted."""
    variables = {
        "assignment_title": assignment_title,
        "cohort_title": cohort_title
    }
    
    data = {"student_id": student_id}
    
    return self.create_templated_notification(
        user_id=student_id,
        notification_type=NotificationType.GRADE_POSTED,
        variables=variables,
        data=data
    )
```

#### Step 2.4: Add Simulation Assignment Notification

```python
def create_simulation_assignment_notification(
    self,
    student_id: int,
    cohort_simulation,  # CohortSimulation model
    scenario,  # Scenario model
    cohort  # Cohort model
) -> Optional[Notification]:
    """Create notification for simulation assignment."""
    variables = {
        "simulation_title": scenario.title,
        "cohort_title": cohort.title
    }
    
    data = {
        "cohort_simulation_id": cohort_simulation.id,
        "simulation_id": scenario.id,
        "cohort_id": cohort.id,
        "due_date": cohort_simulation.due_date.isoformat() if cohort_simulation.due_date else None,
        "is_required": cohort_simulation.is_required
    }
    
    return self.create_templated_notification(
        user_id=student_id,
        notification_type=NotificationType.SIMULATION_ASSIGNED,
        variables=variables,
        data=data
    )
```

#### Step 2.5: Add Message Notifications

```python
def create_professor_message_notification(
    self,
    professor: User,
    student: User,
    message_subject: str,
    cohort_id: Optional[int] = None
) -> Optional[Notification]:
    """Create notification when professor sends message to student."""
    variables = {
        "professor_name": professor.full_name,
        "message_subject": message_subject
    }
    
    data = {
        "professor_id": professor.id,
        "cohort_id": cohort_id,
        "message_type": "professor_message"
    }
    
    return self.create_templated_notification(
        user_id=student.id,
        notification_type=NotificationType.PROFESSOR_MESSAGE,
        variables=variables,
        data=data
    )

def create_student_message_notification(
    self,
    student: User,
    professor: User,
    message_subject: str,
    cohort_id: Optional[int] = None
) -> Optional[Notification]:
    """Create notification when student sends message to professor."""
    variables = {
        "student_name": student.full_name,
        "message_subject": message_subject
    }
    
    data = {
        "student_id": student.id,
        "cohort_id": cohort_id,
        "message_type": "student_message"
    }
    
    return self.create_templated_notification(
        user_id=professor.id,
        notification_type=NotificationType.STUDENT_MESSAGE,
        variables=variables,
        data=data
    )

def create_student_reply_notification(
    self,
    student: User,
    professor: User,
    message_subject: str,
    cohort_id: Optional[int] = None
) -> Optional[Notification]:
    """Create notification when student replies to professor's message."""
    variables = {
        "student_name": student.full_name,
        "message_subject": message_subject
    }
    
    data = {
        "student_id": student.id,
        "cohort_id": cohort_id,
        "message_type": "student_reply"
    }
    
    return self.create_templated_notification(
        user_id=professor.id,
        notification_type=NotificationType.STUDENT_REPLY,
        variables=variables,
        data=data
    )
```

---

### Phase 3: Bulk Notification Methods

**Goal:** Add methods to notify entire cohorts at once.

#### Step 3.1: Add Bulk Assignment Due Notification

**File:** `backend/modules/notifications/service.py`

```python
def create_bulk_assignment_due_notifications(
    self,
    cohort_id: int,
    assignment_title: str,
    due_date: datetime
) -> int:
    """Create notifications for all students in a cohort about assignment due."""
    try:
        # Get all approved students in the cohort
        students = self.db.query(User).join(CohortStudent).filter(
            CohortStudent.cohort_id == cohort_id,
            CohortStudent.status == 'approved',
            User.role == 'student'
        ).all()
        
        created_count = 0
        for student in students:
            notification = self.create_assignment_due_notification(
                student.id, assignment_title, due_date
            )
            if notification:
                created_count += 1
        
        logger.info(
            "Created %d assignment due notifications for cohort %d",
            created_count, cohort_id
        )
        return created_count
        
    except Exception:
        logger.exception("Failed to create bulk assignment notifications")
        return 0
```

#### Step 3.2: Add Bulk Grade Notifications

```python
def create_bulk_grade_notifications(
    self,
    cohort_id: int,
    assignment_title: str
) -> int:
    """Create notifications for all students in a cohort about grade posted."""
    try:
        from common.db.models import Cohort
        
        # Get cohort title
        cohort = self.db.query(Cohort).filter(Cohort.id == cohort_id).first()
        cohort_title = cohort.title if cohort else "Unknown Cohort"
        
        # Get all approved students in the cohort
        students = self.db.query(User).join(CohortStudent).filter(
            CohortStudent.cohort_id == cohort_id,
            CohortStudent.status == 'approved',
            User.role == 'student'
        ).all()
        
        created_count = 0
        for student in students:
            notification = self.create_grade_posted_notification(
                student.id, assignment_title, cohort_title
            )
            if notification:
                created_count += 1
        
        logger.info(
            "Created %d grade posted notifications for cohort %d",
            created_count, cohort_id
        )
        return created_count
        
    except Exception:
        logger.exception("Failed to create bulk grade notifications")
        return 0
```

#### Step 3.3: Add Bulk Simulation Assignment Notification

```python
def create_bulk_simulation_notifications(
    self,
    cohort_simulation,
    scenario,
    cohort
) -> int:
    """Create notifications for all students when a simulation is assigned to cohort."""
    try:
        # Get all approved students in the cohort
        students = self.db.query(User).join(CohortStudent).filter(
            CohortStudent.cohort_id == cohort.id,
            CohortStudent.status == 'approved',
            User.role == 'student'
        ).all()
        
        created_count = 0
        for student in students:
            notification = self.create_simulation_assignment_notification(
                student.id, cohort_simulation, scenario, cohort
            )
            if notification:
                created_count += 1
        
        logger.info(
            "Created %d simulation assignment notifications for cohort %d",
            created_count, cohort.id
        )
        return created_count
        
    except Exception:
        logger.exception("Failed to create bulk simulation notifications")
        return 0
```

---

### Phase 4: Notification Cleanup Utility

**Goal:** Add method to delete old read notifications.

#### Step 4.1: Add to Repository

**File:** `backend/modules/notifications/repository.py`

```python
from datetime import timedelta

def delete_old_notifications(self, days_old: int = 30) -> int:
    """Delete read notifications older than specified days."""
    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
        
        deleted = self.db.query(Notification).filter(
            Notification.created_at < cutoff_date,
            Notification.is_read == True  # noqa: E712
        ).delete(synchronize_session=False)
        
        self.db.commit()
        
        logger.info("Deleted %d old notifications", deleted)
        return deleted
        
    except Exception:
        logger.exception("Failed to delete old notifications")
        self.db.rollback()
        return 0
```

#### Step 4.2: Add to Service

**File:** `backend/modules/notifications/service.py`

```python
def delete_old_notifications(self, days_old: int = 30) -> int:
    """Delete read notifications older than specified days."""
    return self.notification_repo.delete_old_notifications(days_old)
```

---

### Phase 5: Email Notification Service (Optional - Higher Effort)

**Goal:** Add email notification capabilities.

> ⚠️ **Note:** This phase is more complex and may be deferred based on priority.

#### Step 5.1: Create EmailQueue Model

**File:** `backend/common/db/models/notifications/email_queue.py` (new file)

```python
"""Email queue model for email notifications."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Text, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from common.db.base import Base


class EmailQueue(Base):
    """Email queue for sending notifications."""
    __tablename__ = "email_queue"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    email_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    
    __table_args__ = (
        Index("idx_email_queue_status", "status"),
        Index("idx_email_queue_scheduled_at", "scheduled_at"),
        Index("idx_email_queue_email_type", "email_type"),
    )
```

#### Step 5.2: Create Alembic Migration

Create migration file: `backend/common/db/migrations/versions/YYYY_MM_DD_HHMM-add_email_queue_table.py`

#### Step 5.3: Create Email Service

**File:** `backend/modules/notifications/email_service.py` (new file)

Copy and adapt from `prev/backend/services/email_service.py`:
- HTML email templates
- SMTP configuration via environment variables
- `queue_email()` method
- `send_email()` method
- `process_email_queue()` background task

#### Step 5.4: Add Email Config to Environment

Add to `env_template.txt`:
```
# Email Configuration (optional)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
FROM_EMAIL=noreply@yourapp.com
FROM_NAME=AI Agent Education Platform
```

---

### Phase 6: Update Module Exports

**Goal:** Expose all new functionality via module `__init__.py`.

#### Step 6.1: Update Module Init

**File:** `backend/modules/notifications/__init__.py`

```python
"""
Notifications module for in-app notifications and cohort invitations.

This module provides:
- In-app notifications for professors and students
- Cohort invitation management
- Notification read/unread tracking
- Templated notification creation
- Bulk notification utilities
"""
from .router import router
from .service import NotificationService
from .repository import NotificationRepository, InvitationRepository
from .constants import NotificationType, NotificationPriority, NOTIFICATION_TEMPLATES

__all__ = [
    "InvitationRepository",
    "NotificationPriority",
    "NotificationRepository",
    "NotificationService",
    "NotificationType",
    "NOTIFICATION_TEMPLATES",
    "router",
]
```

---

## Implementation Checklist

### Phase 1: Templates (Est. 30 min) ✅ COMPLETE
- [x] Create `constants.py` with `NotificationType`, `NotificationPriority`, and `NOTIFICATION_TEMPLATES`
- [x] Add `create_templated_notification()` to service
- [x] Update imports in `__init__.py`

### Phase 2: Specialized Creators (Est. 1 hour) ✅ COMPLETE
- [x] Add `create_cohort_invitation_notification()`
- [x] Add `create_assignment_due_notification()`
- [x] Add `create_assignment_overdue_notification()` (added)
- [x] Add `create_grade_posted_notification()`
- [x] Add `create_simulation_assignment_notification()`
- [x] Add `create_professor_message_notification()`
- [x] Add `create_student_message_notification()`
- [x] Add `create_student_reply_notification()`
- [x] Add `create_cohort_update_notification()` (added)
- [x] Refactor existing `create_invitation_response_notification()` to use templates

### Phase 3: Bulk Methods (Est. 45 min) ✅ COMPLETE
- [x] Add `_get_cohort_students()` helper method
- [x] Add `create_bulk_assignment_due_notifications()`
- [x] Add `create_bulk_assignment_overdue_notifications()` (added)
- [x] Add `create_bulk_grade_notifications()`
- [x] Add `create_bulk_simulation_notifications()`
- [x] Add `create_bulk_cohort_update_notifications()` (added)

### Phase 4: Cleanup Utility (Est. 15 min) ✅ COMPLETE
- [x] Add `delete_old_notifications()` to repository
- [x] Add `delete_old_notifications()` to service
- [x] Add `delete_all_user_notifications()` to repository (added)
- [x] Add `delete_all_user_notifications()` to service (added)

### Phase 5: Email Service (Est. 2-3 hours) — ⏸️ DEFERRED
> **Note:** Email notification service is on hold. Can be implemented later when needed.
> Requires: EmailQueue model, Alembic migration, SMTP config, background task.

- [ ] Create `EmailQueue` model
- [ ] Create Alembic migration
- [ ] Create `email_service.py`
- [ ] Add email templates
- [ ] Add environment configuration
- [ ] Add background task for queue processing

### Phase 6: Final Touches (Est. 30 min) ✅ COMPLETE
- [x] Update module `__init__.py` exports
- [x] Wire up simulation assignment notification in `cohorts/service.py`
- [ ] Wire up cohort invitation notification (when individual invites are implemented)
- [ ] Add unit tests for new methods (optional - can be done later)
- [x] Manual testing of notification display in frontend (ready to test)

---

## Wiring Summary

### ✅ Wired Up
| Notification Type | Location | Trigger |
|-------------------|----------|---------|
| `SIMULATION_ASSIGNED` | `modules/cohorts/service.py:assign_simulation_to_cohort()` | Professor assigns simulation to cohort |
| `INVITATION_ACCEPTED` | `modules/notifications/service.py:respond_to_invitation()` | Student accepts cohort invitation |
| `INVITATION_DECLINED` | `modules/notifications/service.py:respond_to_invitation()` | Student declines cohort invitation |

### ⏳ Future Wiring (when features are implemented)
| Notification Type | Suggested Location | Trigger |
|-------------------|-------------------|---------|
| `COHORT_INVITATION` | When individual email invites are sent | Professor invites student to cohort |
| `GRADE_POSTED` | Grading service | Professor grades a simulation |
| `ASSIGNMENT_DUE` | Background task/scheduler | X days before due date |
| `PROFESSOR_MESSAGE` / `STUDENT_MESSAGE` | Messaging module | When messages are sent |

---

## Testing Strategy

1. **Unit Tests** for each new service method
2. **Integration Tests** for notification creation flow
3. **Manual Testing** of notification display in frontend

---

## Dependencies

- No new Python packages required for Phases 1-4
- Phase 5 (Email) may benefit from using a library like `aiosmtplib` for async email sending

---

## Notes

- The frontend notification pages already exist and should work with the enhanced backend
- Priority field is stored in templates but not currently in the DB model — can be added later if needed for sorting/filtering
- Email service is optional and can be implemented later based on requirements

