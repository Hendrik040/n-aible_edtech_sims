"""
Notification type constants and templates.

This module provides:
- NotificationType enum for all supported notification types
- NotificationPriority enum for notification importance levels
- NOTIFICATION_TEMPLATES dictionary with title/message templates
"""
from enum import Enum
from typing import Dict, Any


class NotificationType(str, Enum):
    """
    Enumeration of notification types.
    
    Each type corresponds to a specific event in the system that
    triggers a notification to be sent to a user.
    """
    # Cohort invitation notifications
    COHORT_INVITATION = "cohort_invitation"
    INVITATION_ACCEPTED = "invitation_accepted"
    INVITATION_DECLINED = "invitation_declined"
    
    # Assignment notifications
    ASSIGNMENT_DUE = "assignment_due"
    ASSIGNMENT_OVERDUE = "assignment_overdue"
    
    # Grade notifications
    GRADE_POSTED = "grade_posted"
    
    # Cohort notifications
    COHORT_UPDATE = "cohort_update"
    
    # Simulation notifications
    SIMULATION_ASSIGNED = "simulation_assigned"
    
    # Messaging notifications
    PROFESSOR_MESSAGE = "professor_message"
    STUDENT_REPLY = "student_reply"
    STUDENT_MESSAGE = "student_message"
    MESSAGE_SENT = "message_sent"


class NotificationPriority(str, Enum):
    """
    Priority levels for notifications.
    
    Used to determine display order and visual emphasis in the UI.
    """
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# Type alias for template structure
NotificationTemplate = Dict[str, Any]

NOTIFICATION_TEMPLATES: Dict[NotificationType, NotificationTemplate] = {
    # ==================== COHORT INVITATION NOTIFICATIONS ====================
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
    
    # ==================== ASSIGNMENT NOTIFICATIONS ====================
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
    
    # ==================== GRADE NOTIFICATIONS ====================
    NotificationType.GRADE_POSTED: {
        "title_template": "Grade Posted",
        "message_template": 'Your grade for "{assignment_title}" is now available',
        "priority": NotificationPriority.MEDIUM
    },
    
    # ==================== COHORT NOTIFICATIONS ====================
    NotificationType.COHORT_UPDATE: {
        "title_template": "Cohort Updated",
        "message_template": 'The cohort "{cohort_title}" has been updated',
        "priority": NotificationPriority.LOW
    },
    
    # ==================== SIMULATION NOTIFICATIONS ====================
    NotificationType.SIMULATION_ASSIGNED: {
        "title_template": "New Simulation Assigned",
        "message_template": 'A new simulation "{simulation_title}" has been assigned to your cohort "{cohort_title}"',
        "priority": NotificationPriority.HIGH
    },
    
    # ==================== MESSAGING NOTIFICATIONS ====================
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
    },
}


def get_template(notification_type: NotificationType) -> NotificationTemplate:
    """
    Get the template for a notification type.
    
    Args:
        notification_type: The type of notification
        
    Returns:
        The template dictionary containing title_template, message_template, and priority
        
    Raises:
        KeyError: If the notification type is not found in templates
    """
    return NOTIFICATION_TEMPLATES[notification_type]


def format_notification(
    notification_type: NotificationType,
    variables: Dict[str, Any]
) -> Dict[str, str]:
    """
    Format a notification title and message using the template and variables.
    
    Args:
        notification_type: The type of notification
        variables: Dictionary of variables to substitute into the templates
        
    Returns:
        Dictionary with 'title' and 'message' keys
        
    Raises:
        KeyError: If notification type not found or required variable is missing
    """
    template = get_template(notification_type)
    return {
        "title": template["title_template"].format(**variables),
        "message": template["message_template"].format(**variables),
        "priority": template["priority"].value
    }




