"""
Student simulation instance management API endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import logging

from database.connection import get_db
from database.models import User, StudentSimulationInstance, CohortSimulation, Cohort, Scenario, UserProgress
from database.schemas import StudentSimulationInstanceResponse, StudentSimulationInstanceCreate, StudentSimulationInstanceUpdate
from utilities.auth import require_student
from middleware.role_auth import require_professor

router = APIRouter(prefix="/student-simulation-instances", tags=["Student Simulation Instances"])
logger = logging.getLogger(__name__)


def _get_published_instance_query(
    db: Session, 
    student_id: int, 
    instance_id: Optional[int] = None
):
    """
    Helper function to build the base query for published simulation instances.
    
    Joins StudentSimulationInstance -> UserProgress -> Scenario and filters by:
    - student_id
    - Scenario.is_draft == False (only published simulations)
    - instance_id (optional)
    
    Returns:
        SQLAlchemy Query object that can be further filtered before calling first() or all()
    """
    query = db.query(StudentSimulationInstance).join(
        UserProgress, StudentSimulationInstance.user_progress_id == UserProgress.id
    ).join(
        Scenario, UserProgress.scenario_id == Scenario.id
    ).filter(
        StudentSimulationInstance.student_id == student_id,
        Scenario.is_draft == False  # Only published simulations
    )
    
    if instance_id is not None:
        query = query.filter(StudentSimulationInstance.id == instance_id)
    
    return query

@router.get("/", response_model=List[Dict[str, Any]])
async def get_student_simulation_instances(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
    status_filter: Optional[str] = Query(None),
    cohort_id: Optional[int] = Query(None)
):
    """Get simulation instances for the current student (only for published simulations)"""
    
    from database.models import CohortStudent
    
    # Get all cohorts the student is enrolled in
    student_cohorts = db.query(CohortStudent).filter(
        CohortStudent.student_id == current_user.id,
        CohortStudent.status == "approved"
    ).all()
    
    cohort_ids = [sc.cohort_id for sc in student_cohorts]
    
    if not cohort_ids:
        return []
    
    # Get all published simulations assigned to these cohorts
    from sqlalchemy.orm import joinedload
    
    cohort_simulations_query = db.query(CohortSimulation).join(
        Scenario, CohortSimulation.simulation_id == Scenario.id
    ).join(
        Cohort, CohortSimulation.cohort_id == Cohort.id
    ).options(
        joinedload(CohortSimulation.simulation),
        joinedload(CohortSimulation.cohort).joinedload(Cohort.creator)
    ).filter(
        CohortSimulation.cohort_id.in_(cohort_ids),
        Scenario.is_draft == False  # Only published simulations
    )
    
    if cohort_id:
        cohort_simulations_query = cohort_simulations_query.filter(CohortSimulation.cohort_id == cohort_id)
    
    cohort_simulations = cohort_simulations_query.all()
    
    # Format response - create instance if it doesn't exist
    result = []
    for cohort_simulation in cohort_simulations:
        try:
            # Check if student has an instance for this assignment
            instance = db.query(StudentSimulationInstance).filter(
                StudentSimulationInstance.cohort_assignment_id == cohort_simulation.id,
                StudentSimulationInstance.student_id == current_user.id
            ).first()
            
            # If no instance exists, create one automatically
            if not instance:
                try:
                    # Create UserProgress record first
                    user_progress = UserProgress(
                        user_id=current_user.id,
                        scenario_id=cohort_simulation.simulation_id,
                        simulation_status="not_started"
                    )
                    db.add(user_progress)
                    db.flush()
                    
                    # Create the instance
                    instance = StudentSimulationInstance(
                        cohort_assignment_id=cohort_simulation.id,
                        student_id=current_user.id,
                        user_progress_id=user_progress.id
                    )
                    db.add(instance)
                    db.commit()
                    db.refresh(instance)
                    logger.info(f"Auto-created simulation instance for student {current_user.id}, cohort_simulation {cohort_simulation.id}")
                except Exception as e:
                    logger.error(f"Failed to auto-create instance: {str(e)}")
                    db.rollback()
                    continue
            
            # Apply status filter if provided
            if status_filter and instance.status != status_filter:
                continue
            
            # Get simulation and cohort with safe access
            simulation = cohort_simulation.simulation
            cohort = cohort_simulation.cohort
            
            # Build professor info safely (cohort.creator is the professor who created the cohort)
            professor_name = "Unknown"
            if cohort and hasattr(cohort, 'creator') and cohort.creator:
                professor_name = cohort.creator.name if hasattr(cohort.creator, 'name') else "Unknown"
            
            result.append({
                "id": instance.id,
                "cohort_assignment_id": instance.cohort_assignment_id,
                "student_id": instance.student_id,
                "user_progress_id": instance.user_progress_id,
                "status": instance.status,
                "started_at": instance.started_at,
                "completed_at": instance.completed_at,
                "submitted_at": instance.submitted_at,
                "grade": instance.grade,
                "feedback": instance.feedback,
                "graded_by": instance.graded_by,
                "graded_at": instance.graded_at,
                "completion_percentage": instance.completion_percentage,
                "total_time_spent": instance.total_time_spent,
                "attempts_count": instance.attempts_count,
                "hints_used": instance.hints_used,
                "is_overdue": instance.is_overdue,
                "days_late": instance.days_late,
                "created_at": instance.created_at,
                "updated_at": instance.updated_at,
                # Nested relationship data
                "cohort_assignment": {
                    "id": cohort_simulation.id,
                    "simulation_id": cohort_simulation.simulation_id,
                    "cohort_id": cohort_simulation.cohort_id,
                    "due_date": cohort_simulation.due_date,
                    "is_required": cohort_simulation.is_required,
                    "simulation": {
                        "id": simulation.id if simulation else None,
                        "title": simulation.title if simulation else "Unknown Simulation",
                        "description": simulation.description if simulation else "No description available",
                        "is_draft": simulation.is_draft if simulation else True,
                        "status": simulation.status if simulation else "draft",
                    } if simulation else None,
                    "cohort": {
                        "id": cohort.id if cohort else None,
                        "title": cohort.title if cohort else "Unknown Cohort",
                        "professor": {
                            "name": professor_name
                        }
                    } if cohort else None
                }
            })
        except Exception as e:
            logger.error(f"Error processing cohort simulation {cohort_simulation.id}: {str(e)}")
            continue
    
    return result

@router.post("/", response_model=StudentSimulationInstanceResponse)
async def create_student_simulation_instance(
    instance_data: StudentSimulationInstanceCreate,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Create a new student simulation instance"""
    
    # Verify the student is enrolled in the cohort
    cohort_assignment = db.query(CohortSimulation).filter(
        CohortSimulation.id == instance_data.cohort_assignment_id
    ).first()
    
    if not cohort_assignment:
        raise HTTPException(status_code=404, detail="Cohort assignment not found")
    
    # Check if student is enrolled in the cohort
    from database.models import CohortStudent
    enrollment = db.query(CohortStudent).filter(
        CohortStudent.cohort_id == cohort_assignment.cohort_id,
        CohortStudent.student_id == current_user.id,
        CohortStudent.status == "approved"
    ).first()
    
    if not enrollment:
        raise HTTPException(status_code=403, detail="Student not enrolled in this cohort")
    
    # Check if instance already exists
    existing_instance = db.query(StudentSimulationInstance).filter(
        StudentSimulationInstance.cohort_assignment_id == instance_data.cohort_assignment_id,
        StudentSimulationInstance.student_id == current_user.id
    ).first()
    
    if existing_instance:
        raise HTTPException(status_code=400, detail="Simulation instance already exists")
    
    # Get the cohort assignment to get the simulation_id
    cohort_assignment = db.query(CohortSimulation).filter(
        CohortSimulation.id == instance_data.cohort_assignment_id
    ).first()
    
    # Create UserProgress record first
    user_progress = UserProgress(
        user_id=current_user.id,
        scenario_id=cohort_assignment.simulation_id,
        simulation_status="not_started"
    )
    db.add(user_progress)
    db.flush()  # Flush to get the ID
    
    # Create the instance with user_progress_id
    instance = StudentSimulationInstance(
        cohort_assignment_id=instance_data.cohort_assignment_id,
        student_id=current_user.id,
        user_progress_id=user_progress.id
    )
    
    db.add(instance)
    db.commit()
    db.refresh(instance)
    
    logger.info(f"Created simulation instance {instance.id} for student {current_user.id}")
    return instance

@router.get("/{instance_id}", response_model=StudentSimulationInstanceResponse)
async def get_student_simulation_instance(
    instance_id: int,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Get a specific simulation instance (only if simulation is published)"""
    
    # Get base query for published instance
    instance = _get_published_instance_query(db, current_user.id, instance_id).first()
    
    if not instance:
        raise HTTPException(
            status_code=404, 
            detail="Simulation instance not found or simulation is not published"
        )
    
    return instance

@router.put("/{instance_id}", response_model=StudentSimulationInstanceResponse)
async def update_student_simulation_instance(
    instance_id: int,
    update_data: StudentSimulationInstanceUpdate,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Update a simulation instance (only if simulation is published)"""
    
    # Get base query for published instance
    instance = _get_published_instance_query(db, current_user.id, instance_id).first()
    
    if not instance:
        raise HTTPException(
            status_code=404, 
            detail="Simulation instance not found or simulation is not published"
        )
    
    # Update fields
    for field, value in update_data.dict(exclude_unset=True).items():
        setattr(instance, field, value)
    
    db.commit()
    db.refresh(instance)
    
    logger.info(f"Updated simulation instance {instance_id} for student {current_user.id}")
    return instance

@router.post("/{instance_id}/start", response_model=StudentSimulationInstanceResponse)
async def start_simulation_instance(
    instance_id: int,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Start a simulation instance (only if simulation is published)"""
    
    # Get base query for published instance
    instance = _get_published_instance_query(db, current_user.id, instance_id).first()
    
    if not instance:
        raise HTTPException(
            status_code=404, 
            detail="Simulation instance not found or simulation is not published"
        )
    
    if instance.status != "not_started":
        raise HTTPException(status_code=400, detail="Simulation instance already started")
    
    # Update status and start time
    from datetime import datetime, timezone
    instance.status = "in_progress"
    instance.started_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(instance)
    
    logger.info(f"Started simulation instance {instance_id} for student {current_user.id}")
    return instance

@router.post("/{instance_id}/complete", response_model=StudentSimulationInstanceResponse)
async def complete_simulation_instance(
    instance_id: int,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Complete a simulation instance (only if simulation is published)"""
    
    # Get base query for published instance
    instance = _get_published_instance_query(db, current_user.id, instance_id).first()
    
    if not instance:
        raise HTTPException(
            status_code=404, 
            detail="Simulation instance not found or simulation is not published"
        )
    
    if instance.status != "in_progress":
        raise HTTPException(status_code=400, detail="Simulation instance not in progress")
    
    # Update status and completion time
    from datetime import datetime, timezone
    instance.status = "completed"
    instance.completed_at = datetime.now(timezone.utc)
    instance.completion_percentage = 100.0
    
    db.commit()
    db.refresh(instance)
    
    logger.info(f"Completed simulation instance {instance_id} for student {current_user.id}")
    return instance

@router.get("/assignment/{assignment_id}/instances")
async def get_simulation_assignment_instances(
    assignment_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get all student instances for a specific simulation assignment (professor view)"""
    
    # Get the assignment and verify professor has access
    assignment = db.query(CohortSimulation).filter(
        CohortSimulation.id == assignment_id
    ).first()
    
    if not assignment:
        raise HTTPException(status_code=404, detail="Simulation assignment not found")
    
    # Verify professor has access to this cohort
    cohort = db.query(Cohort).filter(
        Cohort.id == assignment.cohort_id,
        Cohort.created_by == current_user.id
    ).first()
    
    if not cohort:
        raise HTTPException(status_code=403, detail="Not authorized to view this data")
    
    # Get all student instances for this assignment with student details
    instances_query = db.query(StudentSimulationInstance, User).join(
        User, StudentSimulationInstance.student_id == User.id
    ).filter(
        StudentSimulationInstance.cohort_assignment_id == assignment_id
    ).all()
    
    result = []
    for instance, student in instances_query:
        result.append({
            "id": instance.id,
            "cohort_assignment_id": instance.cohort_assignment_id,
            "student_id": instance.student_id,
            "student_name": student.full_name,
            "student_email": student.email,
            "user_progress_id": instance.user_progress_id,
            "status": instance.status,
            "started_at": instance.started_at,
            "completed_at": instance.completed_at,
            "submitted_at": instance.submitted_at,
            "grade": instance.grade,
            "feedback": instance.feedback,
            "graded_by": instance.graded_by,
            "graded_at": instance.graded_at,
            "completion_percentage": instance.completion_percentage,
            "total_time_spent": instance.total_time_spent,
            "attempts_count": instance.attempts_count,
            "hints_used": instance.hints_used,
            "is_overdue": instance.is_overdue,
            "days_late": instance.days_late,
            "created_at": instance.created_at,
            "updated_at": instance.updated_at
        })
    
    return result

@router.get("/cohort/{cohort_id}/instances", response_model=List[StudentSimulationInstanceResponse])
async def get_cohort_simulation_instances(
    cohort_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get all simulation instances for a cohort (professor view)"""
    
    # Verify professor has access to the cohort
    cohort = db.query(Cohort).filter(
        Cohort.id == cohort_id,
        Cohort.created_by == current_user.id
    ).first()
    
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    # Get all instances for this cohort
    instances = db.query(StudentSimulationInstance).join(
        CohortSimulation
    ).filter(
        CohortSimulation.cohort_id == cohort_id
    ).all()
    
    return instances

@router.post("/{instance_id}/grade", response_model=StudentSimulationInstanceResponse)
async def grade_simulation_instance(
    instance_id: int,
    grade_data: dict,  # {"grade": float, "feedback": str}
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Grade a student simulation instance (professor only)"""
    from datetime import datetime, timezone
    
    instance = db.query(StudentSimulationInstance).filter(
        StudentSimulationInstance.id == instance_id
    ).first()
    
    if not instance:
        raise HTTPException(status_code=404, detail="Simulation instance not found")
    
    # Verify professor has access to this instance's cohort
    cohort_assignment = db.query(CohortSimulation).filter(
        CohortSimulation.id == instance.cohort_assignment_id
    ).first()
    
    if not cohort_assignment:
        raise HTTPException(status_code=404, detail="Cohort assignment not found")
    
    cohort = db.query(Cohort).filter(
        Cohort.id == cohort_assignment.cohort_id,
        Cohort.created_by == current_user.id
    ).first()
    
    if not cohort:
        raise HTTPException(status_code=403, detail="Not authorized to grade this simulation")
    
    # Update the instance with grade
    instance.grade = grade_data.get("grade")
    instance.feedback = grade_data.get("feedback")
    instance.graded_by = current_user.id
    instance.graded_at = datetime.now(timezone.utc)
    instance.status = "graded"
    
    db.commit()
    db.refresh(instance)
    
    logger.info(f"Graded simulation instance {instance_id} with grade {instance.grade}")
    return instance

@router.get("/cohort/{cohort_id}/grading-summary")
async def get_cohort_grading_summary(
    cohort_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get grading summary for a cohort"""
    
    # Verify professor has access to the cohort
    cohort = db.query(Cohort).filter(
        Cohort.id == cohort_id,
        Cohort.created_by == current_user.id
    ).first()
    
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    # Get grading statistics
    instances = db.query(StudentSimulationInstance).join(
        CohortSimulation
    ).filter(
        CohortSimulation.cohort_id == cohort_id
    ).all()
    
    total_instances = len(instances)
    graded_instances = len([i for i in instances if i.grade is not None])
    pending_instances = total_instances - graded_instances
    
    # Calculate average grade
    graded_grades = [i.grade for i in instances if i.grade is not None]
    average_grade = sum(graded_grades) / len(graded_grades) if graded_grades else 0
    
    return {
        "total_instances": total_instances,
        "graded_instances": graded_instances,
        "pending_instances": pending_instances,
        "average_grade": round(average_grade, 2),
        "completion_rate": round((graded_instances / total_instances * 100) if total_instances > 0 else 0, 2)
    }
