"""
Student simulation instance management API endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime, timezone

from database.connection import get_db
from database.models import (
    User, StudentSimulationInstance, CohortSimulation, Cohort, Scenario, UserProgress,
    ScenarioScene, ScenarioPersona, SceneProgress, ConversationLog, scene_personas
)
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
                    # Import the unique ID generator
                    from utilities.id_generator import generate_unique_simulation_instance_id
                    
                    # Create UserProgress record first
                    user_progress = UserProgress(
                        user_id=current_user.id,
                        scenario_id=cohort_simulation.simulation_id,
                        simulation_status="not_started"
                    )
                    db.add(user_progress)
                    db.flush()
                    
                    # Create the instance with unique ID
                    instance = StudentSimulationInstance(
                        unique_id=generate_unique_simulation_instance_id(db),
                        cohort_assignment_id=cohort_simulation.id,
                        student_id=current_user.id,
                        user_progress_id=user_progress.id
                    )
                    db.add(instance)
                    db.commit()
                    db.refresh(instance)
                    logger.info(f"Auto-created simulation instance {instance.unique_id} for student {current_user.id}, cohort_simulation {cohort_simulation.id}")
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
                "unique_id": instance.unique_id,
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
    
    # Import the unique ID generator
    from utilities.id_generator import generate_unique_simulation_instance_id
    
    # Create the instance with user_progress_id
    instance = StudentSimulationInstance(
        unique_id=generate_unique_simulation_instance_id(db),
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
    instance_id: str,  # Changed to str to accept both integer IDs and unique_ids
    update_data: StudentSimulationInstanceUpdate,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Update a simulation instance (accepts both integer ID and unique_id)"""
    
    # Try to get instance by integer ID or unique_id
    instance = None
    try:
        int_id = int(instance_id)
        instance = _get_published_instance_query(db, current_user.id, int_id).first()
    except ValueError:
        # It's a unique_id string - query by unique_id
        instance = db.query(StudentSimulationInstance).filter(
            StudentSimulationInstance.unique_id == instance_id,
            StudentSimulationInstance.student_id == current_user.id
        ).first()
    
    if not instance:
        raise HTTPException(
            status_code=404, 
            detail="Simulation instance not found or simulation is not published"
        )
    
    # Update fields
    for field, value in update_data.dict(exclude_unset=True).items():
        setattr(instance, field, value)
    
    # Sync completion data from UserProgress if it exists
    if instance.user_progress_id:
        user_progress = db.query(UserProgress).filter(
            UserProgress.id == instance.user_progress_id
        ).first()
        
        if user_progress:
            # Sync completion percentage and time spent from UserProgress
            if user_progress.completion_percentage is not None:
                instance.completion_percentage = user_progress.completion_percentage
            if user_progress.total_time_spent is not None:
                instance.total_time_spent = user_progress.total_time_spent
            if user_progress.hints_used is not None:
                instance.hints_used = user_progress.hints_used
    
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
    instance.status = "in_progress"
    instance.started_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(instance)
    
    logger.info(f"Started simulation instance {instance_id} for student {current_user.id}")
    return instance

@router.post("/{instance_id}/start-simulation")
async def start_simulation_for_instance(
    instance_id: str,  # Changed to str to accept both integer IDs and unique_ids
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """
    Start the actual simulation for a student instance.
    This properly initializes UserProgress and returns simulation data for the chat interface.
    Accepts both integer ID and unique_id (SSI-XXXXXXXX format).
    """
    
    # Determine if instance_id is an integer or unique_id
    instance = None
    try:
        # Try to parse as integer first
        int_id = int(instance_id)
        # Get the instance by integer ID (check if published when user_progress exists)
        instance = db.query(StudentSimulationInstance).filter(
            StudentSimulationInstance.id == int_id,
            StudentSimulationInstance.student_id == current_user.id
        ).first()
        
        # If instance has user_progress, verify it's published
        if instance and instance.user_progress_id:
            user_progress = db.query(UserProgress).filter(
                UserProgress.id == instance.user_progress_id
            ).first()
            if user_progress:
                scenario = db.query(Scenario).filter(Scenario.id == user_progress.scenario_id).first()
                if scenario and scenario.is_draft:
                    instance = None  # Don't allow draft simulations
    except ValueError:
        # It's a unique_id string
        instance = db.query(StudentSimulationInstance).filter(
            StudentSimulationInstance.unique_id == instance_id,
            StudentSimulationInstance.student_id == current_user.id
        ).first()
        
        # If instance has user_progress, verify it's published
        if instance and instance.user_progress_id:
            user_progress = db.query(UserProgress).filter(
                UserProgress.id == instance.user_progress_id
            ).first()
            if user_progress:
                scenario = db.query(Scenario).filter(Scenario.id == user_progress.scenario_id).first()
                if scenario and scenario.is_draft:
                    instance = None  # Don't allow draft simulations
    
    if not instance:
        raise HTTPException(
            status_code=404,
            detail="Simulation instance not found or simulation is not published"
        )
    
    # Get the cohort assignment to get the scenario
    cohort_assignment = db.query(CohortSimulation).filter(
        CohortSimulation.id == instance.cohort_assignment_id
    ).first()
    
    if not cohort_assignment:
        raise HTTPException(status_code=404, detail="Cohort assignment not found")
    
    scenario_id = cohort_assignment.simulation_id
    
    # Get scenario
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    
    # Check if UserProgress already exists and handle accordingly
    user_progress = None
    if instance.user_progress_id:
        user_progress = db.query(UserProgress).filter(
            UserProgress.id == instance.user_progress_id
        ).first()
        
        if user_progress:
            # If already in progress or completed, return existing data (resume)
            if user_progress.simulation_status in ["in_progress", "completed"]:
                logger.info(f"Resuming existing simulation for instance {instance_id}")
                # Will return existing simulation data below
            else:
                # Reset progress if abandoned - reuse the same UserProgress record
                logger.info(f"Resetting abandoned simulation for instance {instance_id}")
                
                # Clean up related data
                db.query(SceneProgress).filter(
                    SceneProgress.user_progress_id == user_progress.id
                ).delete()
                db.query(ConversationLog).filter(
                    ConversationLog.user_progress_id == user_progress.id
                ).delete()
                
                # Reset the UserProgress (don't delete, just reset fields)
                # We'll update it below when creating "new" progress
                user_progress = None  # Mark for recreation
    
    # Create new UserProgress if needed
    if not user_progress:
        # Get first scene
        first_scene = db.query(ScenarioScene).filter(
            ScenarioScene.scenario_id == scenario_id
        ).order_by(ScenarioScene.scene_order).first()
        
        if not first_scene:
            raise HTTPException(status_code=400, detail="Scenario has no scenes")
        
        # Get all scenes and personas
        all_scenes = db.query(ScenarioScene).filter(
            ScenarioScene.scenario_id == scenario_id
        ).order_by(ScenarioScene.scene_order).all()
        
        all_personas = db.query(ScenarioPersona).filter(
            ScenarioPersona.scenario_id == scenario_id
        ).all()
        
        # Get personas involved in each scene from the junction table
        scene_personas_map = {}
        for scene in all_scenes:
            involved_personas = db.query(ScenarioPersona).join(
                scene_personas, ScenarioPersona.id == scene_personas.c.persona_id
            ).filter(
                scene_personas.c.scene_id == scene.id
            ).all()
            scene_personas_map[scene.id] = [p.name for p in involved_personas]
        
        # Build orchestrator data
        scenario_data = {
            "id": scenario.id,
            "title": scenario.title,
            "description": scenario.description,
            "challenge": scenario.challenge,
            "scenes": [
                {
                    "id": scene.id,
                    "title": scene.title,
                    "description": scene.description,
                    "objectives": [scene.user_goal] if scene.user_goal else ["Complete the scene interaction"],
                    "image_url": scene.image_url,
                    "agent_ids": [p.name.lower().replace(" ", "_") for p in all_personas],
                    "personas_involved": scene_personas_map.get(scene.id, []),
                    "max_turns": scene.timeout_turns if scene.timeout_turns is not None else 15,
                    "success_criteria": f"User achieves: {scene.user_goal or 'scene completion'}"
                }
                for scene in all_scenes
            ],
            "personas": [
                {
                    "id": persona.name.lower().replace(" ", "_"),
                    "db_id": persona.id,
                    "identity": {
                        "name": persona.name,
                        "role": persona.role,
                        "bio": persona.background or "Professional team member"
                    },
                    "personality": {
                        "goals": persona.primary_goals or ["Support team objectives"],
                        "traits": persona.personality_traits or "Professional and collaborative"
                    }
                }
                for persona in all_personas
            ]
        }
        
        # Create UserProgress
        user_progress = UserProgress(
            user_id=current_user.id,
            scenario_id=scenario_id,
            current_scene_id=first_scene.id,
            simulation_status="waiting_for_begin",
            session_count=1,
            scenes_completed=[],
            orchestrator_data=scenario_data,
            started_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc)
        )
        db.add(user_progress)
        db.flush()
        
        # Create scene progress for first scene
        scene_progress = SceneProgress(
            user_progress_id=user_progress.id,
            scene_id=first_scene.id,
            status="in_progress",
            started_at=datetime.now(timezone.utc)
        )
        db.add(scene_progress)
        
        # Link UserProgress to instance
        instance.user_progress_id = user_progress.id
    
    # Update instance status
    if instance.status == "not_started":
        instance.status = "in_progress"
        instance.started_at = datetime.now(timezone.utc)
        instance.attempts_count += 1
    
    db.commit()
    db.refresh(instance)
    db.refresh(user_progress)
    
    # Get current scene
    current_scene = db.query(ScenarioScene).filter(
        ScenarioScene.id == user_progress.current_scene_id
    ).first()
    
    if not current_scene:
        raise HTTPException(status_code=404, detail="Current scene not found")
    
    # Get personas involved in current scene
    involved_personas = db.query(ScenarioPersona).join(
        scene_personas, ScenarioPersona.id == scene_personas.c.persona_id
    ).filter(
        scene_personas.c.scene_id == current_scene.id
    ).all()
    
    # Build response
    learning_objectives = scenario.learning_objectives
    if isinstance(learning_objectives, str):
        learning_objectives = [learning_objectives]
    elif learning_objectives is None:
        learning_objectives = []
    
    # Get total scenes count
    total_scenes = db.query(ScenarioScene).filter(
        ScenarioScene.scenario_id == scenario_id
    ).count()
    
    response_data = {
        "user_progress_id": user_progress.id,
        "scenario": {
            "id": scenario.id,
            "title": scenario.title,
            "description": scenario.description,
            "challenge": scenario.challenge,
            "industry": scenario.industry,
            "learning_objectives": learning_objectives,
            "student_role": scenario.student_role,
            "total_scenes": total_scenes
        },
        "current_scene": {
            "id": current_scene.id,
            "title": current_scene.title,
            "description": current_scene.description,
            "user_goal": current_scene.user_goal,
            "scene_order": current_scene.scene_order,
            "estimated_duration": current_scene.estimated_duration,
            "image_url": current_scene.image_url,
            "timeout_turns": current_scene.timeout_turns if current_scene.timeout_turns is not None else 15,
            "personas": [
                {
                    "id": p.id,
                    "name": p.name,
                    "role": p.role,
                    "background": p.background,
                    "correlation": p.correlation,
                    "primary_goals": p.primary_goals,
                    "personality_traits": p.personality_traits
                }
                for p in involved_personas
            ]
        },
        "simulation_status": user_progress.simulation_status,
        "instance_id": instance.id
    }
    
    logger.info(f"Started simulation for instance {instance_id}, user_progress {user_progress.id}")
    return response_data

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
        CohortSimulation,
        StudentSimulationInstance.cohort_assignment_id == CohortSimulation.id
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
