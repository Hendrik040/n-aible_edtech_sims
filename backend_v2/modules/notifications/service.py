"""
Notification Service - Business logic for notifications.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Union

from sqlalchemy import func
from sqlalchemy.orm import Session

from common.db.models import Notification, CohortInvitation, User, CohortStudent
from .repository import NotificationRepository, InvitationRepository
from .constants import (
    NotificationType,
    NOTIFICATION_TEMPLATES,
    format_notification,
)

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
    
    # ==================== CLEANUP UTILITIES ====================
    
    def delete_old_notifications(self, days_old: int = 30) -> int:
        """
        Delete read notifications older than specified days.
        
        This is useful for periodic cleanup to prevent the notifications table
        from growing indefinitely. Only removes notifications that have been read.
        
        Args:
            days_old: Delete read notifications older than this many days (default 30)
            
        Returns:
            The number of notifications deleted
            
        Example:
            # Delete all read notifications older than 60 days
            deleted = service.delete_old_notifications(days_old=60)
            print(f"Cleaned up {deleted} old notifications")
        """
        return self.notification_repo.delete_old_notifications(days_old)
    
    def delete_all_user_notifications(self, user_id: int) -> int:
        """
        Delete all notifications for a user.
        
        This can be used when a user account is deleted or for bulk cleanup.
        
        Args:
            user_id: The ID of the user whose notifications should be deleted
            
        Returns:
            The number of notifications deleted
        """
        return self.notification_repo.delete_all_user_notifications(user_id)
    
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
    
    def create_templated_notification(
        self,
        user_id: int,
        notification_type: Union[NotificationType, str],
        variables: Dict[str, Any],
        data: Optional[dict] = None
    ) -> Optional[Notification]:
        """
        Create a notification using a predefined template.
        
        This method uses the NOTIFICATION_TEMPLATES to automatically format
        the title and message based on the notification type and provided variables.
        
        Args:
            user_id: The ID of the user to receive the notification
            notification_type: The type of notification (from NotificationType enum or string)
            variables: Dictionary of variables to substitute into the template
                       (e.g., {"cohort_title": "CS101", "professor_name": "Dr. Smith"})
            data: Optional additional data to store with the notification (JSON)
            
        Returns:
            The created Notification object, or None if creation failed
            
        Example:
            service.create_templated_notification(
                user_id=123,
                notification_type=NotificationType.COHORT_INVITATION,
                variables={"cohort_title": "CS101", "professor_name": "Dr. Smith"},
                data={"invitation_id": 456, "cohort_id": 789}
            )
        """
        # Convert string to enum if necessary
        if isinstance(notification_type, str):
            try:
                notification_type = NotificationType(notification_type)
            except ValueError:
                logger.error("Unknown notification type: %s", notification_type)
                return None
        
        # Check if notification type exists in templates
        if notification_type not in NOTIFICATION_TEMPLATES:
            logger.error("No template found for notification type: %s", notification_type)
            return None
        
        # Format the notification using the template
        try:
            formatted = format_notification(notification_type, variables)
        except KeyError as e:
            logger.error(
                "Missing template variable for %s: %s. Variables provided: %s",
                notification_type, e, list(variables.keys())
            )
            return None
        
        # Create the notification
        try:
            return self.notification_repo.create_notification(
                user_id=user_id,
                notification_type=notification_type.value,
                title=formatted["title"],
                message=formatted["message"],
                data=data
            )
        except Exception:
            logger.exception(
                "Failed to create templated notification for user %d, type %s",
                user_id, notification_type
            )
            return None
    
    def create_invitation_response_notification(
        self,
        invitation: CohortInvitation,
        action: str
    ) -> Optional[Notification]:
        """
        Create a notification when a student responds to an invitation.
        
        Uses the templated notification system for consistent formatting.
        
        Args:
            invitation: The CohortInvitation that was responded to
            action: Either "accept" or "decline"
            
        Returns:
            The created Notification, or None if creation failed
        """
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
            
            # Determine notification type based on action
            notification_type = (
                NotificationType.INVITATION_ACCEPTED
                if action == "accept"
                else NotificationType.INVITATION_DECLINED
            )
            
            # Build template variables
            variables = {
                "student_name": student_name,
                "cohort_title": cohort_title
            }
            
            # Build notification data payload
            data = {
                "invitation_id": invitation.id,
                "cohort_id": invitation.cohort_id,
                "student_email": student_email,
                "action": action
            }
            
            # Use templated notification creation
            return self.create_templated_notification(
                user_id=invitation.professor_id,
                notification_type=notification_type,
                variables=variables,
                data=data
            )
        except Exception:
            logger.exception("Failed to create invitation response notification")
            return None
    
    # ==================== SPECIALIZED NOTIFICATION CREATORS ====================
    # These methods provide convenient wrappers for common notification scenarios
    
    def create_cohort_invitation_notification(
        self,
        invitation: CohortInvitation
    ) -> Optional[Notification]:
        """
        Create a notification for a student when they receive a cohort invitation.
        
        This notification is sent to the student (if they exist in the system)
        to inform them about a new cohort invitation from a professor.
        
        Args:
            invitation: The CohortInvitation object
            
        Returns:
            The created Notification, or None if student not found or creation failed
        """
        try:
            # Check if student exists in the system (case-insensitive)
            student = self.db.query(User).filter(
                func.lower(User.email) == invitation.student_email.lower(),
                User.role == 'student'
            ).first()
            
            if not student:
                logger.info(
                    "Student with email %s not found, skipping invitation notification",
                    _mask_email(invitation.student_email)
                )
                return None
            
            # Get professor and cohort info
            professor_name = "A professor"
            if invitation.professor:
                professor_name = invitation.professor.full_name or invitation.professor.email
            
            cohort_title = "a cohort"
            if invitation.cohort:
                cohort_title = invitation.cohort.title
            
            variables = {
                "cohort_title": cohort_title,
                "professor_name": professor_name
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
        except Exception:
            logger.exception("Failed to create cohort invitation notification")
            return None
    
    def create_assignment_due_notification(
        self,
        student_id: int,
        assignment_title: str,
        due_date: datetime
    ) -> Optional[Notification]:
        """
        Create a notification for a student when an assignment is due soon.
        
        Args:
            student_id: The ID of the student to notify
            assignment_title: The title of the assignment
            due_date: The due date/time of the assignment
            
        Returns:
            The created Notification, or None if creation failed
        """
        try:
            # Format due date nicely
            formatted_due_date = due_date.strftime("%B %d, %Y at %I:%M %p")
            
            variables = {
                "assignment_title": assignment_title,
                "due_date": formatted_due_date
            }
            
            data = {
                "due_date": due_date.isoformat()
            }
            
            return self.create_templated_notification(
                user_id=student_id,
                notification_type=NotificationType.ASSIGNMENT_DUE,
                variables=variables,
                data=data
            )
        except Exception:
            logger.exception("Failed to create assignment due notification")
            return None
    
    def create_assignment_overdue_notification(
        self,
        student_id: int,
        assignment_title: str
    ) -> Optional[Notification]:
        """
        Create a notification for a student when an assignment is overdue.
        
        Args:
            student_id: The ID of the student to notify
            assignment_title: The title of the overdue assignment
            
        Returns:
            The created Notification, or None if creation failed
        """
        try:
            variables = {
                "assignment_title": assignment_title
            }
            
            return self.create_templated_notification(
                user_id=student_id,
                notification_type=NotificationType.ASSIGNMENT_OVERDUE,
                variables=variables
            )
        except Exception:
            logger.exception("Failed to create assignment overdue notification")
            return None
    
    def create_grade_posted_notification(
        self,
        student_id: int,
        assignment_title: str
    ) -> Optional[Notification]:
        """
        Create a notification for a student when their grade is posted.
        
        Args:
            student_id: The ID of the student to notify
            assignment_title: The title of the graded assignment
            
        Returns:
            The created Notification, or None if creation failed
        """
        try:
            variables = {
                "assignment_title": assignment_title
            }
            
            data = {
                "student_id": student_id
            }
            
            return self.create_templated_notification(
                user_id=student_id,
                notification_type=NotificationType.GRADE_POSTED,
                variables=variables,
                data=data
            )
        except Exception:
            logger.exception("Failed to create grade posted notification")
            return None
    
    def create_simulation_assignment_notification(
        self,
        student_id: int,
        simulation_title: str,
        cohort_title: str,
        cohort_simulation_id: Optional[int] = None,
        simulation_id: Optional[int] = None,
        cohort_id: Optional[int] = None,
        due_date: Optional[datetime] = None,
        is_required: bool = True
    ) -> Optional[Notification]:
        """
        Create a notification for a student when a simulation is assigned.
        
        Args:
            student_id: The ID of the student to notify
            simulation_title: The title of the simulation/scenario
            cohort_title: The title of the cohort
            cohort_simulation_id: Optional ID of the cohort simulation assignment
            simulation_id: Optional ID of the simulation/scenario
            cohort_id: Optional ID of the cohort
            due_date: Optional due date for the simulation
            is_required: Whether the simulation is required
            
        Returns:
            The created Notification, or None if creation failed
        """
        try:
            variables = {
                "simulation_title": simulation_title,
                "cohort_title": cohort_title
            }
            
            data = {
                "cohort_simulation_id": cohort_simulation_id,
                "simulation_id": simulation_id,
                "cohort_id": cohort_id,
                "due_date": due_date.isoformat() if due_date else None,
                "is_required": is_required
            }
            
            return self.create_templated_notification(
                user_id=student_id,
                notification_type=NotificationType.SIMULATION_ASSIGNED,
                variables=variables,
                data=data
            )
        except Exception:
            logger.exception("Failed to create simulation assignment notification")
            return None
    
    def create_professor_message_notification(
        self,
        professor: User,
        student: User,
        message_subject: str,
        cohort_id: Optional[int] = None
    ) -> Optional[Notification]:
        """
        Create a notification for a student when they receive a message from a professor.
        
        Args:
            professor: The professor User who sent the message
            student: The student User who should receive the notification
            message_subject: The subject of the message
            cohort_id: Optional cohort ID for context
            
        Returns:
            The created Notification, or None if creation failed
        """
        try:
            professor_name = professor.full_name or professor.email
            
            variables = {
                "professor_name": professor_name,
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
        except Exception:
            logger.exception("Failed to create professor message notification")
            return None
    
    def create_student_message_notification(
        self,
        student: User,
        professor: User,
        message_subject: str,
        cohort_id: Optional[int] = None
    ) -> Optional[Notification]:
        """
        Create a notification for a professor when they receive a new message from a student.
        
        Args:
            student: The student User who sent the message
            professor: The professor User who should receive the notification
            message_subject: The subject of the message
            cohort_id: Optional cohort ID for context
            
        Returns:
            The created Notification, or None if creation failed
        """
        try:
            student_name = student.full_name or student.email
            
            variables = {
                "student_name": student_name,
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
        except Exception:
            logger.exception("Failed to create student message notification")
            return None
    
    def create_student_reply_notification(
        self,
        student: User,
        professor: User,
        message_subject: str,
        cohort_id: Optional[int] = None
    ) -> Optional[Notification]:
        """
        Create a notification for a professor when a student replies to their message.
        
        Args:
            student: The student User who replied
            professor: The professor User who should receive the notification
            message_subject: The subject of the original message
            cohort_id: Optional cohort ID for context
            
        Returns:
            The created Notification, or None if creation failed
        """
        try:
            student_name = student.full_name or student.email
            
            variables = {
                "student_name": student_name,
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
        except Exception:
            logger.exception("Failed to create student reply notification")
            return None
    
    def create_cohort_update_notification(
        self,
        user_id: int,
        cohort_title: str,
        cohort_id: Optional[int] = None
    ) -> Optional[Notification]:
        """
        Create a notification for a user when a cohort is updated.
        
        Args:
            user_id: The ID of the user to notify
            cohort_title: The title of the updated cohort
            cohort_id: Optional cohort ID for data payload
            
        Returns:
            The created Notification, or None if creation failed
        """
        try:
            variables = {
                "cohort_title": cohort_title
            }
            
            data = {
                "cohort_id": cohort_id
            } if cohort_id else None
            
            return self.create_templated_notification(
                user_id=user_id,
                notification_type=NotificationType.COHORT_UPDATE,
                variables=variables,
                data=data
            )
        except Exception:
            logger.exception("Failed to create cohort update notification")
            return None
    
    # ==================== BULK NOTIFICATION METHODS ====================
    # These methods notify all students in a cohort at once
    
    def _get_cohort_students(self, cohort_id: int) -> List[User]:
        """
        Get all approved students in a cohort.
        
        This is a helper method used by bulk notification methods.
        
        Args:
            cohort_id: The ID of the cohort
            
        Returns:
            List of User objects for approved students in the cohort
        """
        return self.db.query(User).join(CohortStudent).filter(
            CohortStudent.cohort_id == cohort_id,
            CohortStudent.status == 'approved',
            User.role == 'student'
        ).all()
    
    def create_bulk_assignment_due_notifications(
        self,
        cohort_id: int,
        assignment_title: str,
        due_date: datetime
    ) -> int:
        """
        Create notifications for all students in a cohort about an assignment due date.
        
        Args:
            cohort_id: The ID of the cohort
            assignment_title: The title of the assignment
            due_date: The due date/time of the assignment
            
        Returns:
            The number of notifications successfully created
        """
        try:
            students = self._get_cohort_students(cohort_id)
            
            if not students:
                logger.info("No students found in cohort %d for assignment due notifications", cohort_id)
                return 0
            
            created_count = 0
            for student in students:
                notification = self.create_assignment_due_notification(
                    student_id=student.id,
                    assignment_title=assignment_title,
                    due_date=due_date
                )
                if notification:
                    created_count += 1
            
            logger.info(
                "Created %d/%d assignment due notifications for cohort %d",
                created_count, len(students), cohort_id
            )
            return created_count
            
        except Exception:
            logger.exception("Failed to create bulk assignment due notifications for cohort %d", cohort_id)
            return 0
    
    def create_bulk_assignment_overdue_notifications(
        self,
        cohort_id: int,
        assignment_title: str
    ) -> int:
        """
        Create notifications for all students in a cohort about an overdue assignment.
        
        Args:
            cohort_id: The ID of the cohort
            assignment_title: The title of the overdue assignment
            
        Returns:
            The number of notifications successfully created
        """
        try:
            students = self._get_cohort_students(cohort_id)
            
            if not students:
                logger.info("No students found in cohort %d for assignment overdue notifications", cohort_id)
                return 0
            
            created_count = 0
            for student in students:
                notification = self.create_assignment_overdue_notification(
                    student_id=student.id,
                    assignment_title=assignment_title
                )
                if notification:
                    created_count += 1
            
            logger.info(
                "Created %d/%d assignment overdue notifications for cohort %d",
                created_count, len(students), cohort_id
            )
            return created_count
            
        except Exception:
            logger.exception("Failed to create bulk assignment overdue notifications for cohort %d", cohort_id)
            return 0
    
    def create_bulk_grade_notifications(
        self,
        cohort_id: int,
        assignment_title: str
    ) -> int:
        """
        Create notifications for all students in a cohort that grades have been posted.
        
        Args:
            cohort_id: The ID of the cohort
            assignment_title: The title of the graded assignment
            
        Returns:
            The number of notifications successfully created
        """
        try:
            students = self._get_cohort_students(cohort_id)
            
            if not students:
                logger.info("No students found in cohort %d for grade notifications", cohort_id)
                return 0
            
            created_count = 0
            for student in students:
                notification = self.create_grade_posted_notification(
                    student_id=student.id,
                    assignment_title=assignment_title
                )
                if notification:
                    created_count += 1
            
            logger.info(
                "Created %d/%d grade posted notifications for cohort %d",
                created_count, len(students), cohort_id
            )
            return created_count
            
        except Exception:
            logger.exception("Failed to create bulk grade notifications for cohort %d", cohort_id)
            return 0
    
    def create_bulk_simulation_notifications(
        self,
        cohort_id: int,
        simulation_title: str,
        cohort_title: str,
        cohort_simulation_id: Optional[int] = None,
        simulation_id: Optional[int] = None,
        due_date: Optional[datetime] = None,
        is_required: bool = True
    ) -> int:
        """
        Create notifications for all students in a cohort when a simulation is assigned.
        
        Args:
            cohort_id: The ID of the cohort
            simulation_title: The title of the simulation/scenario
            cohort_title: The title of the cohort
            cohort_simulation_id: Optional ID of the cohort simulation assignment
            simulation_id: Optional ID of the simulation/scenario
            due_date: Optional due date for the simulation
            is_required: Whether the simulation is required
            
        Returns:
            The number of notifications successfully created
        """
        try:
            students = self._get_cohort_students(cohort_id)
            
            if not students:
                logger.info("No students found in cohort %d for simulation notifications", cohort_id)
                return 0
            
            created_count = 0
            for student in students:
                notification = self.create_simulation_assignment_notification(
                    student_id=student.id,
                    simulation_title=simulation_title,
                    cohort_title=cohort_title,
                    cohort_simulation_id=cohort_simulation_id,
                    simulation_id=simulation_id,
                    cohort_id=cohort_id,
                    due_date=due_date,
                    is_required=is_required
                )
                if notification:
                    created_count += 1
            
            logger.info(
                "Created %d/%d simulation assignment notifications for cohort %d",
                created_count, len(students), cohort_id
            )
            return created_count
            
        except Exception:
            logger.exception("Failed to create bulk simulation notifications for cohort %d", cohort_id)
            return 0
    
    def create_bulk_cohort_update_notifications(
        self,
        cohort_id: int,
        cohort_title: str
    ) -> int:
        """
        Create notifications for all students in a cohort when the cohort is updated.
        
        Args:
            cohort_id: The ID of the cohort
            cohort_title: The title of the cohort
            
        Returns:
            The number of notifications successfully created
        """
        try:
            students = self._get_cohort_students(cohort_id)
            
            if not students:
                logger.info("No students found in cohort %d for update notifications", cohort_id)
                return 0
            
            created_count = 0
            for student in students:
                notification = self.create_cohort_update_notification(
                    user_id=student.id,
                    cohort_title=cohort_title,
                    cohort_id=cohort_id
                )
                if notification:
                    created_count += 1
            
            logger.info(
                "Created %d/%d cohort update notifications for cohort %d",
                created_count, len(students), cohort_id
            )
            return created_count
            
        except Exception:
            logger.exception("Failed to create bulk cohort update notifications for cohort %d", cohort_id)
            return 0
    
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
        
        # Verify the invitation is for this student (case-insensitive email comparison)
        email_match = invitation.student_email.lower() == user.email.lower()
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
        
        # If accepted, check if the student exists in the system (case-insensitive)
        if action == 'accept':
            student = self.db.query(User).filter(
                func.lower(User.email) == invitation.student_email.lower(),
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
