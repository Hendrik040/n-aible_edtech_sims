"""
Professor notification API endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from typing import List

from database.connection import get_db
from database.models import User, Notification
from database.schemas import NotificationResponse
from middleware.role_auth import require_professor
from services.notification_service import notification_service

router = APIRouter(prefix="/professor", tags=["professor-notifications"])

@router.get("/notifications")
async def get_notifications(
    limit: int = 50,
    offset: int = 0,
    unread_only: bool = False,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get notifications for the current professor"""
    
    notifications = notification_service.get_user_notifications(
        db, current_user.id, limit=limit, offset=offset, unread_only=unread_only
    )
    
    return {
        "notifications": [NotificationResponse.from_orm(notif) for notif in notifications],
        "total": len(notifications)
    }

@router.get("/notifications/unread-count")
async def get_unread_notification_count(
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get count of unread notifications"""
    
    count = notification_service.get_unread_count(db, current_user.id)
    return {"unread_count": count}

@router.post("/notifications/{notification_id}/mark-read")
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Mark a notification as read"""
    
    success = notification_service.mark_notification_read(db, notification_id, current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    
    return {"message": "Notification marked as read"}

@router.post("/notifications/mark-all-read")
async def mark_all_notifications_read(
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Mark all notifications as read"""
    
    success = notification_service.mark_all_notifications_read(db, current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark notifications as read"
        )
    
    return {"message": "All notifications marked as read"}
