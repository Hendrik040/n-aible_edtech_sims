"""
Notification Service - Business logic for notifications.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

from common.db.models import Notification, CohortInvitation, User, CohortStudent
from .repository import NotificationRepository, InvitationRepository

logger = logging.getLogger(__name__)


def _mask_email(email: str) -> str:
    """Mask email address for logging to protect PII."""
    if not email or '@' not in email:
        return "***"
    local, domain = email.rsplit('@', 1)
    if len(local) <= 2:
        masked_local = local[0] + "***"
    else:
        masked_local = local[0] + "***" + local[-1]
    return f"{masked_local}@{domain}"


class NotificationService:
    """Service for notification business logic."""
    
    def __init__(self, db: Session):
        self.db = db
        self.notification_repo = NotificationRepository(db)
        self.invitation_repo = InvitationRepository(db)
    
    def get_user_notifications(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        unread_only: bool = False
    ) -> List[Notification]:
        """Get notifications for a user."""
        return self.notification_repo.get_user_notifications(
            user_id, limit, offset, unread_only
        )
    
    def get_total_notifications_count(
        self,
        user_id: int,
        unread_only: bool = False
    ) -> int:
        """Get total count of notifications for pagination."""
        return self.notification_repo.get_total_notifications_count(user_id, unread_only)
    
    def get_unread_count(self, user_id: int) -> int:
        """Get count of unread notifications for a user."""
        return self.notification_repo.get_unread_count(user_id)
    
    def mark_notification_read(self, notification_id: int, user_id: int) -> bool:
        """Mark a notification as read."""
        return self.notification_repo.mark_notification_read(notification_id, user_id)
    
    def mark_all_notifications_read(self, user_id: int) -> bool:
        """Mark all notifications as read for a user."""
        return self.notification_repo.mark_all_notifications_read(user_id)
    
    def create_notification(
        self,
        user_id: int,
        notification_type: str,
        title: str,
        message: str,
        data: Optional[dict] = None
    ) -> Notification:
        """Create a new notification."""
        return self.notification_repo.create_notification(
            user_id, notification_type, title, message, data
        )
    
    def create_invitation_response_notification(
        self,
        invitation: CohortInvitation,
        action: str
    ) -> Optional[Notification]:
        """Create a notification when a student responds to an invitation."""
        try:
            # Get student info
            student_email = invitation.student_email
            student_name = student_email  # Default to email
            
            if invitation.student_id:
                student = self.db.query(User).filter(
                    User.id == invitation.student_id
                ).first()
                if student:
                    student_name = student.full_name or student.email
            
            # Get cohort info
            cohort_title = "Unknown Cohort"
            if invitation.cohort:
                cohort_title = invitation.cohort.title
            
            # Create notification for the professor
            title = f"Invitation {action}ed"
            if action == "accept":
                message = f"{student_name} has accepted your invitation to join {cohort_title}"
            else:
                message = f"{student_name} has declined your invitation to join {cohort_title}"
            
            return self.notification_repo.create_notification(
                user_id=invitation.professor_id,
                notification_type=f"invitation_{action}ed",
                title=title,
                message=message,
                data={
                    "invitation_id": invitation.id,
                    "cohort_id": invitation.cohort_id,
                    "student_email": student_email,
                    "action": action
                }
            )
        except Exception:
            logger.exception("Failed to create invitation response notification")
            return None
    
    def _check_existing_enrollment(self, cohort_id: int, student_id: int) -> bool:
        """Check if a student is already enrolled in a cohort."""
        existing = self.db.query(CohortStudent).filter(
            CohortStudent.cohort_id == cohort_id,
            CohortStudent.student_id == student_id
        ).first()
        return existing is not None
    
    # ==================== INVITATION METHODS ====================
    
    def get_pending_invitations(self, user: User) -> List[Dict[str, Any]]:
        """Get pending invitations for a user (by email and user ID)."""
        # Get invitations by email
        email_invitations = self.invitation_repo.get_pending_invitations_by_email(user.email)
        
        # Get invitations by user ID
        user_invitations = self.invitation_repo.get_pending_invitations_by_user_id(user.id)
        
        # Combine and deduplicate
        all_invitations = email_invitations + user_invitations
        unique_invitations = list({inv.id: inv for inv in all_invitations}.values())
        
        # Build response with cohort and professor data
        invitations_with_details = []
        for inv in unique_invitations:
            invitation_data = {
                "id": inv.id,
                "cohort_id": inv.cohort_id,
                "professor_id": inv.professor_id,
                "student_email": inv.student_email,
                "student_id": inv.student_id,
                "status": inv.status,
                "message": inv.message,
                "expires_at": inv.expires_at,
                "created_at": inv.created_at,
                "cohort": {
                    "id": inv.cohort.id,
                    "title": inv.cohort.title,
                    "description": inv.cohort.description,
                    "course_code": inv.cohort.course_code
                } if inv.cohort else None,
                "invited_by": {
                    "id": inv.professor.id,
                    "full_name": inv.professor.full_name,
                    "email": inv.professor.email
                } if inv.professor else None
            }
            invitations_with_details.append(invitation_data)
        
        return invitations_with_details
    
    def respond_to_invitation(
        self,
        invitation_id: int,
        action: str,
        user: User
    ) -> Dict[str, Any]:
        """Respond to a cohort invitation (accept or decline)."""
        logger.info("Responding to invitation %d with action: %s", invitation_id, action)
        logger.info("Current user ID: %d", user.id)
        
        # Find the invitation
        invitation = self.invitation_repo.get_invitation_by_id(invitation_id)
        
        if not invitation:
            logger.error("Invitation %d not found or not pending", invitation_id)
            raise ValueError("Invitation not found or already responded to")
        
        logger.info("Found invitation: %d, student_id: %s", invitation.id, invitation.student_id)
        
        # Verify the invitation is for this student
        email_match = invitation.student_email == user.email
        id_match = invitation.student_id is not None and invitation.student_id == user.id
        
        if not (email_match or id_match):
            logger.error("Invitation mismatch for invitation %d, user ID: %d", invitation_id, user.id)
            raise PermissionError("This invitation is not for you")
        
        # Check if invitation is expired
        if self.invitation_repo.is_invitation_expired(invitation):
            self.invitation_repo.mark_invitation_expired(invitation)
            raise ValueError("This invitation has expired")
        
        # Update invitation status
        new_status = 'accepted' if action == 'accept' else 'declined'
        self.invitation_repo.update_invitation_status(invitation, new_status, user.id)
        
        # If accepted, create cohort enrollment (check for duplicates first)
        if action == 'accept':
            if not self._check_existing_enrollment(invitation.cohort_id, user.id):
                enrollment = CohortStudent(
                    cohort_id=invitation.cohort_id,
                    student_id=user.id,
                    status='approved',
                    enrollment_date=datetime.now(timezone.utc)
                )
                self.db.add(enrollment)
                self.db.commit()
                logger.info("Student %d joined cohort %d", user.id, invitation.cohort_id)
            else:
                logger.info("Student %d already enrolled in cohort %d", user.id, invitation.cohort_id)
        
        # Create notification for professor
        self.create_invitation_response_notification(invitation, action)
        
        return {
            "message": f"Invitation {action}ed successfully",
            "action": action,
            "cohort_id": invitation.cohort_id
        }
    
    def get_invitation_by_token(self, token: str) -> Dict[str, Any]:
        """Get invitation details by token (for email links)."""
        invitation = self.invitation_repo.get_invitation_by_token(token)
        
        if not invitation:
            raise ValueError("Invitation not found or expired")
        
        # Check if invitation is expired
        if self.invitation_repo.is_invitation_expired(invitation):
            self.invitation_repo.mark_invitation_expired(invitation)
            raise ValueError("This invitation has expired")
        
        return {
            "invitation": {
                "id": invitation.id,
                "cohort_id": invitation.cohort_id,
                "professor_id": invitation.professor_id,
                "student_email": invitation.student_email,
                "student_id": invitation.student_id,
                "status": invitation.status,
                "message": invitation.message,
                "expires_at": invitation.expires_at,
                "created_at": invitation.created_at,
            },
            "cohort": {
                "id": invitation.cohort.id,
                "title": invitation.cohort.title,
                "description": invitation.cohort.description,
                "course_code": invitation.cohort.course_code,
                "semester": getattr(invitation.cohort, 'semester', None),
                "year": getattr(invitation.cohort, 'year', None)
            } if invitation.cohort else None,
            "professor": {
                "id": invitation.professor.id,
                "full_name": invitation.professor.full_name,
                "email": invitation.professor.email
            } if invitation.professor else None
        }
    
    def respond_to_invitation_by_token(
        self,
        token: str,
        action: str
    ) -> Dict[str, Any]:
        """Respond to invitation by token (for non-authenticated users)."""
        invitation = self.invitation_repo.get_invitation_by_token(token)
        
        if not invitation:
            raise ValueError("Invitation not found or already responded to")
        
        # Check if invitation is expired
        if self.invitation_repo.is_invitation_expired(invitation):
            self.invitation_repo.mark_invitation_expired(invitation)
            raise ValueError("This invitation has expired")
        
        # Update invitation status using repository method
        new_status = 'accepted' if action == 'accept' else 'declined'
        self.invitation_repo.update_invitation_status(invitation, new_status)
        
        requires_registration = False
        
        # If accepted, check if the student exists in the system
        if action == 'accept':
            student = self.db.query(User).filter(
                User.email == invitation.student_email,
                User.role == 'student'
            ).first()
            
            if student:
                # Check for existing enrollment before creating
                if not self._check_existing_enrollment(invitation.cohort_id, student.id):
                    enrollment = CohortStudent(
                        cohort_id=invitation.cohort_id,
                        student_id=student.id,
                        status='approved',
                        enrollment_date=datetime.now(timezone.utc)
                    )
                    self.db.add(enrollment)
                
                invitation.student_id = student.id
                self.db.commit()
                logger.info("Student %d joined cohort %d", student.id, invitation.cohort_id)
            else:
                requires_registration = True
                logger.info(
                    "Invitation accepted but student %s not found in system",
                    _mask_email(invitation.student_email)
                )
        
        # Create notification for professor
        self.create_invitation_response_notification(invitation, action)
        
        return {
            "message": f"Invitation {action}ed successfully",
            "action": action,
            "cohort_id": invitation.cohort_id,
            "requires_registration": requires_registration
        }
