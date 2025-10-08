"""
Student Simulation Instance Management API
Handles individual student simulation instances for cohort assignments
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
from datetime import datetime, timezone

from database.connection import get_db
from database.models import (
    User, StudentSimulationInstance, CohortSimulation, CohortStudent, 
    UserProgress, Scenario, Cohort
)
from database.schemas import (
    StudentSimulationInstanceResponse, 
    StudentSimulationInstanceCreate,
    StudentSimulationInstanceUpdate
)
from utilities.auth import get_current_user, require_student, require_professor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/student-simulation-instances", tags=["Student Simulation Instances"])

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

@router.get("/", response_model=List[StudentSimulationInstanceResponse])
async def get_student_simulation_instances(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
    status_filter: Optional[str] = Query(None),
    cohort_id: Optional[int] = Query(None)
):
    """Get student's simulation instances (only for published simulations)"""
    
    # Join with UserProgress and Scenario to filter out draft simulations
    query = db.query(StudentSimulationInstance).join(
        UserProgress, StudentSimulationInstance.user_progress_id == UserProgress.id
    ).join(
        Scenario, UserProgress.scenario_id == Scenario.id
    ).filter(
        StudentSimulationInstance.student_id == current_user.id,
        Scenario.is_draft == False  # Only show instances for published simulations
    )
    
    # Apply filters
    if status_filter:
        query = query.filter(StudentSimulationInstance.status == status_filter)
    
    if cohort_id:
        query = query.join(CohortSimulation).filter(
            CohortSimulation.cohort_id == cohort_id
        )
    
    instances = query.all()
    return instances

@router.get("/{instance_id}", response_model=StudentSimulationInstanceResponse)
async def get_student_simulation_instance(
    instance_id: int,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Get a specific student simulation instance (only if simulation is published)"""
    
    # Join with UserProgress and Scenario to check if simulation is published
    instance = db.query(StudentSimulationInstance).join(
        UserProgress, StudentSimulationInstance.user_progress_id == UserProgress.id
    ).join(
        Scenario, UserProgress.scenario_id == Scenario.id
    ).filter(
        StudentSimulationInstance.id == instance_id,
        StudentSimulationInstance.student_id == current_user.id,
        Scenario.is_draft == False  # Only allow access to published simulations
    ).first()
    
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
    """Update a student simulation instance (only if simulation is published)"""
    
    # Join with UserProgress and Scenario to check if simulation is published
    instance = db.query(StudentSimulationInstance).join(
        UserProgress, StudentSimulationInstance.user_progress_id == UserProgress.id
    ).join(
        Scenario, UserProgress.scenario_id == Scenario.id
    ).filter(
        StudentSimulationInstance.id == instance_id,
        StudentSimulationInstance.student_id == current_user.id,
        Scenario.is_draft == False  # Only allow updates to published simulations
    ).first()
    
    if not instance:
        raise HTTPException(
            status_code=404, 
            detail="Simulation instance not found or simulation is not published"
        )
    
    # Update fields
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(instance, field, value)
    
    # Update timestamps based on status changes
    if update_data.status == "in_progress" and not instance.started_at:
        instance.started_at = datetime.now(timezone.utc)
    elif update_data.status == "completed" and not instance.completed_at:
        instance.completed_at = datetime.now(timezone.utc)
    elif update_data.status == "submitted" and not instance.submitted_at:
        instance.submitted_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(instance)
    
    logger.info(f"Updated simulation instance {instance.id}")
    return instance

@router.post("/{instance_id}/start", response_model=StudentSimulationInstanceResponse)
async def start_simulation_instance(
    instance_id: int,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Start a simulation instance (only if simulation is published)"""
    
    # Join with UserProgress and Scenario to check if simulation is published
    instance = db.query(StudentSimulationInstance).join(
        UserProgress, StudentSimulationInstance.user_progress_id == UserProgress.id
    ).join(
        Scenario, UserProgress.scenario_id == Scenario.id
    ).filter(
        StudentSimulationInstance.id == instance_id,
        StudentSimulationInstance.student_id == current_user.id,
        Scenario.is_draft == False  # Only allow starting published simulations
    ).first()
    
    if not instance:
        raise HTTPException(
            status_code=404, 
            detail="Simulation instance not found or simulation is not published"
        )
    
    if instance.status != "not_started":
        raise HTTPException(status_code=400, detail="Simulation already started")
    
    # Get the cohort assignment to get the simulation ID
    cohort_assignment = db.query(CohortSimulation).filter(
        CohortSimulation.id == instance.cohort_assignment_id
    ).first()
    
    if not cohort_assignment:
        raise HTTPException(status_code=404, detail="Cohort assignment not found")
    
    # Create or get user progress
    user_progress = db.query(UserProgress).filter(
        UserProgress.user_id == current_user.id,
        UserProgress.scenario_id == cohort_assignment.simulation_id
    ).first()
    
    if not user_progress:
        # Create new user progress
        user_progress = UserProgress(
            user_id=current_user.id,
            scenario_id=cohort_assignment.simulation_id,
            simulation_status="in_progress",
            started_at=datetime.now(timezone.utc)
        )
        db.add(user_progress)
        db.commit()
        db.refresh(user_progress)
    
    # Update instance
    instance.status = "in_progress"
    instance.started_at = datetime.now(timezone.utc)
    instance.user_progress_id = user_progress.id
    instance.attempts_count += 1
    
    db.commit()
    db.refresh(instance)
    
    logger.info(f"Started simulation instance {instance.id}")
    return instance

@router.post("/{instance_id}/complete", response_model=StudentSimulationInstanceResponse)
async def complete_simulation_instance(
    instance_id: int,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Mark a simulation instance as completed (only if simulation is published)"""
    
    # Join with UserProgress and Scenario to check if simulation is published
    instance = db.query(StudentSimulationInstance).join(
        UserProgress, StudentSimulationInstance.user_progress_id == UserProgress.id
    ).join(
        Scenario, UserProgress.scenario_id == Scenario.id
    ).filter(
        StudentSimulationInstance.id == instance_id,
        StudentSimulationInstance.student_id == current_user.id,
        Scenario.is_draft == False  # Only allow completing published simulations
    ).first()
    
    if not instance:
        raise HTTPException(
            status_code=404, 
            detail="Simulation instance not found or simulation is not published"
        )
    
    if instance.status not in ["in_progress", "not_started"]:
        raise HTTPException(status_code=400, detail="Simulation not in progress")
    
    # Update user progress if it exists
    if instance.user_progress_id:
        user_progress = db.query(UserProgress).filter(
            UserProgress.id == instance.user_progress_id
        ).first()
        
        if user_progress:
            user_progress.simulation_status = "completed"
            user_progress.completed_at = datetime.now(timezone.utc)
            user_progress.last_activity = datetime.now(timezone.utc)
    
    # Update instance
    instance.status = "completed"
    instance.completed_at = datetime.now(timezone.utc)
    
    # Calculate completion percentage from user progress
    if instance.user_progress_id:
        user_progress = db.query(UserProgress).filter(
            UserProgress.id == instance.user_progress_id
        ).first()
        if user_progress:
            instance.completion_percentage = user_progress.completion_percentage or 0.0
            instance.total_time_spent = user_progress.total_time_spent or 0
    
    db.commit()
    db.refresh(instance)
    
    logger.info(f"Completed simulation instance {instance.id}")
    return instance

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
