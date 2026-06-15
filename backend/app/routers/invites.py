"""
Public invite router - Handles invite link validation and acceptance
"""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from common.db.core import get_db
from common.db.models import User, CohortInvite, Cohort, CohortStudent
from app.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/invites", tags=["Invites"])


class InviteInfoResponse(BaseModel):
    """Response for invite validation"""
    valid: bool
    invite_type: str
    max_uses: Optional[int]
    uses_count: int
    uses_left: Optional[int]
    expires_at: datetime
    is_expired: bool
    is_used_up: bool
    cohort: dict
    professor: dict


class AcceptInviteResponse(BaseModel):
    """Response for accepting an invite"""
    success: bool
    message: str
    cohort_id: int
    cohort_title: str
    already_enrolled: bool = False


@router.get("/{token}", response_model=InviteInfoResponse)
async def validate_invite(
    token: str,
    db: Session = Depends(get_db)
):
    """Validate an invite link and return cohort information (no auth required)"""
    try:
        # Find the invite by token
        invite = db.query(CohortInvite).filter(CohortInvite.token == token).first()
        
        if not invite:
            raise HTTPException(status_code=404, detail="Invalid or expired invite link")
        
        # Get the cohort
        cohort = db.query(Cohort).filter(Cohort.id == invite.cohort_id).first()
        if not cohort:
            raise HTTPException(status_code=404, detail="Cohort not found")
        
        # Get the professor (creator)
        professor = db.query(User).filter(User.id == cohort.created_by).first()
        
        # Check expiration
        now = datetime.now(timezone.utc)
        expires_at = invite.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        is_expired = expires_at < now
        
        # Calculate uses_left and is_used_up
        if invite.invite_type == "SINGLE_USE":
            is_used_up = invite.uses_count >= 1
            uses_left = 0 if is_used_up else 1
        else:
            if invite.max_uses is None:
                is_used_up = False
                uses_left = None  # Unlimited
            else:
                is_used_up = invite.uses_count >= invite.max_uses
                uses_left = max(0, invite.max_uses - invite.uses_count)
        
        # Check if invite is still valid
        if is_expired:
            raise HTTPException(status_code=410, detail="This invite link has expired")
        
        if is_used_up:
            raise HTTPException(status_code=410, detail="This invite link has been fully used")
        
        return InviteInfoResponse(
            valid=True,
            invite_type=invite.invite_type,
            max_uses=invite.max_uses,
            uses_count=invite.uses_count,
            uses_left=uses_left,
            expires_at=invite.expires_at,
            is_expired=is_expired,
            is_used_up=is_used_up,
            cohort={
                "id": cohort.id,
                "unique_id": cohort.unique_id,
                "title": cohort.title,
                "description": cohort.description,
                "course_code": cohort.course_code
            },
            professor={
                "id": professor.id if professor else None,
                "name": professor.full_name if professor else "Unknown"
                # NOTE: professor email intentionally omitted - this endpoint is
                # unauthenticated, so exposing PII (email) here is an info leak.
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating invite: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to validate invite link")


@router.post("/{token}/accept", response_model=AcceptInviteResponse)
async def accept_invite(
    token: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Accept an invite link and join the cohort (requires student authentication)"""
    try:
        # Only students can accept invites
        if current_user.role != "student":
            raise HTTPException(
                status_code=403, 
                detail="Only students can accept cohort invite links"
            )
        
        # Find the invite by token with row-level lock to prevent race conditions
        # SELECT FOR UPDATE ensures only one transaction can modify the invite at a time
        invite = db.query(CohortInvite).filter(
            CohortInvite.token == token
        ).with_for_update().first()
        
        if not invite:
            raise HTTPException(status_code=404, detail="Invalid or expired invite link")
        
        # Get the cohort
        cohort = db.query(Cohort).filter(Cohort.id == invite.cohort_id).first()
        if not cohort:
            raise HTTPException(status_code=404, detail="Cohort not found")
        
        # Check expiration
        now = datetime.now(timezone.utc)
        expires_at = invite.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        if expires_at < now:
            raise HTTPException(status_code=410, detail="This invite link has expired")
        
        # Check if used up
        if invite.invite_type == "SINGLE_USE" and invite.uses_count >= 1:
            raise HTTPException(status_code=410, detail="This invite link has already been used")
        
        if invite.invite_type == "MULTI_USE" and invite.max_uses is not None:
            if invite.uses_count >= invite.max_uses:
                raise HTTPException(status_code=410, detail="This invite link has been fully used")
        
        # Check if already enrolled
        existing_enrollment = db.query(CohortStudent).filter(
            CohortStudent.cohort_id == cohort.id,
            CohortStudent.student_id == current_user.id
        ).first()
        
        if existing_enrollment:
            return AcceptInviteResponse(
                success=True,
                message="You are already a member of this cohort",
                cohort_id=cohort.id,
                cohort_title=cohort.title,
                already_enrolled=True
            )
        
        # Create enrollment
        enrollment = CohortStudent(
            cohort_id=cohort.id,
            student_id=current_user.id,
            status="approved" if cohort.auto_approve else "pending"
        )
        db.add(enrollment)
        
        # Increment invite usage
        invite.uses_count += 1
        if invite.invite_type == "SINGLE_USE":
            invite.used_by = current_user.id
            invite.used_at = now
        
        db.commit()
        
        # Invalidate cache so student sees new cohort immediately
        from common.services.cache_service import redis_manager
        redis_manager.delete(f"student_cohorts:{current_user.id}")
        
        # If auto-approved, create simulation instances immediately (no waiting for backfill)
        if cohort.auto_approve:
            try:
                from modules.cohorts.service import CohortService
                cohort_service = CohortService(db)
                instances_created = cohort_service._create_simulation_instances_for_student(
                    cohort_id=cohort.id,
                    student_id=current_user.id
                )
                if instances_created > 0:
                    logger.info(f"Created {instances_created} simulation instances for user {current_user.id} in cohort {cohort.id}")
                
                # Commit the created simulation instances to persist them
                db.commit()
                
                # Invalidate simulation instances cache so student sees them immediately
                redis_manager.delete(f"student_instances:{current_user.id}:all:all")
                redis_manager.delete(f"missing_instances_check:{current_user.id}")
            except Exception as e:
                # Rollback to avoid leaving the session in a dirty state
                db.rollback()
                # Don't fail the invite acceptance if instance creation fails
                # The backfill will catch it later
                logger.warning(f"Failed to create simulation instances for user {current_user.id}: {e}")
        
        logger.info(f"User {current_user.id} joined cohort {cohort.id} via invite {invite.id}")
        
        status_msg = "approved" if cohort.auto_approve else "pending approval"
        return AcceptInviteResponse(
            success=True,
            message=f"Successfully joined cohort! Your status is: {status_msg}",
            cohort_id=cohort.id,
            cohort_title=cohort.title,
            already_enrolled=False
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error accepting invite: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to accept invite")
