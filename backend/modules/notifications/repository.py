"""
Notification Repository - Database access layer for notifications.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from common.db.models import Notification, CohortInvitation

logger = logging.getLogger(__name__)


class NotificationRepository:
    """Repository for notification database operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_user_notifications(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        unread_only: bool = False
    ) -> List[Notification]:
        """Get notifications for a user with pagination."""
        query = self.db.query(Notification).filter(
            Notification.user_id == user_id
        )
        
        if unread_only:
            query = query.filter(Notification.is_read == False)  # noqa: E712 - SQLAlchemy requires ==
        
        return query.order_by(
            desc(Notification.created_at)
        ).offset(offset).limit(limit).all()
    
    def get_total_notifications_count(
        self,
        user_id: int,
        unread_only: bool = False
    ) -> int:
        """Get total count of notifications for pagination."""
        query = self.db.query(Notification).filter(
            Notification.user_id == user_id
        )
        
        if unread_only:
            query = query.filter(Notification.is_read == False)  # noqa: E712 - SQLAlchemy requires ==
        
        return query.count()
    
    def get_unread_count(self, user_id: int) -> int:
        """Get count of unread notifications for a user."""
        return self.db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False  # noqa: E712 - SQLAlchemy requires ==
        ).count()
    
    def get_notification_by_id(
        self,
        notification_id: int,
        user_id: Optional[int] = None
    ) -> Optional[Notification]:
        """Get a notification by ID, optionally filtered by user."""
        query = self.db.query(Notification).filter(
            Notification.id == notification_id
        )
        if user_id is not None:
            query = query.filter(Notification.user_id == user_id)
        return query.first()
    
    def mark_notification_read(self, notification_id: int, user_id: int) -> bool:
        """Mark a notification as read."""
        notification = self.get_notification_by_id(notification_id, user_id)
        if notification:
            notification.is_read = True
            self.db.commit()
            return True
        return False
    
    def mark_all_notifications_read(self, user_id: int) -> bool:
        """Mark all notifications as read for a user."""
        try:
            self.db.query(Notification).filter(
                Notification.user_id == user_id,
                Notification.is_read == False  # noqa: E712 - SQLAlchemy requires ==
            ).update({"is_read": True})
            self.db.commit()
            return True
        except Exception:
            logger.exception("Failed to mark all notifications read for user %d", user_id)
            self.db.rollback()
            return False
    
    def create_notification(
        self,
        user_id: int,
        notification_type: str,
        title: str,
        message: str,
        data: Optional[dict] = None
    ) -> Notification:
        """Create a new notification."""
        notification = Notification(
            user_id=user_id,
            type=notification_type,
            title=title,
            message=message,
            data=data,
            is_read=False
        )
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        return notification
    
    def delete_notification(self, notification_id: int, user_id: int) -> bool:
        """Delete a notification."""
        notification = self.get_notification_by_id(notification_id, user_id)
        if notification:
            self.db.delete(notification)
            self.db.commit()
            return True
        return False


class InvitationRepository:
    """Repository for cohort invitation database operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_pending_invitations_by_email(self, email: str) -> List[CohortInvitation]:
        """Get pending invitations for a user by email."""
        from sqlalchemy.orm import selectinload
        
        return self.db.query(CohortInvitation).options(
            selectinload(CohortInvitation.cohort),
            selectinload(CohortInvitation.professor)
        ).filter(
            func.lower(CohortInvitation.student_email) == email.lower(),
            CohortInvitation.status == 'pending'
        ).all()
    
    def get_pending_invitations_by_user_id(self, user_id: int) -> List[CohortInvitation]:
        """Get pending invitations for a user by user ID."""
        from sqlalchemy.orm import selectinload
        
        return self.db.query(CohortInvitation).options(
            selectinload(CohortInvitation.cohort),
            selectinload(CohortInvitation.professor)
        ).filter(
            CohortInvitation.student_id == user_id,
            CohortInvitation.status == 'pending'
        ).all()
    
    def get_invitation_by_id(self, invitation_id: int) -> Optional[CohortInvitation]:
        """Get an invitation by ID."""
        return self.db.query(CohortInvitation).filter(
            CohortInvitation.id == invitation_id,
            CohortInvitation.status == 'pending'
        ).first()
    
    def get_invitation_by_token(self, token: str) -> Optional[CohortInvitation]:
        """Get an invitation by token."""
        from sqlalchemy.orm import selectinload
        
        return self.db.query(CohortInvitation).options(
            selectinload(CohortInvitation.cohort),
            selectinload(CohortInvitation.professor)
        ).filter(
            CohortInvitation.invitation_token == token,
            CohortInvitation.status == 'pending'
        ).first()
    
    def update_invitation_status(
        self,
        invitation: CohortInvitation,
        status: str,
        student_id: Optional[int] = None
    ) -> CohortInvitation:
        """Update invitation status."""
        invitation.status = status
        if student_id:
            invitation.student_id = student_id
        self.db.commit()
        self.db.refresh(invitation)
        return invitation
    
    def is_invitation_expired(self, invitation: CohortInvitation) -> bool:
        """Check if an invitation is expired.
        
        Handles both timezone-aware and naive datetimes for compatibility
        with different databases (PostgreSQL returns timezone-aware, SQLite naive).
        """
        expires_at = invitation.expires_at
        # Handle naive datetimes (e.g., from SQLite)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at < datetime.now(timezone.utc)
    
    def mark_invitation_expired(self, invitation: CohortInvitation) -> CohortInvitation:
        """Mark an invitation as expired."""
        invitation.status = 'expired'
        self.db.commit()
        return invitation
