"""
Student notification API endpoints
"""
import logging
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session

from common.db.core import get_db
from common.db.models import User
from app.dependencies import require_student
from modules.notifications.service import NotificationService
from modules.notifications.schemas import (
    NotificationResponse,
    NotificationListResponse,
    UnreadCountResponse,
    MarkReadResponse,
    InvitationActionRequest,
    InvitationsListResponse,
    InvitationRespondResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/student", tags=["Student Notifications"])


def get_notification_service(db: Session = Depends(get_db)) -> NotificationService:
    """Dependency to get notification service"""
    return NotificationService(db)


# ==================== INVITATION ENDPOINTS ====================

@router.get("/invitations", response_model=InvitationsListResponse)
async def get_pending_invitations(
    current_user: User = Depends(require_student),
    service: NotificationService = Depends(get_notification_service)
):
    """Get pending invitations for the current student"""
    invitations = service.get_pending_invitations(current_user)
    return {"invitations": invitations}


@router.post("/invitations/{invitation_id}/respond", response_model=InvitationRespondResponse)
async def respond_to_invitation(
    invitation_id: int,
    request_body: InvitationActionRequest,
    current_user: User = Depends(require_student),
    service: NotificationService = Depends(get_notification_service)
):
    """Respond to a cohort invitation (accept or decline)"""
    try:
        result = service.respond_to_invitation(invitation_id, request_body.action, current_user)
        return result
    except ValueError as e:
        status_code = status.HTTP_400_BAD_REQUEST
        if "not found" in str(e).lower():
            status_code = status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=status_code, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        ) from e


# ==================== NOTIFICATION ENDPOINTS ====================

@router.get("/notifications", response_model=NotificationListResponse)
async def get_notifications(
    limit: int = 50,
    offset: int = 0,
    unread_only: bool = False,
    current_user: User = Depends(require_student),
    service: NotificationService = Depends(get_notification_service)
):
    """Get notifications for the current student"""
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
    current_user: User = Depends(require_student),
    service: NotificationService = Depends(get_notification_service)
):
    """Get count of unread notifications"""
    count = service.get_unread_count(current_user.id)
    return {"unread_count": count}


@router.post("/notifications/{notification_id}/read", response_model=MarkReadResponse)
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(require_student),
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
    current_user: User = Depends(require_student),
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


# ==================== TOKEN-BASED INVITATION ENDPOINTS ====================
# These endpoints don't require authentication and are used from email links

@router.get("/invitations/{invitation_token}")
async def get_invitation_by_token(
    invitation_token: str,
    service: NotificationService = Depends(get_notification_service)
):
    """Get invitation details by token (for email links)"""
    try:
        return service.get_invitation_by_token(invitation_token)
    except ValueError as e:
        status_code = status.HTTP_400_BAD_REQUEST
        if "not found" in str(e).lower():
            status_code = status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=status_code, detail=str(e)) from e


@router.post("/invitations/{invitation_token}/respond", response_model=InvitationRespondResponse)
async def respond_to_invitation_by_token(
    invitation_token: str,
    request_body: InvitationActionRequest,
    service: NotificationService = Depends(get_notification_service)
):
    """Respond to invitation by token (for non-authenticated users)"""
    try:
        result = service.respond_to_invitation_by_token(invitation_token, request_body.action)
        return result
    except ValueError as e:
        status_code = status.HTTP_400_BAD_REQUEST
        if "not found" in str(e).lower():
            status_code = status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=status_code, detail=str(e)) from e
