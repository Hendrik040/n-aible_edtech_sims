"""
Student simulation instances router - Endpoints for student simulation instances
"""
import logging
import secrets
import string
import time
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query, Body
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import IntegrityError, OperationalError

from common.db.core import get_db
from common.db.models import User, StudentSimulationInstance, CohortSimulation, CohortStudent, Cohort, Simulation
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
        logger.debug(f"_ensure_simulation_instances_exist called for student_id={student_id}, cohort_id={cohort_id}")
        
        # Get all cohorts the student is approved in
        cohort_query = db.query(CohortStudent).filter(
            CohortStudent.student_id == student_id,
            CohortStudent.status == "approved"
        )
        
        if cohort_id:
            cohort_query = cohort_query.filter(CohortStudent.cohort_id == cohort_id)
        
        approved_enrollments = cohort_query.all()
        logger.debug(f"Found {len(approved_enrollments)} approved enrollments for student {student_id}")
        
        # OPTIMIZED: Removed db.expire_all() - it flushes session cache unnecessarily
        # SQLAlchemy will handle cache invalidation when needed
        
        # FIRST: Query ALL existing instances for this student ONCE at the start
        # This gives us a complete picture before we start checking/creating
        from sqlalchemy import text
        all_existing_instances = db.execute(
            text("SELECT id, unique_id, cohort_assignment_id, student_id FROM student_simulation_instances WHERE student_id = :student_id"),
            {"student_id": student_id}
        ).all()
        # OPTIMIZED: Reduced verbose logging (only log count, not full details)
        logger.debug(f"[INITIAL STATE] Found {len(all_existing_instances)} existing instances for student {student_id}")
        
        # Create a map of cohort_assignment_id -> instance for quick lookup
        existing_instances_map = {r[2]: (r[0], r[1]) for r in all_existing_instances if r[2] is not None}
        logger.debug(f"[INITIAL STATE] Existing instances map size: {len(existing_instances_map)}")
        
        # OPTIMIZED: Batch load all cohort_simulations for all cohorts at once instead of per enrollment
        cohort_ids = [enrollment.cohort_id for enrollment in approved_enrollments]
        all_cohort_simulations = db.query(CohortSimulation).filter(
            CohortSimulation.cohort_id.in_(cohort_ids)
        ).all() if cohort_ids else []
        
        # Group by cohort_id for processing
        cohort_simulations_by_cohort = {}
        for cs in all_cohort_simulations:
            if cs.cohort_id not in cohort_simulations_by_cohort:
                cohort_simulations_by_cohort[cs.cohort_id] = []
            cohort_simulations_by_cohort[cs.cohort_id].append(cs)
        
        for enrollment in approved_enrollments:
            # Get simulations for this cohort from pre-loaded batch
            cohort_simulations = cohort_simulations_by_cohort.get(enrollment.cohort_id, [])
            
            logger.debug(f"Processing {len(cohort_simulations)} simulations for cohort {enrollment.cohort_id}")
            
            for cohort_simulation in cohort_simulations:
                # Check our pre-loaded map first (fastest, no DB query needed)
                if cohort_simulation.id in existing_instances_map:
                    # OPTIMIZED: Trust the pre-loaded map (we just queried it), skip redundant DB check
                    logger.debug(f"✓ Instance found in pre-loaded map for cohort_assignment_id={cohort_simulation.id}")
                    continue
                
                # Use SELECT ... FOR UPDATE to prevent race conditions when checking for existing instances
                # This locks the row if it exists, preventing concurrent creation attempts
                sql_result = db.execute(
                    text("SELECT id, unique_id FROM student_simulation_instances WHERE cohort_assignment_id = :assignment_id AND student_id = :student_id FOR UPDATE"),
                    {"assignment_id": cohort_simulation.id, "student_id": student_id}
                ).first()
                
                if sql_result:
                    instance_id = sql_result[0]
                    unique_id = sql_result[1] if len(sql_result) > 1 else "unknown"
                    logger.debug(f"✓ Instance found via direct SQL: id={instance_id}, unique_id={unique_id}")
                    # Add to map for future iterations
                    existing_instances_map[cohort_simulation.id] = (instance_id, unique_id)
                    continue
                
                # OPTIMIZED: Removed redundant ORM check - we already checked via SQL above
                # If SQL didn't find it, it doesn't exist
                
                logger.info(f"Creating missing instance for student {student_id}, cohort_assignment {cohort_simulation.id}")
                
                # Create or fetch UserProgress first to ensure proper linking
                user_progress = None
                user_progress_was_new = False  # Track if we created a new UserProgress
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
                            user_progress_was_new = True
                
                # Create StudentSimulationInstance with retry logic for unique_id collisions
                # Note: We accumulate all instances and commit once at the end for transaction atomicity
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
                        db.flush()  # Flush to check for unique constraint violation, but don't commit yet
                        logger.info(f"Created simulation instance unique_id={student_instance.unique_id} for student {student_id}, cohort_assignment {cohort_simulation.id} (will commit at end)")
                        # Update the map so subsequent checks in this function call will find it
                        existing_instances_map[cohort_simulation.id] = (student_instance.id, student_instance.unique_id)
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
                                existing_instances_map[cohort_simulation.id] = (existing.id, existing.unique_id)
                            instance_created = True  # Don't create, instance already exists
                            break
                        elif 'unique_id' in error_str or 'unique constraint' in error_str:
                            # Unique constraint violation on unique_id - retry with new ID
                            retry_count += 1
                            db.rollback()  # Rollback only the failed instance creation
                            # Re-add user_progress if it was newly created (rollback removed it from session)
                            if user_progress and user_progress_was_new:
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
        
        # Commit all instances atomically at the end to maintain transaction integrity
        if instances_created > 0:
            try:
                db.commit()
                logger.info(f"Committed {instances_created} simulation instances atomically for student {student_id}")
            except Exception as commit_error:
                logger.error(f"Error committing instances: {commit_error!r}", exc_info=True)
                db.rollback()
                raise
        else:
            # No instances created, but ensure any UserProgress created is committed
            db.commit()
        
    except Exception as e:
        logger.error(f"Error ensuring simulation instances exist: {e!r}", exc_info=True)
        db.rollback()
        raise
    
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
        from common.services.cache_service import redis_manager
        
        # Check Redis cache first (2-minute TTL for performance)
        # Include filters in cache key to ensure correct data is returned
        # Note: Cache TTL of 2 minutes means deleted simulations will disappear within 2 minutes
        # The query filter below ensures deleted sims are excluded from fresh queries
        cache_key = f"student_instances:{current_user.id}:{status_filter or 'all'}:{cohort_id or 'all'}"
        cached_result = redis_manager.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Returning cached simulation instances for user {current_user.id}")
            return cached_result
        
        # OPTIMIZED: Only ensure instances exist if we detect missing ones
        # Quick check: Count expected vs actual instances to avoid expensive operation on every request
        from sqlalchemy import func, text
        
        # Quick check if backfill is needed (only if we have approved enrollments)
        enrollment_count = db.query(func.count(CohortStudent.id)).filter(
            CohortStudent.student_id == current_user.id,
            CohortStudent.status == "approved"
        ).scalar() or 0
        
        if enrollment_count > 0:
            # OPTIMIZED: Cache the missing instance check result to avoid running expensive query on every request
            # Only check once per 60 seconds per student
            missing_check_cache_key = f"missing_instances_check:{current_user.id}"
            last_check_time = redis_manager.get(missing_check_cache_key)
            current_time = time.time()
            
            # Only run check if we haven't checked in the last 60 seconds
            should_check = last_check_time is None or (current_time - last_check_time) > 60
            
            if should_check:
                # Check if there are any cohort_simulations without instances (rough check)
                missing_check = db.execute(
                    text("""
                        SELECT COUNT(*) 
                        FROM cohort_students cs
                        INNER JOIN cohort_simulations cohsim ON cohsim.cohort_id = cs.cohort_id
                        LEFT JOIN student_simulation_instances ssi ON ssi.cohort_assignment_id = cohsim.id AND ssi.student_id = cs.student_id
                        WHERE cs.student_id = :student_id 
                        AND cs.status = 'approved'
                        AND ssi.id IS NULL
                    """),
                    {"student_id": current_user.id}
                ).scalar() or 0
                
                # Cache the check timestamp
                redis_manager.set(missing_check_cache_key, current_time, ttl=120)
                
                # Only run expensive backfill if we detect missing instances
                if missing_check > 0:
                    logger.info(f"Detected {missing_check} missing instances, running backfill for student {current_user.id}")
                    await _ensure_simulation_instances_exist(db, current_user.id, cohort_id)
                    # Invalidate cache after backfill to ensure fresh data
                    redis_manager.delete(cache_key)
                # else: instances are up to date, skip expensive backfill
        
        # Build query for student's simulation instances
        # Use outerjoin to handle NULL cohort_assignment_id (test simulations)
        # Filter out instances where simulation is deleted (deleted_at is not NULL)
        from sqlalchemy import or_
        query = db.query(StudentSimulationInstance).options(
            selectinload(StudentSimulationInstance.cohort_assignment).selectinload(CohortSimulation.simulation),
            selectinload(StudentSimulationInstance.cohort_assignment).selectinload(CohortSimulation.cohort)
        ).outerjoin(
            CohortSimulation,
            StudentSimulationInstance.cohort_assignment_id == CohortSimulation.id
        ).outerjoin(
            Simulation,
            CohortSimulation.simulation_id == Simulation.id
        ).filter(
            StudentSimulationInstance.student_id == current_user.id,
            # Include instances where: simulation is NULL (test sims) OR simulation is not deleted
            or_(
                Simulation.id.is_(None),  # Test simulations without cohort_assignment
                Simulation.deleted_at.is_(None)  # Cohort simulations that are not deleted
            )
        )
        
        # Apply status filter if provided
        if status_filter:
            query = query.filter(StudentSimulationInstance.status == status_filter)
        
        # Apply cohort filter if provided
        if cohort_id:
            query = query.filter(CohortSimulation.cohort_id == cohort_id)
        
        # Execute query with timeout protection
        query_start = time.time()
        try:
            # Use execution_options for actual DB-level timeout
            instances = query.execution_options(timeout=30).all()
            query_elapsed = time.time() - query_start
            if query_elapsed > 2.0:  # Log slow queries
                logger.warning(f"get_student_simulation_instances query took {query_elapsed:.2f}s for user {current_user.id}")
        except OperationalError as timeout_error:
            # Check if this is a timeout error (PostgreSQL timeout error codes)
            error_str = str(timeout_error.orig).lower() if hasattr(timeout_error, 'orig') else str(timeout_error).lower()
            is_timeout = (
                'timeout' in error_str or 
                'timed out' in error_str or
                'canceling statement due to statement timeout' in error_str
            )
            query_elapsed = time.time() - query_start
            if is_timeout:
                logger.error(f"Query timeout in get_student_simulation_instances for user {current_user.id} ({query_elapsed:.2f}s)")
                raise HTTPException(status_code=504, detail="Query timeout") from timeout_error
            else:
                # OperationalError that's not a timeout - treat as 500
                logger.error(
                    f"Database operational error in get_student_simulation_instances for user {current_user.id} "
                    f"(took {query_elapsed:.2f}s): {timeout_error!r}",
                    exc_info=True
                )
                raise HTTPException(
                    status_code=500,
                    detail="Failed to fetch simulation instances"
                ) from timeout_error
        except Exception as query_error:
            query_elapsed = time.time() - query_start
            logger.error(
                f"Query error in get_student_simulation_instances for user {current_user.id} "
                f"(took {query_elapsed:.2f}s): {query_error!r}",
                exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to fetch simulation instances"
            ) from query_error
        
        # Build response with simulation details
        # Filter out instances with deleted simulations as a safeguard
        result = []
        for instance in instances:
            cohort_assignment = instance.cohort_assignment
            simulation = cohort_assignment.simulation if cohort_assignment else None
            cohort = cohort_assignment.cohort if cohort_assignment else None
            
            # Skip instances where simulation is deleted (safeguard in case query filter missed it)
            if simulation and simulation.deleted_at is not None:
                logger.warning(f"Skipping instance {instance.unique_id} - simulation {simulation.id} is deleted")
                continue
            
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
        
        # Cache result for 2 minutes (balanced between freshness and performance)
        # Under load, we see 0% cache hits with 30s TTL - increasing to 120s allows cache hits
        # This significantly improves performance by avoiding ~44ms of cache overhead per request
        redis_manager.set(cache_key, result, ttl=120)
        
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
        
        # Ownership check for professors: only allow access to assignments in cohorts they created
        if current_user.role == "professor":
            from sqlalchemy.orm import joinedload
            assignment_with_cohort = db.query(CohortSimulation).options(
                joinedload(CohortSimulation.cohort)
            ).join(
                Cohort, CohortSimulation.cohort_id == Cohort.id
            ).filter(
                CohortSimulation.id == assignment_id,
                Cohort.created_by == current_user.id
            ).first()
            
            if not assignment_with_cohort:
                raise HTTPException(status_code=403, detail="Access denied: You can only view instances for assignments in cohorts you created")
        
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
    """Update a student simulation instance.
    
    Students can only update their own progress fields (status, completion_percentage, completed_at).
    Grading fields (grade, feedback, ai_grade, ai_feedback) are read-only and can only be set by
    professors or system processes through dedicated endpoints.
    """
    try:
        instance = db.query(StudentSimulationInstance).filter(
            StudentSimulationInstance.unique_id == instance_unique_id,
            StudentSimulationInstance.student_id == current_user.id
        ).first()
        
        if not instance:
            raise HTTPException(status_code=404, detail="Simulation instance not found")
        
        # Security: Log and reject attempts to update grading fields
        grading_fields_attempted = []
        if "grade" in update_data:
            grading_fields_attempted.append("grade")
        if "feedback" in update_data:
            grading_fields_attempted.append("feedback")
        if "ai_grade" in update_data:
            grading_fields_attempted.append("ai_grade")
        if "ai_feedback" in update_data:
            grading_fields_attempted.append("ai_feedback")
        
        if grading_fields_attempted:
            logger.warning(
                f"SECURITY: Student {current_user.id} attempted to update grading fields "
                f"{grading_fields_attempted} on instance {instance_unique_id}. "
                f"These fields are read-only for students and can only be set by professors or system processes."
            )
            raise HTTPException(
                status_code=403,
                detail=f"Grading fields ({', '.join(grading_fields_attempted)}) are read-only. "
                       f"Only professors can update grades through the grading endpoint."
            )
        
        # Update allowed fields (student progress only)
        fields_updated = []
        if "status" in update_data:
            instance.status = update_data["status"]
            fields_updated.append("status")
        if "completion_percentage" in update_data:
            instance.completion_percentage = update_data["completion_percentage"]
            fields_updated.append("completion_percentage")
        if "completed_at" in update_data and update_data["completed_at"]:
            from datetime import datetime
            try:
                instance.completed_at = datetime.fromisoformat(update_data["completed_at"].replace("Z", "+00:00"))
                fields_updated.append("completed_at")
            except (ValueError, AttributeError):
                pass  # Skip if date parsing fails
        
        if fields_updated:
            db.commit()
            db.refresh(instance)
            logger.info(
                f"Student {current_user.id} updated fields {fields_updated} on instance {instance_unique_id}"
            )
        else:
            logger.debug(f"Student {current_user.id} attempted to update instance {instance_unique_id} but no valid fields were provided")
        
        return {
            "id": instance.id,
            "unique_id": instance.unique_id,
            "status": instance.status,
            "completion_percentage": instance.completion_percentage,
            # Grading fields are read-only - return current values but don't allow updates
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
        
        # Use direct SQL query to verify the instance exists and get fresh data
        # This bypasses session cache and ensures we get current database state
        from sqlalchemy import text
        result = db.execute(
            text("SELECT id, unique_id, student_id, cohort_assignment_id FROM student_simulation_instances WHERE unique_id = :unique_id AND student_id = :student_id"),
            {"unique_id": instance_unique_id, "student_id": current_user.id}
        ).first()
        
        instance = None
        if result:
            instance_id = result[0]
            logger.info(f"Found instance via direct SQL: id={instance_id}, unique_id={result[1]}, student_id={result[2]}, cohort_assignment_id={result[3]}")
            
            # Use populate_existing() to ensure we get fresh data from database, not cached session state
            instance = db.query(StudentSimulationInstance).options(
                selectinload(StudentSimulationInstance.cohort_assignment).selectinload(CohortSimulation.simulation)
            ).populate_existing().filter(StudentSimulationInstance.id == instance_id).first()
            
            if instance:
                logger.info(f"Successfully loaded instance: unique_id={instance.unique_id}, cohort_assignment_id={instance.cohort_assignment_id}")
            else:
                logger.error(f"Direct SQL found instance id={instance_id}, but ORM query returned None! This suggests the instance was deleted between queries.")
                # Fall through to error handling below
        else:
            # Instance not found with student_id filter - query without student filter to check ownership
            # Use populate_existing() to ensure fresh data
            instance = db.query(StudentSimulationInstance).options(
                selectinload(StudentSimulationInstance.cohort_assignment).selectinload(CohortSimulation.simulation)
            ).populate_existing().filter(
                StudentSimulationInstance.unique_id == instance_unique_id,
                StudentSimulationInstance.student_id == current_user.id
            ).first()
        
        if not instance:
            # Try to find if instance exists at all (for debugging) - use direct SQL for freshness
            instance_check = db.execute(
                text("SELECT student_id FROM student_simulation_instances WHERE unique_id = :unique_id"),
                {"unique_id": instance_unique_id}
            ).first()
            
            if instance_check:
                owner_student_id = instance_check[0]
                logger.warning(f"Instance {instance_unique_id} exists but belongs to student_id={owner_student_id}, not {current_user.id}")
                raise HTTPException(status_code=403, detail="This simulation instance belongs to a different student")
            else:
                # Instance doesn't exist - query all instances for this student for debugging
                logger.warning(f"Instance {instance_unique_id} not found in database. Searching for correct instance...")
                
                # Use direct SQL for fresh data without loading full ORM objects
                all_student_instances = db.execute(
                    text("SELECT unique_id, cohort_assignment_id, status FROM student_simulation_instances WHERE student_id = :student_id"),
                    {"student_id": current_user.id}
                ).all()
                
                logger.info(f"Found {len(all_student_instances)} total instances for student {current_user.id}")
                for inst in all_student_instances:
                    logger.info(f"  - Instance unique_id={inst[0]}, cohort_assignment_id={inst[1]}, status={inst[2]}")
                
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
                detail="Simulation not found. The simulation associated with this assignment may have been deleted. Please contact your instructor."
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
            "completed_scene_ids": result.completed_scene_ids if hasattr(result, 'completed_scene_ids') else [],
            "sandbox_id": result.sandbox_id if hasattr(result, 'sandbox_id') else None,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in start_simulation_from_instance: {e!r}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start simulation: {e!s}") from e


@router.post("/{instance_unique_id}/reset-simulation", response_model=dict)
async def reset_simulation_from_instance(
    instance_unique_id: str,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """
    Reset a completed simulation to allow the student to re-run it.

    This will:
    - Delete all existing conversation history and progress
    - Clear all grading data (AI grade, professor grade)
    - Reset the instance status to allow starting fresh
    - Increment the attempts counter
    - Start a new simulation session

    WARNING: This permanently deletes the previous grade and cannot be undone.
    """
    try:
        logger.info(f"Resetting simulation for instance {instance_unique_id} by student {current_user.id}")

        # Find the instance
        instance = db.query(StudentSimulationInstance).options(
            selectinload(StudentSimulationInstance.cohort_assignment).selectinload(CohortSimulation.simulation)
        ).filter(
            StudentSimulationInstance.unique_id == instance_unique_id,
            StudentSimulationInstance.student_id == current_user.id
        ).first()

        if not instance:
            raise HTTPException(status_code=404, detail="Simulation instance not found")

        # Verify the simulation is in a completed/graded state (only allow reset if done)
        if instance.status not in ["completed", "submitted", "graded"]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot reset a simulation that is not completed. Current status: {instance.status}"
            )

        # Get simulation_id from cohort assignment
        if not instance.cohort_assignment:
            raise HTTPException(status_code=400, detail="Instance is not associated with a cohort assignment")

        simulation_id = instance.cohort_assignment.simulation_id

        # Import necessary services
        from modules.simulation.repository import SimulationRepository
        from modules.simulation.services.lifecycle_service import LifecycleService
        from datetime import datetime, timezone

        repository = SimulationRepository(db)

        # Verify simulation exists and is not soft-deleted before any destructive operations
        simulation = repository.get_simulation_by_id(simulation_id)
        if not simulation:
            logger.error(
                f"Simulation {simulation_id} not found or deleted for instance {instance.unique_id} "
                f"(cohort_assignment_id={instance.cohort_assignment_id}). "
                f"Reset blocked — the simulation may have been deleted but instances still reference it."
            )
            raise HTTPException(
                status_code=404,
                detail="Simulation not found. The simulation associated with this assignment may have been deleted. Please contact your instructor."
            )

        lifecycle_service = LifecycleService(db, repository)

        # Delete existing progress (this cascades to conversation logs, agent sessions, etc.)
        if instance.user_progress_id:
            logger.info(f"Deleting existing progress for user_progress_id={instance.user_progress_id}")
            repository.delete_all_user_progress_for_simulation(current_user.id, simulation_id)

        # Clear all grading data from the instance
        instance.ai_grade = None
        instance.ai_feedback = None
        instance.ai_graded_at = None
        instance.grade = None
        instance.feedback = None
        instance.graded_by = None
        instance.graded_at = None
        instance.grade_status = "not_graded"

        # Reset status fields
        instance.status = "not_started"
        instance.completed_at = None
        instance.submitted_at = None

        # Reset performance metrics but preserve attempts count
        instance.completion_percentage = 0.0
        instance.total_time_spent = 0
        instance.hints_used = 0
        instance.attempts_count = (instance.attempts_count or 0) + 1

        # Clear the user_progress_id reference
        instance.user_progress_id = None

        # Commit the instance changes
        db.commit()
        logger.info(f"Instance {instance_unique_id} reset successfully. Attempts: {instance.attempts_count}")

        # Now start a fresh simulation
        result = await lifecycle_service.start_simulation(
            user_id=current_user.id,
            simulation_id=simulation_id
        )

        # Link the new progress to the instance
        instance = db.query(StudentSimulationInstance).filter(
            StudentSimulationInstance.unique_id == instance_unique_id
        ).first()

        if instance:
            instance.user_progress_id = result.user_progress_id
            instance.status = "in_progress"
            instance.started_at = datetime.now(timezone.utc)
            db.commit()
            logger.info(f"Linked new progress to instance {instance_unique_id}: user_progress_id={result.user_progress_id}")

        return {
            "success": True,
            "message": "Simulation reset successfully",
            "user_progress_id": result.user_progress_id,
            "simulation": result.simulation,
            "current_scene": result.current_scene,
            "simulation_status": result.simulation_status,
            "all_scenes": result.all_scenes,
            "attempts_count": instance.attempts_count if instance else 1
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in reset_simulation_from_instance: {e!r}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to reset simulation: {e!s}") from e

