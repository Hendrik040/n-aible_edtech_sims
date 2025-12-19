"""
Student cohort router - Thin HTTP layer for student cohort views
"""
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from common.db.core import get_db
from common.db.models import User, CohortInvitation
from app.dependencies import require_student
from modules.cohorts.service import CohortService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/student", tags=["Student Cohorts"])


def get_cohort_service(db: Session = Depends(get_db)) -> CohortService:
    """Dependency to get cohort service"""
    return CohortService(db)


class InvitationResponse(BaseModel):
    """Response model for cohort invitations"""
    id: int
    cohort_id: int
    cohort_title: str
    professor_name: str
    professor_email: str
    message: str | None
    status: str
    expires_at: str
    created_at: str


class RespondToInvitationRequest(BaseModel):
    """Request model for responding to an invitation"""
    action: str  # 'accept' or 'decline'


@router.get("/cohorts", response_model=List[Dict[str, Any]])
async def get_student_cohorts(
    current_user: User = Depends(require_student),
    service: CohortService = Depends(get_cohort_service)
):
    """Get cohorts that the current student is enrolled in"""
    try:
        return service.get_student_cohorts(current_user.id)
    except Exception as e:
        logger.error(f"Error in get_student_cohorts: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch cohorts")


@router.get("/cohorts/{cohort_unique_id}/simulations", response_model=List[Dict[str, Any]])
async def get_cohort_simulations(
    cohort_unique_id: str,
    current_user: User = Depends(require_student),
    service: CohortService = Depends(get_cohort_service)
):
    """Get simulations assigned to a cohort that the student is enrolled in"""
    try:
        return service.get_student_cohort_simulations(cohort_unique_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error in get_cohort_simulations: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch simulations")


@router.get("/invitations", response_model=List[InvitationResponse])
async def get_pending_invitations(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Get pending cohort invitations for the current student"""
    try:
        from datetime import datetime, timezone
        from common.db.models import Cohort
        
        # Get all pending invitations for this student's email
        invitations = db.query(CohortInvitation).filter(
            CohortInvitation.student_email == current_user.email,
            CohortInvitation.status == "pending"
        ).all()
        
        # Filter out expired invitations
        now = datetime.now(timezone.utc)
        valid_invitations = []
        
        for invitation in invitations:
            expires_at = invitation.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            
            if expires_at < now:
                # Mark as expired
                invitation.status = "expired"
                db.commit()
                continue
            
            # Get cohort and professor info
            cohort = db.query(Cohort).filter(Cohort.id == invitation.cohort_id).first()
            if not cohort:
                continue
            
            from common.db.models import User as UserModel
            professor = db.query(UserModel).filter(UserModel.id == invitation.professor_id).first()
            
            valid_invitations.append(InvitationResponse(
                id=invitation.id,
                cohort_id=cohort.id,
                cohort_title=cohort.title,
                professor_name=professor.full_name if professor else "Unknown",
                professor_email=professor.email if professor else "Unknown",
                message=invitation.message,
                status=invitation.status,
                expires_at=invitation.expires_at.isoformat(),
                created_at=invitation.created_at.isoformat()
            ))
        
        return valid_invitations
    except Exception as e:
        logger.error(f"Error getting pending invitations: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch invitations")


@router.post("/invitations/{invitation_id}/respond")
async def respond_to_invitation(
    invitation_id: int,
    request: RespondToInvitationRequest,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Accept or decline a cohort invitation"""
    try:
        from datetime import datetime, timezone
        from common.db.models import Cohort, CohortStudent
        
        # Get the invitation
        invitation = db.query(CohortInvitation).filter(
            CohortInvitation.id == invitation_id,
            CohortInvitation.student_email == current_user.email
        ).first()
        
        if not invitation:
            raise HTTPException(status_code=404, detail="Invitation not found")
        
        if invitation.status != "pending":
            raise HTTPException(status_code=400, detail=f"Invitation is already {invitation.status}")
        
        # Check expiration
        now = datetime.now(timezone.utc)
        expires_at = invitation.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        if expires_at < now:
            invitation.status = "expired"
            db.commit()
            raise HTTPException(status_code=410, detail="This invitation has expired")
        
        if request.action == "accept":
            # Check if already enrolled
            cohort = db.query(Cohort).filter(Cohort.id == invitation.cohort_id).first()
            if not cohort:
                raise HTTPException(status_code=404, detail="Cohort not found")
            
            existing_enrollment = db.query(CohortStudent).filter(
                CohortStudent.cohort_id == cohort.id,
                CohortStudent.student_id == current_user.id
            ).first()
            
            if existing_enrollment:
                invitation.status = "accepted"
                db.commit()
                return {"success": True, "message": "You are already enrolled in this cohort"}
            
            # Create enrollment
            enrollment = CohortStudent(
                cohort_id=cohort.id,
                student_id=current_user.id,
                status="approved" if cohort.auto_approve else "pending"
            )
            db.add(enrollment)
            
            # Update invitation
            invitation.status = "accepted"
            invitation.student_id = current_user.id
            db.commit()
            
            status_msg = "approved" if cohort.auto_approve else "pending approval"
            return {
                "success": True,
                "message": f"Successfully joined cohort! Your status is: {status_msg}",
                "cohort_id": cohort.id,
                "cohort_title": cohort.title
            }
        
        elif request.action == "decline":
            invitation.status = "declined"
            db.commit()
            return {"success": True, "message": "Invitation declined"}
        
        else:
            raise HTTPException(status_code=400, detail="Action must be 'accept' or 'decline'")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error responding to invitation: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to respond to invitation")
