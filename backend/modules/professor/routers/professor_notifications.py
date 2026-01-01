"""
Professor notifications router - Endpoints for professor notification operations
Returns empty list for now as notifications feature is not yet implemented
"""
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, Query
from common.db.models import User
from app.dependencies import require_professor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/professor", tags=["Professor Notifications"])


@router.get("/notifications", response_model=Dict[str, Any])
async def get_notifications(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
    current_user: User = Depends(require_professor)
):
    """
    Get notifications for the current professor.
    
    Currently returns an empty list as notifications feature is pending implementation.
    This prevents 404 errors from the frontend.
    """
    logger.debug(f"[NOTIFICATIONS] Getting notifications for user {current_user.id} (limit={limit}, offset={offset}, unread_only={unread_only})")
    
    return {
        "notifications": [],
        "total": 0,
        "unread_count": 0,
        "limit": limit,
        "offset": offset
    }


@router.get("/notifications/unread-count", response_model=Dict[str, int])
async def get_unread_count(
    current_user: User = Depends(require_professor)
):
    """
    Get count of unread notifications.
    
    Currently returns 0 as notifications feature is pending implementation.
    """
    return {"count": 0}


@router.post("/notifications/{notification_id}/read", response_model=Dict[str, bool])
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(require_professor)
):
    """
    Mark a notification as read.
    
    Currently a no-op as notifications feature is pending implementation.
    """
    logger.debug(f"[NOTIFICATIONS] Marking notification {notification_id} as read for user {current_user.id}")
    return {"success": True}


@router.post("/notifications/mark-all-read", response_model=Dict[str, bool])
async def mark_all_read(
    current_user: User = Depends(require_professor)
):
    """
    Mark all notifications as read.
    
    Currently a no-op as notifications feature is pending implementation.
    """
    logger.debug(f"[NOTIFICATIONS] Marking all notifications as read for user {current_user.id}")
    return {"success": True}


