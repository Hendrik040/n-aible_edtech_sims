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
    """Start or resume a simulation from a student simulation instance (stub).

    The legacy implementation depended on the LangChain-backed simulation
    runtime, which has been removed from backend_v2. The endpoint is kept as
    a stub so that FastAPI routing and OpenAPI docs stay stable until the
    runtime is rebuilt on the Claude Agent SDK.
    """
    raise NotImplementedError(
        "start_simulation_from_instance is not yet available in backend_v2 — "
        "the simulation runtime is being rebuilt on the Claude Agent SDK."
    )



@router.post("/{instance_unique_id}/reset-simulation", response_model=dict)
async def reset_simulation_from_instance(
    instance_unique_id: str,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Reset a completed simulation so the student can re-run it (stub).

    Stubbed in backend_v2 alongside the simulation runtime rewrite. Will be
    reimplemented on top of the Claude Agent SDK.
    """
    raise NotImplementedError(
        "reset_simulation_from_instance is not yet available in backend_v2 — "
        "the simulation runtime is being rebuilt on the Claude Agent SDK."
    )


