"""
Professor notification API endpoints
"""
import logging
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session

from common.db.core import get_db
from common.db.models import User
from app.dependencies import require_professor
from modules.notifications.service import NotificationService
from modules.notifications.schemas import (
    NotificationResponse,
    NotificationListResponse,
    UnreadCountResponse,
    MarkReadResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/professor", tags=["Professor Notifications"])


def get_notification_service(db: Session = Depends(get_db)) -> NotificationService:
    """Dependency to get notification service"""
    return NotificationService(db)


@router.get("/notifications", response_model=NotificationListResponse)
async def get_notifications(
    limit: int = 50,
    offset: int = 0,
    unread_only: bool = False,
    current_user: User = Depends(require_professor),
    service: NotificationService = Depends(get_notification_service)
):
    """Get notifications for the current professor"""
    notifications = service.get_user_notifications(
        current_user.id, limit=limit, offset=offset, unread_only=unread_only
    )
    
    # Get actual total count for pagination
    total = service.get_total_notifications_count(current_user.id, unread_only=unread_only)
    
    return {
        "notifications": [NotificationResponse.model_validate(notif) for notif in notifications],
        "total": total
    }


@router.get("/notifications/unread-count", response_model=UnreadCountResponse)
async def get_unread_notification_count(
    current_user: User = Depends(require_professor),
    service: NotificationService = Depends(get_notification_service)
):
    """Get count of unread notifications"""
    count = service.get_unread_count(current_user.id)
    return {"unread_count": count}


@router.post("/notifications/{notification_id}/mark-read", response_model=MarkReadResponse)
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(require_professor),
    service: NotificationService = Depends(get_notification_service)
):
    """Mark a notification as read"""
    success = service.mark_notification_read(notification_id, current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    
    return {"message": "Notification marked as read"}


@router.post("/notifications/mark-all-read", response_model=MarkReadResponse)
async def mark_all_notifications_read(
    current_user: User = Depends(require_professor),
    service: NotificationService = Depends(get_notification_service)
):
    """Mark all notifications as read"""
    success = service.mark_all_notifications_read(current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark notifications as read"
        )
    
    return {"message": "All notifications marked as read"}

