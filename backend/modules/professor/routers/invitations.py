"""
Professor invitation API endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, status, Request
from sqlalchemy.orm import Session, joinedload
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
import logging
import hashlib
import os

from database.connection import get_db
from database.models import User, Cohort, CohortInvitation, CohortInvite, CohortStudent
from database.schemas import (
    StudentInvitation, 
    CohortInvitationResponse,
    UserResponse
)
from middleware.role_auth import require_professor
from common.utils.id_generator import generate_invitation_token, generate_invite_link_token
from services.email_service import email_service
from services.notification_service import notification_service
from common.utils.redis_manager import redis_manager
from common.utils.rate_limiter import rate_limiter, RateLimitConfig
from common.utils.auth import get_current_user_optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/professor", tags=["professor-invitations"])

# Public router for invite link endpoints (no auth required initially)
# This will be exported and added to main.py separately
public_router = APIRouter(tags=["invite-links"])

# Rate limiting config for invite link generation
INVITE_GENERATE_CONFIG = RateLimitConfig(
    max_requests=10,  # 10 invite links per hour per professor
    window_seconds=3600,
    key_prefix="invite_generate"
)

@router.post("/cohorts/{cohort_id}/invite")
async def invite_students_to_cohort(
    cohort_id: int,
    invitations: List[StudentInvitation],
    request: Request,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Invite students to a cohort by email"""
    
    # Verify cohort ownership
    cohort = db.query(Cohort).filter(
        Cohort.id == cohort_id,
        Cohort.created_by == current_user.id
    ).first()
    
    if not cohort:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cohort not found or you don't have permission to invite students"
        )
    
    # Check cohort capacity (only if max_students is set)
    if cohort.max_students is not None:
        current_enrollment = db.query(CohortInvitation).filter(
            CohortInvitation.cohort_id == cohort_id,
            CohortInvitation.status.in_(['pending', 'accepted'])
        ).count()
        
        if current_enrollment + len(invitations) > cohort.max_students:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cohort capacity exceeded. Current: {current_enrollment}, Requested: {len(invitations)}, Max: {cohort.max_students}"
            )
    
    created_invitations = []
    base_url = str(request.base_url).rstrip('/')
    
    for invitation_data in invitations:
        try:
            # Check if invitation already exists
            existing_invitation = db.query(CohortInvitation).filter(
                CohortInvitation.cohort_id == cohort_id,
                CohortInvitation.student_email == invitation_data.email,
                CohortInvitation.status == 'pending'
            ).first()
            
            if existing_invitation:
                logger.info(f"Invitation already exists for {invitation_data.email} to cohort {cohort_id}")
                continue
            
            # Check if user already enrolled
            existing_student = db.query(User).filter(
                User.email == invitation_data.email,
                User.role == 'student'
            ).first()
            
            if existing_student:
                # Check if already enrolled in this cohort
                from database.models import CohortStudent
                existing_enrollment = db.query(CohortStudent).filter(
                    CohortStudent.cohort_id == cohort_id,
                    CohortStudent.student_id == existing_student.id,
                    CohortStudent.status == 'approved'
                ).first()
                
                if existing_enrollment:
                    logger.info(f"Student {invitation_data.email} already enrolled in cohort {cohort_id}")
                    continue
            
            # Create invitation
            invitation = CohortInvitation(
                cohort_id=cohort_id,
                professor_id=current_user.id,
                student_email=invitation_data.email,
                student_id=existing_student.id if existing_student else None,
                invitation_token=generate_invitation_token(),
                message=invitation_data.message,
                expires_at=datetime.now(timezone.utc) + timedelta(days=7)  # 7 days expiry
            )
            
            db.add(invitation)
            db.commit()
            db.refresh(invitation)
            
            # Send email notification
            try:
                await email_service.send_cohort_invitation(db, invitation, base_url)
                logger.info(f"Email invitation sent to {invitation_data.email}")
            except Exception as e:
                logger.error(f"Failed to send email to {invitation_data.email}: {str(e)}")
            
            # Create in-app notification (if student exists)
            if existing_student:
                try:
                    notification_service.create_cohort_invitation_notification(db, invitation)
                except Exception as e:
                    logger.error(f"Failed to create notification for {invitation_data.email}: {str(e)}")
            
            created_invitations.append(invitation)
            
        except Exception as e:
            logger.error(f"Failed to create invitation for {invitation_data.email}: {str(e)}")
            db.rollback()
            continue
    
    # Build response manually to avoid ORM relationship issues
    invitation_responses = []
    for inv in created_invitations:
        invitation_responses.append({
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
                "id": cohort.id,
                "title": cohort.title,
                "unique_id": cohort.unique_id
            } if cohort else None,
            "invited_by": {
                "id": current_user.id,
                "name": current_user.full_name,
                "email": current_user.email
            }
        })
    
    return {
        "message": f"Successfully sent {len(created_invitations)} invitations",
        "invitations": invitation_responses
    }

@router.get("/invitations/sent")
async def get_sent_invitations(
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get all invitations sent by the professor"""
    
    invitations = db.query(CohortInvitation).filter(
        CohortInvitation.professor_id == current_user.id
    ).options(
        joinedload(CohortInvitation.cohort)
    ).order_by(CohortInvitation.created_at.desc()).all()
    
    # Build response manually to avoid ORM relationship issues
    invitation_responses = []
    for inv in invitations:
        cohort = inv.cohort
        
        invitation_responses.append({
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
                "id": cohort.id,
                "title": cohort.title,
                "unique_id": cohort.unique_id
            } if cohort else None,
            "invited_by": {
                "id": current_user.id,
                "name": current_user.full_name,
                "email": current_user.email
            }
        })
    
    return {
        "invitations": invitation_responses
    }

@router.get("/cohorts/{cohort_id}/invitations")
async def get_cohort_invitations(
    cohort_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get all invitations for a specific cohort"""
    
    # Verify cohort ownership
    cohort = db.query(Cohort).filter(
        Cohort.id == cohort_id,
        Cohort.created_by == current_user.id
    ).first()
    
    if not cohort:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cohort not found or you don't have permission to view invitations"
        )
    
    invitations = db.query(CohortInvitation).filter(
        CohortInvitation.cohort_id == cohort_id
    ).options(
        joinedload(CohortInvitation.professor)
    ).order_by(CohortInvitation.created_at.desc()).all()
    
    # Build response manually to avoid ORM relationship issues
    invitation_responses = []
    for inv in invitations:
        # Use eagerly loaded professor relationship instead of N+1 query
        professor = inv.professor
        
        invitation_responses.append({
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
                "id": cohort.id,
                "title": cohort.title,
                "unique_id": cohort.unique_id
            },
            "invited_by": {
                "id": professor.id,
                "name": professor.full_name,
                "email": professor.email
            } if professor else None
        })
    
    return {
        "cohort": {
            "id": cohort.id,
            "title": cohort.title,
            "max_students": cohort.max_students
        },
        "invitations": invitation_responses
    }

@router.delete("/invitations/{invitation_id}")
async def cancel_invitation(
    invitation_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Cancel a pending invitation"""
    
    invitation = db.query(CohortInvitation).filter(
        CohortInvitation.id == invitation_id,
        CohortInvitation.professor_id == current_user.id,
        CohortInvitation.status == 'pending'
    ).first()
    
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found or cannot be cancelled"
        )
    
    invitation.status = 'expired'
    db.commit()
    
    logger.info(f"Cancelled invitation {invitation_id} by professor {current_user.id}")
    
    return {"message": "Invitation cancelled successfully"}

@router.post("/invitations/{invitation_id}/resend")
async def resend_invitation(
    invitation_id: int,
    request: Request,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Resend an invitation email"""
    
    invitation = db.query(CohortInvitation).filter(
        CohortInvitation.id == invitation_id,
        CohortInvitation.professor_id == current_user.id,
        CohortInvitation.status.in_(['pending', 'expired'])
    ).first()
    
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found or cannot be resent"
        )
    
    # Reset expiration
    invitation.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    invitation.status = 'pending'
    db.commit()
    
    # Resend email
    base_url = str(request.base_url).rstrip('/')
    try:
        await email_service.send_cohort_invitation(db, invitation, base_url)
        logger.info(f"Resent invitation email for invitation {invitation_id}")
    except Exception as e:
        logger.error(f"Failed to resend email for invitation {invitation_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resend invitation email"
        )
    
    return {"message": "Invitation resent successfully"}

@router.get("/cohorts/{cohort_id}/enrollment-stats")
async def get_cohort_enrollment_stats(
    cohort_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get enrollment statistics for a cohort"""
    
    # Verify cohort ownership
    cohort = db.query(Cohort).filter(
        Cohort.id == cohort_id,
        Cohort.created_by == current_user.id
    ).first()
    
    if not cohort:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cohort not found or you don't have permission to view stats"
        )
    
    # Count invitations by status
    stats = db.query(
        CohortInvitation.status,
        db.func.count(CohortInvitation.id)
    ).filter(
        CohortInvitation.cohort_id == cohort_id
    ).group_by(CohortInvitation.status).all()
    
    status_counts = {status: count for status, count in stats}
    
    # Get recent activity
    recent_invitations = db.query(CohortInvitation).filter(
        CohortInvitation.cohort_id == cohort_id
    ).order_by(CohortInvitation.updated_at.desc()).limit(10).all()
    
    # Build response manually to avoid ORM relationship issues
    recent_activity = []
    for inv in recent_invitations:
        recent_activity.append({
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
                "id": cohort.id,
                "title": cohort.title,
                "unique_id": cohort.unique_id
            },
            "invited_by": {
                "id": current_user.id,
                "name": current_user.full_name,
                "email": current_user.email
            }
        })
    
    return {
        "cohort": {
            "id": cohort.id,
            "title": cohort.title,
            "max_students": cohort.max_students
        },
        "enrollment_stats": {
            "pending": status_counts.get('pending', 0),
            "accepted": status_counts.get('accepted', 0),
            "declined": status_counts.get('declined', 0),
            "expired": status_counts.get('expired', 0),
            "total_invitations": sum(status_counts.values()),
            "available_spots": max(
                0,
                cohort.max_students
                - status_counts.get('pending', 0)
                - status_counts.get('accepted', 0)
            ) if cohort.max_students is not None else None
        },
        "recent_activity": recent_activity
    }


# ============================================================================
# Invite Link Endpoints
# ============================================================================

@router.get("/cohorts/{cohort_id}/invites")
async def get_cohort_invite_links(
    cohort_id: int,
    request: Request,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get all invite links for a cohort"""
    
    # Verify cohort ownership
    cohort = db.query(Cohort).filter(
        Cohort.id == cohort_id,
        Cohort.created_by == current_user.id
    ).first()
    
    if not cohort:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cohort not found or you don't have permission to view invite links"
        )
    
    # Get all invites for this cohort
    invites = db.query(CohortInvite).filter(
        CohortInvite.cohort_id == cohort_id
    ).order_by(CohortInvite.created_at.desc()).all()
    
    # Get frontend URL from environment variable or request origin
    # Use FRONTEND_URL env var first, then check request origin header, fallback to request base_url
    frontend_url = os.getenv('FRONTEND_URL') or os.getenv('FRONTEND_BASE_URL')
    if not frontend_url:
        # Try to get from request origin (when proxied through Next.js)
        origin = request.headers.get('origin') or request.headers.get('referer')
        if origin:
            # Extract base URL from origin/referer
            frontend_url = origin.split('/api/')[0] if '/api/' in origin else origin
        else:
            # Fallback to request base_url (might be backend URL, but better than nothing)
            frontend_url = str(request.base_url).rstrip('/')
    
    # Remove trailing slash
    frontend_url = frontend_url.rstrip('/')
    
    # Build response with full URLs
    invite_responses = []
    for invite in invites:
        # Skip invites without tokens (shouldn't happen, but handle gracefully)
        if not invite.token:
            logger.warning(f"Invite {invite.id} is missing token, skipping")
            continue
        
        # Check if expired or used (use timezone-aware datetime for comparison)
        now = datetime.now(timezone.utc)
        is_expired = invite.expires_at < now
        is_used_up = False
        uses_left = None
        
        if invite.invite_type == "SINGLE_USE":
            is_used_up = invite.used_by is not None
            uses_left = 0 if is_used_up else 1
        elif invite.invite_type == "MULTI_USE":
            if invite.max_uses is not None:
                uses_left = max(0, invite.max_uses - invite.uses_count)
                is_used_up = uses_left == 0
            else:
                uses_left = None  # Unlimited
                is_used_up = False
        
        # Build URL from stored token (use frontend URL for invite links)
        invite_url = f"{frontend_url}/invite/{invite.token}"
        
        invite_responses.append({
            "invite_id": invite.id,
            "invite_url": invite_url,
            "token": invite.token,
            "invite_type": invite.invite_type,
            "max_uses": invite.max_uses,
            "uses_count": invite.uses_count,
            "uses_left": uses_left,
            "expires_at": invite.expires_at.isoformat(),
            "created_at": invite.created_at.isoformat(),
            "is_expired": is_expired,
            "is_used_up": is_used_up,
            "status": "expired" if is_expired else ("used" if is_used_up else "active")
        })
    
    return {
        "cohort": {
            "id": cohort.id,
            "title": cohort.title,
            "unique_id": cohort.unique_id
        },
        "invites": invite_responses
    }


@router.delete("/cohorts/{cohort_id}/invites/clear-expired")
async def clear_expired_and_used_invites(
    cohort_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Delete all expired or used up invite links for a cohort"""
    
    # Verify cohort ownership
    cohort = db.query(Cohort).filter(
        Cohort.id == cohort_id,
        Cohort.created_by == current_user.id
    ).first()
    
    if not cohort:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cohort not found or you don't have permission to delete invite links"
        )
    
    # Get current time for expiration check
    now = datetime.now(timezone.utc)
    
    # Find all invites for this cohort that are expired or used up
    all_invites = db.query(CohortInvite).filter(
        CohortInvite.cohort_id == cohort_id
    ).all()
    
    invites_to_delete = []
    cache_keys_to_delete = []
    
    for invite in all_invites:
        should_delete = False
        
        # Check if expired
        if invite.expires_at < now:
            should_delete = True
        
        # Check if used up
        elif invite.invite_type == "SINGLE_USE" and invite.used_by is not None:
            should_delete = True
        elif invite.invite_type == "MULTI_USE" and invite.max_uses is not None:
            if invite.uses_count >= invite.max_uses:
                should_delete = True
        
        if should_delete:
            invites_to_delete.append(invite)
            if invite.token_hash:
                cache_keys_to_delete.append(f"invite_validate:{invite.token_hash}")
    
    # Delete the invites
    deleted_count = 0
    for invite in invites_to_delete:
        db.delete(invite)
        deleted_count += 1
    
    if deleted_count > 0:
        db.commit()
        
        # Invalidate cache for deleted invites
        for cache_key in cache_keys_to_delete:
            redis_manager.delete(cache_key)
        
        logger.info(f"Deleted {deleted_count} expired/used invite links for cohort {cohort_id} by professor {current_user.id}")
    
    return {
        "message": f"Cleared {deleted_count} expired or used invite link(s)",
        "deleted_count": deleted_count
    }


@router.delete("/cohorts/{cohort_id}/invites/{invite_id}")
async def delete_invite_link(
    cohort_id: int,
    invite_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Delete an invite link for a cohort"""
    
    # Verify cohort ownership
    cohort = db.query(Cohort).filter(
        Cohort.id == cohort_id,
        Cohort.created_by == current_user.id
    ).first()
    
    if not cohort:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cohort not found or you don't have permission to delete invite links"
        )
    
    # Get the invite and verify it belongs to this cohort
    invite = db.query(CohortInvite).filter(
        CohortInvite.id == invite_id,
        CohortInvite.cohort_id == cohort_id
    ).first()
    
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite link not found"
        )
    
    # Delete the invite
    db.delete(invite)
    db.commit()
    
    # Invalidate any cached validation data for this invite
    token_hash = invite.token_hash
    cache_key = f"invite_validate:{token_hash}"
    redis_manager.delete(cache_key)
    
    logger.info(f"Deleted invite link {invite_id} for cohort {cohort_id} by professor {current_user.id}")
    
    return {"message": "Invite link deleted successfully"}


@router.post("/cohorts/{cohort_id}/invites")
async def generate_invite_link(
    cohort_id: int,
    request: Request,
    invite_data: Dict[str, Any],
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Generate a shareable invite link for a cohort"""
    
    # Rate limiting
    rate_limit_result = rate_limiter.check_rate_limit(request, f"invite_generate_{current_user.id}", INVITE_GENERATE_CONFIG)
    if not rate_limit_result.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many invite links generated. Please wait {rate_limit_result.retry_after} seconds."
        )
    
    # Verify cohort ownership
    cohort = db.query(Cohort).filter(
        Cohort.id == cohort_id,
        Cohort.created_by == current_user.id
    ).first()
    
    if not cohort:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cohort not found or you don't have permission to create invite links"
        )
    
    # Parse invite data
    invite_type = invite_data.get("type", "SINGLE_USE")
    if invite_type not in ["SINGLE_USE", "MULTI_USE"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invite type must be 'SINGLE_USE' or 'MULTI_USE'"
        )
    
    max_uses = invite_data.get("max_uses")
    if invite_type == "MULTI_USE" and max_uses is not None and max_uses < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="max_uses must be at least 1 for MULTI_USE invites"
        )
    
    expires_in_days = invite_data.get("expires_in_days", 7)
    if expires_in_days < 1 or expires_in_days > 90:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="expires_in_days must be between 1 and 90"
        )
    
    # Generate token and hash
    token = generate_invite_link_token()
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    # Check for hash collision (unlikely but possible)
    existing_invite = db.query(CohortInvite).filter(CohortInvite.token_hash == token_hash).first()
    if existing_invite:
        # Retry once
        token = generate_invite_link_token()
        token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    # Create invite record
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
    invite = CohortInvite(
        cohort_id=cohort_id,
        token=token,  # Store original token for URL reconstruction
        token_hash=token_hash,
        invite_type=invite_type,
        max_uses=max_uses,
        uses_count=0,
        expires_at=expires_at,
        created_by=current_user.id
    )
    
    db.add(invite)
    db.commit()
    db.refresh(invite)
    
    # Get frontend URL from environment variable or request origin
    # Use FRONTEND_URL env var first, then check request origin header, fallback to request base_url
    frontend_url = os.getenv('FRONTEND_URL') or os.getenv('FRONTEND_BASE_URL')
    if not frontend_url:
        # Try to get from request origin (when proxied through Next.js)
        origin = request.headers.get('origin') or request.headers.get('referer')
        if origin:
            # Extract base URL from origin/referer
            frontend_url = origin.split('/api/')[0] if '/api/' in origin else origin
        else:
            # Fallback to request base_url (might be backend URL, but better than nothing)
            frontend_url = str(request.base_url).rstrip('/')
    
    # Remove trailing slash
    frontend_url = frontend_url.rstrip('/')
    
    # Build invite URL (use frontend URL for invite links)
    invite_url = f"{frontend_url}/invite/{token}"
    
    logger.info(f"Generated invite link for cohort {cohort_id} by professor {current_user.id}")
    
    return {
        "invite_id": invite.id,
        "invite_url": invite_url,
        "token": token,  # Return token only once - it's needed to build the URL
        "invite_type": invite_type,
        "max_uses": max_uses,
        "uses_count": 0,
        "uses_left": None if invite_type == "MULTI_USE" and max_uses is None else (max_uses if invite_type == "MULTI_USE" else 1),
        "expires_at": expires_at.isoformat(),
        "created_at": invite.created_at.isoformat(),
        "cohort": {
            "id": cohort.id,
            "title": cohort.title,
            "unique_id": cohort.unique_id
        }
    }


@public_router.get("/invites/{token}")
async def validate_invite_link(
    token: str,
    db: Session = Depends(get_db)
):
    """Validate an invite link and return cohort information"""
    
    # Hash the token
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    # Check Redis cache first
    cache_key = f"invite_validate:{token_hash}"
    cached_data = redis_manager.get(cache_key)
    if cached_data:
        logger.debug(f"Cache hit for invite validation: {token_hash[:8]}...")
        return cached_data
    
    # Query database
    invite = db.query(CohortInvite).filter(CohortInvite.token_hash == token_hash).first()
    
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite link not found or invalid"
        )
    
    # Check expiration
    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This invite link has expired"
        )
    
    # Check usage limits
    if invite.invite_type == "SINGLE_USE" and invite.used_by is not None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This invite link has already been used"
        )
    
    if invite.invite_type == "MULTI_USE" and invite.max_uses is not None:
        if invite.uses_count >= invite.max_uses:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="This invite link has reached its maximum usage limit"
            )
    
    # Load cohort and professor information
    cohort = invite.cohort
    professor = invite.creator
    
    response_data = {
        "valid": True,
        "cohort": {
            "id": cohort.id,
            "title": cohort.title,
            "description": cohort.description,
            "unique_id": cohort.unique_id
        },
        "professor": {
            "id": professor.id,
            "name": professor.full_name,
            "email": professor.email
        },
        "invite_type": invite.invite_type,
        "uses_left": None,
        "expires_at": invite.expires_at.isoformat()
    }
    
    if invite.invite_type == "MULTI_USE" and invite.max_uses is not None:
        response_data["uses_left"] = invite.max_uses - invite.uses_count
    elif invite.invite_type == "SINGLE_USE":
        response_data["uses_left"] = 1 if invite.used_by is None else 0
    
    # Cache the result until expiry (with a small buffer)
    ttl = int((invite.expires_at - datetime.now(timezone.utc)).total_seconds())
    if ttl > 0:
        redis_manager.set(cache_key, response_data, min(ttl, 3600))  # Cache for up to 1 hour
    
    return response_data


@public_router.post("/invites/{token}/accept")
async def accept_invite_link(
    token: str,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Accept an invite link to join a cohort"""
    
    # User must be authenticated
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="You must be logged in to accept an invite link"
        )
    
    # User must be a student
    if current_user.role != "student":
        # Invalidate cache
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        cache_key = f"invite_validate:{token_hash}"
        redis_manager.delete(cache_key)
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can accept cohort invite links. Professors cannot join cohorts as students."
        )
    
    # Hash the token
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    # Query database
    invite = db.query(CohortInvite).filter(CohortInvite.token_hash == token_hash).first()
    
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite link not found or invalid"
        )
    
    # Check expiration
    if invite.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This invite link has expired"
        )
    
    # Check usage limits
    if invite.invite_type == "SINGLE_USE":
        if invite.used_by is not None:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="This invite link has already been used"
            )
    
    if invite.invite_type == "MULTI_USE" and invite.max_uses is not None:
        if invite.uses_count >= invite.max_uses:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="This invite link has reached its maximum usage limit"
            )
    
    # Check if student is already enrolled
    existing_enrollment = db.query(CohortStudent).filter(
        CohortStudent.cohort_id == invite.cohort_id,
        CohortStudent.student_id == current_user.id
    ).first()
    
    if existing_enrollment:
        if existing_enrollment.status == 'approved':
            # Invalidate cache to ensure fresh data
            cache_key = f"invite_validate:{token_hash}"
            redis_manager.delete(cache_key)
            
            # Return success message but indicate already enrolled
            return {
                "message": "You are already enrolled in this cohort",
                "already_enrolled": True,
                "cohort": {
                    "id": invite.cohort.id,
                    "title": invite.cohort.title,
                    "unique_id": invite.cohort.unique_id
                }
            }
        elif existing_enrollment.status == 'pending':
            # Approve the pending enrollment
            existing_enrollment.status = 'approved'
            existing_enrollment.approved_by = invite.created_by
            existing_enrollment.approved_at = datetime.now(timezone.utc)
            db.commit()
            
            # Update invite usage
            if invite.invite_type == "SINGLE_USE":
                invite.used_by = current_user.id
                invite.used_at = datetime.now(timezone.utc)
                invite.uses_count = 1  # Mark as used for display purposes
            else:
                invite.uses_count += 1
            
            db.commit()
            
            # Invalidate cache
            cache_key = f"invite_validate:{token_hash}"
            redis_manager.delete(cache_key)
            
            return {
                "message": "Successfully joined cohort",
                "cohort": {
                    "id": invite.cohort.id,
                    "title": invite.cohort.title,
                    "unique_id": invite.cohort.unique_id
                }
            }
    
    # Create new enrollment
    enrollment_status = 'approved' if invite.cohort.auto_approve else 'pending'
    enrollment = CohortStudent(
        cohort_id=invite.cohort_id,
        student_id=current_user.id,
        status=enrollment_status,
        approved_by=invite.created_by if enrollment_status == 'approved' else None,
        approved_at=datetime.now(timezone.utc) if enrollment_status == 'approved' else None
    )
    
    db.add(enrollment)
    
    # Update invite usage
    if invite.invite_type == "SINGLE_USE":
        invite.used_by = current_user.id
        invite.used_at = datetime.now(timezone.utc)
        invite.uses_count = 1  # Mark as used for display purposes
    else:
        invite.uses_count += 1
    
    db.commit()
    
    # Invalidate cache
    cache_key = f"invite_validate:{token_hash}"
    redis_manager.delete(cache_key)
    
    logger.info(f"Student {current_user.id} accepted invite link for cohort {invite.cohort_id}")
    
    return {
        "message": f"Successfully joined cohort. {'Approval pending.' if enrollment_status == 'pending' else 'You are now enrolled.'}",
        "cohort": {
            "id": invite.cohort.id,
            "title": invite.cohort.title,
            "unique_id": invite.cohort.unique_id
        },
        "status": enrollment_status
    }
