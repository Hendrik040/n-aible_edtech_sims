"""
Notifications module for in-app notifications and cohort invitations.

This module provides:
- In-app notifications for professors and students
- Cohort invitation management
- Notification read/unread tracking
- Templated notification creation with predefined types
"""
from .router import router
from .service import NotificationService
from .repository import NotificationRepository, InvitationRepository
from .constants import (
    NotificationType,
    NotificationPriority,
    NOTIFICATION_TEMPLATES,
    format_notification,
    get_template,
)

__all__ = [
    # Repository classes
    "InvitationRepository",
    "NotificationRepository",
    # Service class
    "NotificationService",
    # Router
    "router",
    # Constants and utilities
    "NotificationType",
    "NotificationPriority",
    "NOTIFICATION_TEMPLATES",
    "format_notification",
    "get_template",
]

