"""
Student simulation instances router - Endpoints for student simulation instances
"""
import logging
import secrets
import string
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session, selectinload

from common.db.core import get_db
from common.db.models import User, StudentSimulationInstance, CohortSimulation, CohortStudent
from app.dependencies import require_student

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/student-simulation-instances", tags=["Student Simulation Instances"])


def generate_instance_id() -> str:
    """Generate a short, user-friendly instance ID like SI-MAN8P1QS"""
    chars = string.ascii_uppercase + string.digits
    random_part = ''.join(secrets.choice(chars) for _ in range(8))
    return f"SI-{random_part}"


async def _ensure_simulation_instances_exist(db: Session, student_id: int, cohort_id: Optional[int] = None) -> int:
    """
    Ensure simulation instances exist for the student in their approved cohorts.
    This backfills any missing instances that should have been created when simulations were assigned.
    
    Returns the number of instances created.
    """
    instances_created = 0
    
    try:
        # Get all cohorts the student is approved in
        cohort_query = db.query(CohortStudent).filter(
            CohortStudent.student_id == student_id,
            CohortStudent.status == "approved"
        )
        
        if cohort_id:
            cohort_query = cohort_query.filter(CohortStudent.cohort_id == cohort_id)
        
        approved_enrollments = cohort_query.all()
        
        for enrollment in approved_enrollments:
            # Get all simulations assigned to this cohort
            cohort_simulations = db.query(CohortSimulation).filter(
                CohortSimulation.cohort_id == enrollment.cohort_id
            ).all()
            
            for cohort_simulation in cohort_simulations:
                # Check if instance already exists
                existing = db.query(StudentSimulationInstance).filter(
                    StudentSimulationInstance.cohort_assignment_id == cohort_simulation.id,
                    StudentSimulationInstance.student_id == student_id
                ).first()
                
                if existing:
                    continue
                
                # Create StudentSimulationInstance (user_progress_id is optional)
                student_instance = StudentSimulationInstance(
                    unique_id=generate_instance_id(),
                    cohort_assignment_id=cohort_simulation.id,
                    student_id=student_id,
                    user_progress_id=None
                )
                db.add(student_instance)
                instances_created += 1
                logger.info(f"Created simulation instance for student {student_id}, cohort_assignment {cohort_simulation.id}")
        
        if instances_created > 0:
            db.commit()
            logger.info(f"Auto-created {instances_created} simulation instances for student {student_id}")
        
    except Exception as e:
        logger.error(f"Error ensuring simulation instances exist: {e!r}", exc_info=True)
        db.rollback()
    
    return instances_created


@router.get("", response_model=List[dict])
@router.get("/", response_model=List[dict])
async def get_student_simulation_instances(
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    cohort_id: Optional[int] = Query(None, description="Filter by cohort ID"),
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Get all simulation instances for the current student"""
    try:
        # First, ensure simulation instances exist for this student
        # This auto-creates any missing instances for cohorts the student is approved in
        await _ensure_simulation_instances_exist(db, current_user.id, cohort_id)
        
        # Build query for student's simulation instances
        query = db.query(StudentSimulationInstance).options(
            selectinload(StudentSimulationInstance.cohort_assignment).selectinload(CohortSimulation.simulation),
            selectinload(StudentSimulationInstance.cohort_assignment).selectinload(CohortSimulation.cohort)
        ).filter(
            StudentSimulationInstance.student_id == current_user.id
        )
        
        # Apply status filter if provided
        if status_filter:
            query = query.filter(StudentSimulationInstance.status == status_filter)
        
        # Apply cohort filter if provided
        if cohort_id:
            query = query.join(
                CohortSimulation, 
                StudentSimulationInstance.cohort_assignment_id == CohortSimulation.id
            ).filter(CohortSimulation.cohort_id == cohort_id)
        
        instances = query.all()
        
        # Build response with simulation details
        result = []
        for instance in instances:
            cohort_assignment = instance.cohort_assignment
            simulation = cohort_assignment.simulation if cohort_assignment else None
            cohort = cohort_assignment.cohort if cohort_assignment else None
            
            result.append({
                "id": instance.id,
                "unique_id": instance.unique_id,
                "student_id": instance.student_id,
                "status": instance.status,
                "started_at": instance.started_at.isoformat() if instance.started_at else None,
                "completed_at": instance.completed_at.isoformat() if instance.completed_at else None,
                "submitted_at": instance.submitted_at.isoformat() if instance.submitted_at else None,
                "completion_percentage": instance.completion_percentage,
                "total_time_spent": instance.total_time_spent,
                "grade": instance.grade,
                "ai_grade": instance.ai_grade,
                "feedback": instance.feedback,
                "ai_feedback": instance.ai_feedback,
                "grade_status": instance.grade_status,
                "created_at": instance.created_at.isoformat() if instance.created_at else None,
                "cohort_assignment": {
                    "id": cohort_assignment.id if cohort_assignment else None,
                    "simulation_id": cohort_assignment.simulation_id if cohort_assignment else None,
                    "due_date": cohort_assignment.due_date.isoformat() if cohort_assignment and cohort_assignment.due_date else None,
                    "is_required": cohort_assignment.is_required if cohort_assignment else False,
                    "simulation": {
                        "id": simulation.id,
                        "title": simulation.title,
                        "description": simulation.description,
                        "is_draft": simulation.is_draft,
                        "status": simulation.status
                    } if simulation else None,
                    "cohort": {
                        "id": cohort.id,
                        "unique_id": cohort.unique_id,
                        "title": cohort.title
                    } if cohort else None
                } if cohort_assignment else None
            })
        
        return result
        
    except Exception as e:
        logger.error(f"Error in get_student_simulation_instances: {e!r}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch simulation instances: {e!s}") from e


@router.get("/{instance_unique_id}", response_model=dict)
async def get_student_simulation_instance(
    instance_unique_id: str,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Get a specific simulation instance by unique_id"""
    try:
        instance = db.query(StudentSimulationInstance).options(
            selectinload(StudentSimulationInstance.cohort_assignment).selectinload(CohortSimulation.simulation),
            selectinload(StudentSimulationInstance.cohort_assignment).selectinload(CohortSimulation.cohort)
        ).filter(
            StudentSimulationInstance.unique_id == instance_unique_id,
            StudentSimulationInstance.student_id == current_user.id
        ).first()
        
        if not instance:
            raise HTTPException(status_code=404, detail="Simulation instance not found")
        
        cohort_assignment = instance.cohort_assignment
        simulation = cohort_assignment.simulation if cohort_assignment else None
        cohort = cohort_assignment.cohort if cohort_assignment else None
        
        return {
            "id": instance.id,
            "unique_id": instance.unique_id,
            "student_id": instance.student_id,
            "status": instance.status,
            "started_at": instance.started_at.isoformat() if instance.started_at else None,
            "completed_at": instance.completed_at.isoformat() if instance.completed_at else None,
            "submitted_at": instance.submitted_at.isoformat() if instance.submitted_at else None,
            "completion_percentage": instance.completion_percentage,
            "total_time_spent": instance.total_time_spent,
            "grade": instance.grade,
            "ai_grade": instance.ai_grade,
            "feedback": instance.feedback,
            "ai_feedback": instance.ai_feedback,
            "grade_status": instance.grade_status,
            "created_at": instance.created_at.isoformat() if instance.created_at else None,
            "cohort_assignment": {
                "id": cohort_assignment.id if cohort_assignment else None,
                "simulation_id": cohort_assignment.simulation_id if cohort_assignment else None,
                "due_date": cohort_assignment.due_date.isoformat() if cohort_assignment and cohort_assignment.due_date else None,
                "is_required": cohort_assignment.is_required if cohort_assignment else False,
                "simulation": {
                    "id": simulation.id,
                    "title": simulation.title,
                    "description": simulation.description,
                    "is_draft": simulation.is_draft,
                    "status": simulation.status
                } if simulation else None,
                "cohort": {
                    "id": cohort.id,
                    "unique_id": cohort.unique_id,
                    "title": cohort.title
                } if cohort else None
            } if cohort_assignment else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_student_simulation_instance: {e!r}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch simulation instance: {e!s}") from e

