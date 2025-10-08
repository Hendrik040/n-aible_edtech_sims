"""
Student simulation instance management API endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from database.connection import get_db
from database.models import User, StudentSimulationInstance, CohortSimulation, Cohort, Scenario, UserProgress
from database.schemas import StudentSimulationInstanceResponse, StudentSimulationInstanceCreate, StudentSimulationInstanceUpdate
from utilities.auth import require_student

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/", response_model=List[StudentSimulationInstanceResponse])
async def get_student_simulation_instances(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
    status_filter: Optional[str] = Query(None),
    cohort_id: Optional[int] = Query(None)
):
    """Get simulation instances for the current student (only for published simulations)"""
    
    # Join with UserProgress and Scenario to filter out draft simulations
    query = db.query(StudentSimulationInstance).join(
        UserProgress, StudentSimulationInstance.user_progress_id == UserProgress.id
    ).join(
        Scenario, UserProgress.scenario_id == Scenario.id
    ).filter(
        StudentSimulationInstance.student_id == current_user.id,
        Scenario.is_draft == False  # Only show instances for published simulations
    )
    
    if status_filter:
        query = query.filter(StudentSimulationInstance.status == status_filter)
    
    if cohort_id:
        # Filter by cohort through the cohort assignment
        query = query.join(CohortSimulation).filter(
            CohortSimulation.cohort_id == cohort_id
        )
    
    instances = query.all()
    return instances

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
    """Update a simulation instance (only if simulation is published)"""
    
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
