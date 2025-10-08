"""
Professor invitation API endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, status, Request
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime, timedelta
import logging

from database.connection import get_db
from database.models import User, Cohort, CohortInvitation
from database.schemas import (
    StudentInvitation, 
    CohortInvitationResponse,
    UserResponse
)
from middleware.role_auth import require_professor
from utilities.id_generator import generate_invitation_token
from services.email_service import email_service
from services.notification_service import notification_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/professor", tags=["professor-invitations"])

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
                expires_at=datetime.utcnow() + timedelta(days=7)  # 7 days expiry
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
    ).order_by(CohortInvitation.created_at.desc()).all()
    
    # Build response manually to avoid ORM relationship issues
    invitation_responses = []
    for inv in invitations:
        # Get cohort details
        cohort = db.query(Cohort).filter(Cohort.id == inv.cohort_id).first()
        
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
    ).order_by(CohortInvitation.created_at.desc()).all()
    
    # Build response manually to avoid ORM relationship issues
    invitation_responses = []
    for inv in invitations:
        # Get professor details
        professor = db.query(User).filter(User.id == inv.professor_id).first()
        
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
    invitation.expires_at = datetime.utcnow() + timedelta(days=7)
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
            "available_spots": cohort.max_students - status_counts.get('accepted', 0)
        },
        "recent_activity": recent_activity
    }
