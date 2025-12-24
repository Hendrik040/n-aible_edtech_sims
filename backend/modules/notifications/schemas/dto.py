"""
Notification API schemas (DTOs)
"""
from datetime import datetime
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    """Response schema for a notification"""
    id: int
    user_id: int
    type: str
    title: str
    message: str
    data: Optional[Dict[str, Any]] = None
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    """Response schema for list of notifications"""
    notifications: list[NotificationResponse]
    total: int


class UnreadCountResponse(BaseModel):
    """Response schema for unread notification count"""
    unread_count: int


class MarkReadResponse(BaseModel):
    """Response schema for marking notifications as read"""
    message: str


class InvitationActionRequest(BaseModel):
    """Request schema for responding to a cohort invitation"""
    action: Literal["accept", "decline"] = Field(
        ...,
        description="Action to take on the invitation: 'accept' or 'decline'"
    )


class CohortInfoResponse(BaseModel):
    """Cohort info included in invitation response"""
    id: int
    title: str
    description: Optional[str] = None
    course_code: Optional[str] = None


class InvitedByResponse(BaseModel):
    """Professor info who sent the invitation"""
    id: int
    full_name: str
    email: str


class InvitationDetailResponse(BaseModel):
    """Response schema for a cohort invitation with details"""
    id: int
    cohort_id: int
    professor_id: int
    student_email: str
    student_id: Optional[int] = None
    status: str
    message: Optional[str] = None
    expires_at: datetime
    created_at: datetime
    cohort: Optional[CohortInfoResponse] = None
    invited_by: Optional[InvitedByResponse] = None


class InvitationsListResponse(BaseModel):
    """Response schema for list of invitations"""
    invitations: list[InvitationDetailResponse]


class InvitationRespondResponse(BaseModel):
    """Response schema for invitation response action"""
    message: str
    action: str
    cohort_id: int
    requires_registration: bool = False


class CohortInvitationTokenResponse(BaseModel):
    """Response schema for invitation lookup by token"""
    invitation: InvitationDetailResponse
    cohort: CohortInfoResponse
    professor: InvitedByResponse
