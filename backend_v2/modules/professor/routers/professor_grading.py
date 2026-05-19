"""
Professor grading router - Endpoints for professor grading operations.

Endpoints that depended on the legacy `modules.simulation` package are
stubbed in backend_v2 with `NotImplementedError`. They will be reimplemented
on top of the Claude Agent SDK in a later rewrite ticket.
"""
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone

from common.db.core import get_db
from common.db.models import User, StudentSimulationInstance, GradeHistory
from common.db.models.cohorts.cohort import CohortSimulation
from app.dependencies import require_professor, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/professor/grading", tags=["Professor Grading"])


_SIMULATION_STUB_DETAIL = (
    "Simulation-backed grading is not yet available in backend_v2. "
    "The simulation module is being rebuilt on the Claude Agent SDK."
)


@router.get("/instances/{instance_id}/submission", response_model=Dict[str, Any])
async def get_submission_details(
    instance_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get submission details for a student simulation instance (stub)."""
    raise NotImplementedError(_SIMULATION_STUB_DETAIL)


@router.get("/instances/{instance_id}/history", response_model=List[Dict[str, Any]])
async def get_grade_history(
    instance_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get grade history for a student simulation instance."""
    try:
        # Verify instance exists and professor has access
        instance = db.query(StudentSimulationInstance).options(
            selectinload(StudentSimulationInstance.cohort_assignment).joinedload(CohortSimulation.cohort)
        ).filter(
            StudentSimulationInstance.id == instance_id
        ).first()

        if not instance:
            raise HTTPException(status_code=404, detail="Simulation instance not found")

        # Verify the professor has access to this instance
        # Enforce authorization unconditionally - missing cohort linkage results in denied access
        cohort = instance.cohort_assignment.cohort if instance.cohort_assignment else None
        if cohort is None or cohort.created_by != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Get grade history
        history_records = db.query(GradeHistory).filter(
            GradeHistory.instance_id == instance_id
        ).order_by(GradeHistory.created_at.desc()).all()

        # Bulk load all graders to avoid N+1 queries
        graded_by_ids = {record.graded_by for record in history_records if record.graded_by}
        graders_map = {}
        if graded_by_ids:
            graders = db.query(User).filter(User.id.in_(graded_by_ids)).all()
            graders_map = {grader.id: grader for grader in graders}

        # Format history records
        history = []
        for record in history_records:
            grader = None
            if record.graded_by:
                grader_user = graders_map.get(record.graded_by)
                if grader_user:
                    grader = {
                        "id": grader_user.id,
                        "name": grader_user.full_name or grader_user.email.split('@')[0],
                        "email": grader_user.email
                    }

            history.append({
                "id": record.id,
                "grade_type": record.grade_type,
                "grade_value": record.grade_value,
                "feedback": record.feedback,
                "graded_by": grader,
                "previous_status": record.previous_status,
                "new_status": record.new_status,
                "created_at": record.created_at.isoformat() if record.created_at else None
            })

        return history

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_grade_history: {e!r}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get grade history: {e!s}") from e


@router.post("/instances/{instance_id}/review", response_model=Dict[str, Any])
async def submit_professor_review(
    instance_id: int,
    review_data: Dict[str, Any],
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Submit professor review/grade for a student simulation instance."""
    try:
        # Get the instance
        instance = db.query(StudentSimulationInstance).options(
            selectinload(StudentSimulationInstance.cohort_assignment).joinedload(CohortSimulation.cohort)
        ).filter(
            StudentSimulationInstance.id == instance_id
        ).first()

        if not instance:
            raise HTTPException(status_code=404, detail="Simulation instance not found")

        # Verify the professor has access
        # Enforce authorization unconditionally - missing cohort linkage results in denied access
        if (not instance.cohort_assignment or
            not instance.cohort_assignment.cohort or
            instance.cohort_assignment.cohort.created_by != current_user.id):
            raise HTTPException(status_code=403, detail="Access denied")

        # Extract review data
        grade = review_data.get("grade")
        feedback = review_data.get("feedback", "")

        if grade is None:
            raise HTTPException(status_code=400, detail="Grade is required")

        try:
            grade = float(grade)
            if grade < 0 or grade > 100:
                raise HTTPException(status_code=400, detail="Grade must be between 0 and 100")
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid grade value")

        # Store previous values for history
        previous_status = instance.grade_status

        # Update instance
        instance.grade = grade
        instance.feedback = feedback
        instance.graded_by = current_user.id
        instance.graded_at = datetime.now(timezone.utc)
        instance.grade_status = "professor_graded"

        # Update status if needed
        if instance.status in ["completed", "submitted"]:
            instance.status = "graded"

        # Create grade history record
        history_record = GradeHistory(
            instance_id=instance.id,
            grade_type="professor",
            grade_value=grade,
            feedback=feedback,
            graded_by=current_user.id,
            previous_status=previous_status,
            new_status="professor_graded"
        )
        db.add(history_record)

        db.commit()
        db.refresh(instance)

        return {
            "instance_id": instance.id,
            "grade": instance.grade,
            "feedback": instance.feedback,
            "graded_by": instance.graded_by,
            "graded_at": instance.graded_at.isoformat() if instance.graded_at else None,
            "grade_status": instance.grade_status,
            "status": instance.status
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in submit_professor_review: {e!r}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to submit review: {e!s}") from e


@router.post("/instances/{instance_id}/review/revert", response_model=Dict[str, Any])
async def revert_to_ai_grade(
    instance_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Revert to AI grade (remove professor override)."""
    try:
        # Get the instance
        instance = db.query(StudentSimulationInstance).options(
            selectinload(StudentSimulationInstance.cohort_assignment).joinedload(CohortSimulation.cohort)
        ).filter(
            StudentSimulationInstance.id == instance_id
        ).first()

        if not instance:
            raise HTTPException(status_code=404, detail="Simulation instance not found")

        # Verify the professor has access
        # Enforce authorization unconditionally - missing cohort linkage results in denied access
        if (not instance.cohort_assignment or
            not instance.cohort_assignment.cohort or
            instance.cohort_assignment.cohort.created_by != current_user.id):
            raise HTTPException(status_code=403, detail="Access denied")

        if instance.ai_grade is None:
            raise HTTPException(status_code=400, detail="No AI grade available to revert to")

        # Store previous status for history
        previous_status = instance.grade_status

        # Revert to AI grade
        instance.grade = None
        instance.feedback = None
        instance.graded_by = None
        instance.graded_at = None
        instance.grade_status = "ai_graded" if instance.ai_grade is not None else "not_graded"

        # Create grade history record
        history_record = GradeHistory(
            instance_id=instance.id,
            grade_type="ai",
            grade_value=instance.ai_grade,
            feedback=instance.ai_feedback,
            graded_by=None,
            previous_status=previous_status,
            new_status="ai_graded"
        )
        db.add(history_record)

        db.commit()
        db.refresh(instance)

        return {
            "instance_id": instance.id,
            "grade": instance.grade,
            "ai_grade": instance.ai_grade,
            "ai_feedback": instance.ai_feedback,
            "grade_status": instance.grade_status
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in revert_to_ai_grade: {e!r}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to revert to AI grade: {e!s}") from e


@router.post("/admin/regrade/{user_progress_id}", response_model=Dict[str, Any])
async def admin_regrade_simulation(
    user_progress_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Re-grade a simulation with updated grading logic (admin only, stub)."""
    raise NotImplementedError(_SIMULATION_STUB_DETAIL)


@router.post("/regrade/{user_progress_id}", response_model=Dict[str, Any])
async def professor_regrade_simulation(
    user_progress_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Re-grade a simulation (professor access, stub)."""
    raise NotImplementedError(_SIMULATION_STUB_DETAIL)
