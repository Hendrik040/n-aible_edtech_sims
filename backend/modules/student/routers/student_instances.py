"""
Student simulation instances router - Endpoints for student simulation instances
"""
import logging
import secrets
import string
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query, Body
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import IntegrityError

from common.db.core import get_db
from common.db.models import User, StudentSimulationInstance, CohortSimulation, CohortStudent
from app.dependencies import require_student, get_current_user

# Import UserProgress with graceful handling
try:
    from common.db.models import UserProgress
    USER_PROGRESS_AVAILABLE = True
except ImportError:
    USER_PROGRESS_AVAILABLE = False
    UserProgress = None

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
        logger.info(f"_ensure_simulation_instances_exist called for student_id={student_id}, cohort_id={cohort_id}")
        
        # Get all cohorts the student is approved in
        cohort_query = db.query(CohortStudent).filter(
            CohortStudent.student_id == student_id,
            CohortStudent.status == "approved"
        )
        
        if cohort_id:
            cohort_query = cohort_query.filter(CohortStudent.cohort_id == cohort_id)
        
        approved_enrollments = cohort_query.all()
        logger.info(f"Found {len(approved_enrollments)} approved enrollments for student {student_id}")
        
        # Expire any cached instances to ensure we query fresh data
        db.expire_all()
        
        # FIRST: Query ALL existing instances for this student ONCE at the start
        # This gives us a complete picture before we start checking/creating
        from sqlalchemy import text
        all_existing_instances = db.execute(
            text("SELECT id, unique_id, cohort_assignment_id, student_id FROM student_simulation_instances WHERE student_id = :student_id"),
            {"student_id": student_id}
        ).all()
        logger.info(f"[INITIAL STATE] All existing instances for student {student_id}: {[(r[0], r[1], r[2], r[3]) for r in all_existing_instances]}")
        
        # Create a map of cohort_assignment_id -> instance for quick lookup
        existing_instances_map = {r[2]: (r[0], r[1]) for r in all_existing_instances if r[2] is not None}
        logger.info(f"[INITIAL STATE] Existing instances map: {existing_instances_map}")
        
        for enrollment in approved_enrollments:
            # Get all simulations assigned to this cohort
            cohort_simulations = db.query(CohortSimulation).filter(
                CohortSimulation.cohort_id == enrollment.cohort_id
            ).all()
            
            logger.info(f"Processing {len(cohort_simulations)} simulations for cohort {enrollment.cohort_id}")
            
            for cohort_simulation in cohort_simulations:
                logger.info(f"[CHECK] student_id={student_id}, cohort_assignment_id={cohort_simulation.id}, simulation_id={cohort_simulation.simulation_id}")
                
                # Check our pre-loaded map first (fastest, no DB query needed)
                if cohort_simulation.id in existing_instances_map:
                    instance_id, unique_id = existing_instances_map[cohort_simulation.id]
                    logger.info(f"✓ Instance found in pre-loaded map: id={instance_id}, unique_id={unique_id}")
                    # Verify it still exists in DB (in case it was deleted)
                    db.expire_all()
                    existing = db.query(StudentSimulationInstance).filter(
                        StudentSimulationInstance.id == instance_id
                    ).first()
                    if existing:
                        logger.info(f"✓ Instance confirmed in DB: unique_id={existing.unique_id}, status={existing.status}")
                        continue
                    else:
                        logger.warning(f"⚠ Instance {instance_id} was in map but not in DB - may have been deleted")
                        # Remove from map and continue to create new one
                        del existing_instances_map[cohort_simulation.id]
                
                # If not in map, do direct SQL query
                sql_result = db.execute(
                    text("SELECT id, unique_id FROM student_simulation_instances WHERE cohort_assignment_id = :assignment_id AND student_id = :student_id"),
                    {"assignment_id": cohort_simulation.id, "student_id": student_id}
                ).first()
                
                if sql_result:
                    instance_id = sql_result[0]
                    unique_id = sql_result[1] if len(sql_result) > 1 else "unknown"
                    logger.info(f"✓ Instance found via direct SQL: id={instance_id}, unique_id={unique_id}")
                    # Add to map for future iterations
                    existing_instances_map[cohort_simulation.id] = (instance_id, unique_id)
                    continue
                
                # Final ORM check
                db.expire_all()
                existing = db.query(StudentSimulationInstance).filter(
                    StudentSimulationInstance.cohort_assignment_id == cohort_simulation.id,
                    StudentSimulationInstance.student_id == student_id
                ).first()
                
                if existing:
                    logger.info(f"✓ Instance found via ORM: unique_id={existing.unique_id}, status={existing.status}, id={existing.id}")
                    # Add to map
                    existing_instances_map[cohort_simulation.id] = (existing.id, existing.unique_id)
                    continue
                
                logger.warning(f"✗ NO instance found for student {student_id}, cohort_assignment {cohort_simulation.id} - WILL CREATE NEW ONE")
                
                # Create or fetch UserProgress first to ensure proper linking
                user_progress = None
                if USER_PROGRESS_AVAILABLE and UserProgress:
                    # Check if UserProgress already exists for this student and simulation
                    # Note: UserProgress from simulation module uses simulation_id, not scenario_id
                    user_progress = db.query(UserProgress).filter(
                        UserProgress.user_id == student_id,
                        UserProgress.simulation_id == cohort_simulation.simulation_id
                    ).first()
                    
                    # Create UserProgress if it doesn't exist
                    if not user_progress:
                        # Get first scene for the simulation to set current_scene_id
                        from common.db.models import SimulationScene
                        first_scene = db.query(SimulationScene).filter(
                            SimulationScene.simulation_id == cohort_simulation.simulation_id
                        ).order_by(SimulationScene.scene_order.asc()).first()
                        
                        if first_scene:
                            user_progress = UserProgress(
                                user_id=student_id,
                                simulation_id=cohort_simulation.simulation_id,
                                current_scene_id=first_scene.id,
                                simulation_status="not_started"
                            )
                            db.add(user_progress)
                            db.flush()  # Flush to get user_progress.id for foreign key
                
                # Create StudentSimulationInstance with retry logic for unique_id collisions
                max_retries = 5
                retry_count = 0
                instance_created = False
                
                while retry_count < max_retries and not instance_created:
                    try:
                        student_instance = StudentSimulationInstance(
                            unique_id=generate_instance_id(),
                            cohort_assignment_id=cohort_simulation.id,
                            student_id=student_id,
                            user_progress_id=user_progress.id if user_progress else None
                        )
                        db.add(student_instance)
                        db.flush()  # Flush to check for unique constraint violation
                        # Commit immediately so subsequent queries in the same function can see it
                        db.commit()
                        # Verify the commit worked by querying the instance back
                        db.refresh(student_instance)
                        logger.info(f"Created and committed simulation instance unique_id={student_instance.unique_id}, id={student_instance.id} for student {student_id}, cohort_assignment {cohort_simulation.id}")
                        # Update the map so subsequent checks in this function call will find it
                        existing_instances_map[cohort_simulation.id] = (student_instance.id, student_instance.unique_id)
                        logger.info(f"Updated instances map: {existing_instances_map}")
                        instance_created = True
                        instances_created += 1
                    except IntegrityError as e:
                        error_str = str(e.orig).lower()
                        # Check if it's a unique constraint violation
                        if 'unique_student_cohort_assignment' in error_str or ('student_id' in error_str and 'cohort_assignment_id' in error_str):
                            # This means an instance already exists for this student+assignment (race condition)
                            logger.warning(f"IntegrityError: Instance already exists for student {student_id}, cohort_assignment {cohort_simulation.id}. Race condition detected.")
                            db.rollback()
                            # Query to get the existing instance after rollback
                            existing = db.query(StudentSimulationInstance).filter(
                                StudentSimulationInstance.cohort_assignment_id == cohort_simulation.id,
                                StudentSimulationInstance.student_id == student_id
                            ).first()
                            if existing:
                                logger.info(f"Found existing instance after IntegrityError: unique_id={existing.unique_id}")
                            instance_created = True  # Don't create, instance already exists
                            break
                        elif 'unique_id' in error_str or 'unique constraint' in error_str:
                            # Unique constraint violation on unique_id - retry with new ID
                            retry_count += 1
                            db.rollback()  # Rollback only the failed instance creation
                            # Re-flush user_progress since we rolled back
                            if user_progress:
                                db.add(user_progress)
                                db.flush()
                            if retry_count >= max_retries:
                                logger.error(
                                    f"Failed to create StudentSimulationInstance after {max_retries} "
                                    f"retries due to unique_id collisions for student {student_id}, "
                                    f"cohort_simulation {cohort_simulation.id}"
                                )
                                raise ValueError(
                                    f"Failed to generate unique instance ID after {max_retries} attempts"
                                ) from e
                        else:
                            # Not a unique constraint violation, re-raise
                            logger.error(f"Unexpected IntegrityError: {e}")
                            raise
        
        # Note: Instances are now committed immediately after creation, so no need to commit here
        if instances_created > 0:
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


@router.get("/assignment/{assignment_id}/instances", response_model=List[dict])
async def get_assignment_instances(
    assignment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all simulation instances for a specific assignment (cohort simulation).
    
    Professors can see all instances. Students can only see their own instances.
    """
    try:
        # Verify the assignment exists
        cohort_assignment = db.query(CohortSimulation).filter(
            CohortSimulation.id == assignment_id
        ).first()
        
        if not cohort_assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")
        
        # Build query for instances with student information
        query = db.query(StudentSimulationInstance).options(
            selectinload(StudentSimulationInstance.cohort_assignment).selectinload(CohortSimulation.simulation),
            selectinload(StudentSimulationInstance.cohort_assignment).selectinload(CohortSimulation.cohort)
        ).filter(
            StudentSimulationInstance.cohort_assignment_id == assignment_id
        )
        
        # Students can only see their own instances
        if current_user.role == "student":
            query = query.filter(StudentSimulationInstance.student_id == current_user.id)
        # Professors can see all instances (no additional filter needed)
        
        instances = query.all()
        
        # Load student information for all instances
        from common.db.models import User
        student_ids = [instance.student_id for instance in instances]
        students = {}
        if student_ids:
            student_records = db.query(User).filter(User.id.in_(student_ids)).all()
            for student in student_records:
                students[student.id] = {
                    "id": student.id,
                    "name": student.full_name or student.email.split('@')[0],
                    "email": student.email
                }
        
        # Build response
        result = []
        for instance in instances:
            student_info = students.get(instance.student_id, {
                "id": instance.student_id,
                "name": "Unknown",
                "email": "unknown@example.com"
            })
            
            result.append({
                "id": instance.id,
                "unique_id": instance.unique_id,
                "student_id": instance.student_id,
                "student": student_info,
                "student_name": student_info["name"],
                "student_email": student_info["email"],
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
                "created_at": instance.created_at.isoformat() if instance.created_at else None
            })
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_assignment_instances: {e!r}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch assignment instances: {e!s}") from e


@router.put("/{instance_unique_id}", response_model=dict)
async def update_student_simulation_instance(
    instance_unique_id: str,
    update_data: dict = Body(...),
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Update a student simulation instance."""
    try:
        instance = db.query(StudentSimulationInstance).filter(
            StudentSimulationInstance.unique_id == instance_unique_id,
            StudentSimulationInstance.student_id == current_user.id
        ).first()
        
        if not instance:
            raise HTTPException(status_code=404, detail="Simulation instance not found")
        
        # Update allowed fields
        if "status" in update_data:
            instance.status = update_data["status"]
        if "completion_percentage" in update_data:
            instance.completion_percentage = update_data["completion_percentage"]
        if "grade" in update_data:
            instance.grade = update_data["grade"]
        if "feedback" in update_data:
            instance.feedback = update_data["feedback"]
        if "ai_grade" in update_data:
            instance.ai_grade = update_data["ai_grade"]
        if "ai_feedback" in update_data:
            instance.ai_feedback = update_data["ai_feedback"]
        if "completed_at" in update_data and update_data["completed_at"]:
            from datetime import datetime
            try:
                instance.completed_at = datetime.fromisoformat(update_data["completed_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass  # Skip if date parsing fails
        
        db.commit()
        db.refresh(instance)
        
        return {
            "id": instance.id,
            "unique_id": instance.unique_id,
            "status": instance.status,
            "completion_percentage": instance.completion_percentage,
            "grade": instance.grade,
            "ai_grade": instance.ai_grade,
            "feedback": instance.feedback,
            "ai_feedback": instance.ai_feedback
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in update_student_simulation_instance: {e!r}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update simulation instance: {e!s}") from e


@router.post("/{instance_unique_id}/start-simulation", response_model=dict)
async def start_simulation_from_instance(
    instance_unique_id: str,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Start or resume a simulation from a student simulation instance."""
    try:
        logger.info(f"Looking for instance with unique_id={instance_unique_id} for student_id={current_user.id}")
        
        # Use a fresh query with explicit connection to bypass any session caching
        # First, try a direct SQL query to verify the instance exists in the database
        from sqlalchemy import text
        result = db.execute(
            text("SELECT id, unique_id, student_id, cohort_assignment_id FROM student_simulation_instances WHERE unique_id = :unique_id AND student_id = :student_id"),
            {"unique_id": instance_unique_id, "student_id": current_user.id}
        ).first()
        
        if result:
            instance_id = result[0]
            logger.info(f"Found instance via direct SQL: id={instance_id}, unique_id={result[1]}, student_id={result[2]}, cohort_assignment_id={result[3]}")
            
            # Use query with selectinload to load relationships properly
            db.expire_all()
            instance = db.query(StudentSimulationInstance).options(
                selectinload(StudentSimulationInstance.cohort_assignment).selectinload(CohortSimulation.simulation)
            ).filter(StudentSimulationInstance.id == instance_id).first()
            
            if instance:
                logger.info(f"Successfully loaded instance: unique_id={instance.unique_id}, cohort_assignment_id={instance.cohort_assignment_id}")
            else:
                logger.error(f"Direct SQL found instance id={instance_id}, but ORM query returned None! This suggests the instance was deleted between queries.")
                # Fall through to error handling below
        else:
            # Expire any cached data to ensure we query fresh from the database
            db.expire_all()
            
            # Find the instance by unique_id and verify it belongs to the current student
            instance = db.query(StudentSimulationInstance).options(
                selectinload(StudentSimulationInstance.cohort_assignment).selectinload(CohortSimulation.simulation)
            ).filter(
                StudentSimulationInstance.unique_id == instance_unique_id,
                StudentSimulationInstance.student_id == current_user.id
            ).first()
        
        if not instance:
            # Try to find if instance exists at all (for debugging) - use a fresh query
            db.expire_all()
            instance_by_id = db.query(StudentSimulationInstance).filter(
                StudentSimulationInstance.unique_id == instance_unique_id
            ).first()
            if instance_by_id:
                logger.warning(f"Instance {instance_unique_id} exists but belongs to student_id={instance_by_id.student_id}, not {current_user.id}")
                raise HTTPException(status_code=403, detail="This simulation instance belongs to a different student")
            else:
                # Instance doesn't exist - try to find the correct instance by looking up cohort assignments
                logger.warning(f"Instance {instance_unique_id} not found in database. Searching for correct instance...")
                
                # Query all instances for this student to see what exists - use fresh query
                db.expire_all()
                all_student_instances = db.query(StudentSimulationInstance).filter(
                    StudentSimulationInstance.student_id == current_user.id
                ).all()
                
                logger.info(f"Found {len(all_student_instances)} total instances for student {current_user.id}")
                for inst in all_student_instances:
                    logger.info(f"  - Instance unique_id={inst.unique_id}, cohort_assignment_id={inst.cohort_assignment_id}, status={inst.status}")
                
                raise HTTPException(
                    status_code=404, 
                    detail=f"Simulation instance '{instance_unique_id}' not found. The instance may have been deleted or the page may need to be refreshed to get the current instance ID."
                )
        
        # Get the simulation_id from the cohort assignment
        # Ensure cohort_assignment is loaded
        if not instance.cohort_assignment:
            logger.warning(f"cohort_assignment is None for instance {instance.unique_id}, trying to load it")
            db.refresh(instance, ['cohort_assignment'])
            if instance.cohort_assignment:
                db.refresh(instance.cohort_assignment, ['simulation'])
        
        if not instance.cohort_assignment:
            logger.error(f"Instance {instance.unique_id} has no cohort_assignment (cohort_assignment_id={instance.cohort_assignment_id})")
            raise HTTPException(status_code=400, detail="Instance is not associated with a cohort assignment")
        
        simulation_id = instance.cohort_assignment.simulation_id
        logger.info(f"Starting/resuming simulation_id={simulation_id} for instance {instance.unique_id}")
        
        # Verify simulation exists before proceeding (better error message)
        from modules.simulation.repository import SimulationRepository
        repository = SimulationRepository(db)
        simulation = repository.get_simulation_by_id(simulation_id)
        if not simulation:
            logger.error(
                f"Simulation {simulation_id} not found or deleted for instance {instance.unique_id} "
                f"(cohort_assignment_id={instance.cohort_assignment_id}). "
                f"The simulation may have been deleted but instances still reference it."
            )
            raise HTTPException(
                status_code=404,
                detail=f"Simulation not found. The simulation associated with this assignment may have been deleted. Please contact your instructor."
            )
        
        # Capture instance status and ID BEFORE calling lifecycle service (which may detach the instance)
        instance_status = instance.status
        instance_id = instance.id
        needs_status_update = instance_status == "not_started"
        
        # Import lifecycle service
        from modules.simulation.services.lifecycle_service import LifecycleService
        
        lifecycle_service = LifecycleService(db, repository)
        
        # Check if there's existing progress to resume
        existing_user_progress_id = instance.user_progress_id
        should_resume = False
        
        if existing_user_progress_id:
            existing_progress = repository.get_user_progress_by_id(existing_user_progress_id)
            # Only resume if user_progress exists, belongs to user, matches simulation, AND has orchestrator_data
            if existing_progress:
                # CRITICAL VALIDATION: Ensure UserProgress belongs to this student
                if existing_progress.user_id != current_user.id:
                    logger.error(
                        f"SECURITY ISSUE: Instance {instance.unique_id} (student_id={current_user.id}) "
                        f"has user_progress_id={existing_user_progress_id} that belongs to "
                        f"different user_id={existing_progress.user_id}. This should never happen! "
                        f"Clearing invalid reference and starting fresh."
                    )
                    instance.user_progress_id = None
                    should_resume = False
                elif (existing_progress.simulation_id == simulation_id and
                      existing_progress.orchestrator_data):  # Critical: must have orchestrator_data to resume
                    logger.info(f"✓ Resuming existing progress: user_progress_id={existing_user_progress_id} for instance {instance.unique_id} (student_id={current_user.id})")
                    should_resume = True
                else:
                    logger.warning(
                        f"Existing user_progress_id={existing_user_progress_id} doesn't match simulation "
                        f"(expected simulation_id={simulation_id}, got {existing_progress.simulation_id}) "
                        f"or missing orchestrator_data - starting fresh"
                    )
                    instance.user_progress_id = None
                    should_resume = False
            else:
                logger.warning(f"Existing user_progress_id={existing_user_progress_id} not found in database - starting fresh")
                instance.user_progress_id = None
                should_resume = False
            
            # If we're not resuming, we cleared user_progress_id above
            # Note: We don't flush yet because user_progress_id has a NOT NULL constraint
            # We'll update it when we create the new UserProgress below
        
        if should_resume:
            # Build resume response from existing progress
            result = await lifecycle_service.resume_simulation(
                user_id=current_user.id,
                user_progress_id=existing_user_progress_id,
                simulation_id=simulation_id
            )
            # No need to link - it's already linked
            # Just update status if needed
            if needs_status_update and instance.status == "not_started":
                from datetime import datetime, timezone
                instance.status = "in_progress"
                instance.started_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(f"Updated instance {instance.unique_id}: status={instance.status}")
        else:
            logger.info(f"Starting fresh simulation for instance {instance.unique_id}")
            # Start the simulation (creates new UserProgress)
            result = await lifecycle_service.start_simulation(
                user_id=current_user.id,
                simulation_id=simulation_id
            )
            
            # Link the newly created UserProgress back to the instance and update status
            # Re-query the instance since lifecycle service may have affected the session
            from datetime import datetime, timezone
            instance = db.query(StudentSimulationInstance).filter(
                StudentSimulationInstance.id == instance_id
            ).first()
            
            if instance:
                # Link the new UserProgress to this instance
                # This will overwrite any invalid user_progress_id that was set earlier
                instance.user_progress_id = result.user_progress_id
                logger.info(f"Linked instance {instance.unique_id} to user_progress_id={result.user_progress_id}")
                
                # Update the instance status if needed
                if needs_status_update and instance.status == "not_started":
                    instance.status = "in_progress"
                    instance.started_at = datetime.now(timezone.utc)
                
                # Now it's safe to commit since user_progress_id is set to a valid value
                db.commit()
                logger.info(f"Updated instance {instance.unique_id}: status={instance.status}, user_progress_id={instance.user_progress_id}")
            else:
                logger.error(f"Instance id={instance_id} not found after starting simulation - this should not happen!")
        
        # Return the simulation start response as a dict
        return {
            "user_progress_id": result.user_progress_id,
            "simulation": result.simulation,
            "current_scene": result.current_scene,
            "simulation_status": result.simulation_status,
            "conversation_history": result.conversation_history,
            "is_resuming": result.is_resuming,
            "all_scenes": result.all_scenes,
            "turn_count": result.turn_count if hasattr(result, 'turn_count') else 0,
            "completed_scene_ids": result.completed_scene_ids if hasattr(result, 'completed_scene_ids') else []
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in start_simulation_from_instance: {e!r}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start simulation: {e!s}") from e

