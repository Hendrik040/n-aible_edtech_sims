"""
Cohorts API endpoints for educational group management
Handles cohort creation, student enrollment, and simulation assignments
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import and_, or_, desc, func
from sqlalchemy.sql.functions import coalesce
from typing import List, Optional
from datetime import datetime, timezone
import secrets
import logging

logger = logging.getLogger(__name__)

from database.connection import get_db
from utilities.auth import get_current_user, require_admin
from middleware.role_auth import require_professor
from utilities.debug_logging import debug_log
from database.models import (
    Cohort, CohortStudent, CohortSimulation, User, UserProgress, Scenario, 
    StudentSimulationInstance, ScenarioScene, SceneProgress, generate_cohort_id
)
from database.schemas import (
    CohortCreate, CohortUpdate, CohortResponse, CohortListResponse,
    CohortStudentCreate, CohortStudentUpdate, CohortStudentResponse,
    CohortSimulationCreate, CohortSimulationUpdate, CohortSimulationResponse
)

router = APIRouter(prefix="/professor/cohorts", tags=["Professor Cohorts"])

# --- COHORT CRUD ENDPOINTS ---

@router.get("", response_model=List[CohortListResponse])
@router.get("/", response_model=List[CohortListResponse])
async def get_cohorts(
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None)
):
    """Get all cohorts with optional filtering"""
    try:
        query = db.query(Cohort)
        
        # Filter by creator (users can only see their own cohorts unless admin)
        if current_user.role != "admin":
            query = query.filter(Cohort.created_by == current_user.id)
        
        # Apply search filter
        if search:
            query = query.filter(
                or_(
                    Cohort.title.ilike(f"%{search}%"),
                    Cohort.description.ilike(f"%{search}%"),
                    Cohort.course_code.ilike(f"%{search}%")
                )
            )
        
        # Apply status filter
        if status:
            if status == "active":
                query = query.filter(Cohort.is_active == True)
            elif status == "inactive":
                query = query.filter(Cohort.is_active == False)
        
        # Order by creation date (newest first)
        query = query.order_by(desc(Cohort.created_at))
        
        # Create subqueries for counts to optimize performance
        student_count_subquery = db.query(
            CohortStudent.cohort_id,
            func.count(CohortStudent.id).label('student_count')
        ).filter(
            CohortStudent.status == "approved"
        ).group_by(CohortStudent.cohort_id).subquery()
        
        simulation_count_subquery = db.query(
            CohortSimulation.cohort_id,
            func.count(CohortSimulation.id).label('simulation_count')
        ).join(
            Scenario, CohortSimulation.simulation_id == Scenario.id
        ).filter(
            Scenario.deleted_at.is_(None),  # Exclude soft-deleted scenarios
            Scenario.is_draft == False,
            Scenario.status == "active"
        ).group_by(CohortSimulation.cohort_id).subquery()
        
        # Main query with left joins to get counts in single query
        cohorts_with_counts = query.outerjoin(
            student_count_subquery,
            Cohort.id == student_count_subquery.c.cohort_id
        ).outerjoin(
            simulation_count_subquery,
            Cohort.id == simulation_count_subquery.c.cohort_id
        ).add_columns(
            coalesce(student_count_subquery.c.student_count, 0).label('student_count'),
            coalesce(simulation_count_subquery.c.simulation_count, 0).label('simulation_count')
        ).offset(skip).limit(limit).all()
        
        # Build response with counts from single query
        result = []
        for cohort_row in cohorts_with_counts:
            cohort = cohort_row[0]  # The Cohort object is first in the tuple
            student_count = cohort_row[1]  # student_count from coalesce
            simulation_count = cohort_row[2]  # simulation_count from coalesce
            
            result.append(CohortListResponse(
                id=cohort.id,
                unique_id=cohort.unique_id,
                title=cohort.title,
                description=cohort.description,
                course_code=cohort.course_code,
                semester=cohort.semester,
                year=cohort.year,
                max_students=cohort.max_students,
                is_active=cohort.is_active,
                created_by=cohort.created_by,
                created_at=cohort.created_at,
                student_count=student_count,
                simulation_count=simulation_count
            ))
        
        return result
    except Exception as e:
        debug_log(f"Error in get_cohorts: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# --- REFRESH ASSIGNED SIMULATIONS (ONE-TIME ON LOAD) ---
@router.post("/refresh-assignments")
async def refresh_assigned_simulations(
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Recalculate time_spent for all student instances in the professor's cohorts.
    This endpoint is lightweight and safe to call on page load.
    """
    try:
        cohorts = db.query(Cohort).filter(Cohort.created_by == current_user.id).all()
        for cohort in cohorts:
            assignments = db.query(CohortSimulation).filter(CohortSimulation.cohort_id == cohort.id).all()
            for assignment in assignments:
                instances = db.query(StudentSimulationInstance).filter(
                    StudentSimulationInstance.cohort_assignment_id == assignment.id
                ).all()
                for instance in instances:
                    # Prefer started_at -> completed_at; fallback to user_progress
                    start_dt = instance.started_at
                    end_dt = instance.completed_at
                    if instance.user_progress_id:
                        up = db.query(UserProgress).filter(UserProgress.id == instance.user_progress_id).first()
                        if not start_dt:
                            start_dt = up.created_at if up else None
                        if not end_dt:
                            end_dt = (up.last_activity if up else None) or (up.updated_at if up else None)
                        # Recompute completion percentage
                        if up:
                            # If completed/graded, force 100%
                            if up.simulation_status in ["completed", "graded"] or instance.status in ["completed", "graded", "submitted"]:
                                if instance.completion_percentage != 100.0:
                                    instance.completion_percentage = 100.0
                            else:
                                total_scenes = db.query(ScenarioScene).filter(ScenarioScene.scenario_id == up.scenario_id).count()
                                completed_scenes = db.query(SceneProgress).filter(
                                    SceneProgress.user_progress_id == up.id,
                                    SceneProgress.status == "completed"
                                ).count()
                                if total_scenes > 0:
                                    instance.completion_percentage = (completed_scenes / total_scenes) * 100.0
                    if not end_dt:
                        end_dt = datetime.now(timezone.utc)
                    if start_dt:
                        if start_dt.tzinfo is None:
                            start_dt = start_dt.replace(tzinfo=timezone.utc)
                        if end_dt and end_dt.tzinfo is None:
                            end_dt = end_dt.replace(tzinfo=timezone.utc)
                        delta = end_dt - start_dt
                        instance.total_time_spent = max(0, int(delta.total_seconds()))
                db.commit()
        return {"status": "ok", "refreshed": True}
    except Exception as e:
        debug_log(f"Error in refresh_assigned_simulations: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to refresh assignments")

@router.get("/admin/all", response_model=List[CohortListResponse])
async def get_all_cohorts_admin(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """Admin-only endpoint to get all cohorts across all users"""
    query = db.query(Cohort).order_by(desc(Cohort.created_at))
    
    # Create subqueries for counts
    student_count_subquery = db.query(
        CohortStudent.cohort_id,
        func.count(CohortStudent.id).label('student_count')
    ).filter(
        CohortStudent.status == "approved"
    ).group_by(CohortStudent.cohort_id).subquery()
    
    simulation_count_subquery = db.query(
            CohortSimulation.cohort_id,
            func.count(CohortSimulation.id).label('simulation_count')
        ).join(
            Scenario, CohortSimulation.simulation_id == Scenario.id
        ).filter(
            Scenario.deleted_at.is_(None),  # Exclude soft-deleted scenarios
            Scenario.is_draft == False,
            Scenario.status == "active"
        ).group_by(CohortSimulation.cohort_id).subquery()
    
    # Main query with left joins to get counts in single query
    cohorts_with_counts = query.outerjoin(
        student_count_subquery,
        Cohort.id == student_count_subquery.c.cohort_id
    ).outerjoin(
        simulation_count_subquery,
        Cohort.id == simulation_count_subquery.c.cohort_id
    ).add_columns(
        coalesce(student_count_subquery.c.student_count, 0).label('student_count'),
        coalesce(simulation_count_subquery.c.simulation_count, 0).label('simulation_count')
    ).offset(skip).limit(limit).all()
    
    # Build response with counts from single query
    result = []
    for cohort_row in cohorts_with_counts:
        cohort = cohort_row[0]  # The Cohort object is first in the tuple
        student_count = cohort_row[1]  # student_count from coalesce
        simulation_count = cohort_row[2]  # simulation_count from coalesce
        
        result.append(CohortListResponse(
            id=cohort.id,
            unique_id=cohort.unique_id,
            title=cohort.title,
            description=cohort.description,
            course_code=cohort.course_code,
            semester=cohort.semester,
            year=cohort.year,
            max_students=cohort.max_students,
            is_active=cohort.is_active,
            created_by=cohort.created_by,
            created_at=cohort.created_at,
            student_count=student_count,
            simulation_count=simulation_count
        ))
    
    return result

@router.get("/{cohort_unique_id}", response_model=CohortResponse)
async def get_cohort(
    cohort_unique_id: str,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get a specific cohort with students and simulations"""
    cohort = db.query(Cohort).filter(Cohort.unique_id == cohort_unique_id).first()
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    # Check permissions (creator or admin)
    if cohort.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to view this cohort")
    
    # Get students with user details using eager loading
    students_query = db.query(CohortStudent, User).join(
        User, CohortStudent.student_id == User.id
    ).filter(CohortStudent.cohort_id == cohort.id)
    
    students = []
    for cohort_student, user in students_query:
        students.append(CohortStudentResponse(
            id=cohort_student.id,
            student_id=cohort_student.student_id,
            student_name=user.full_name,
            student_email=user.email,
            status=cohort_student.status,
            enrollment_date=cohort_student.enrollment_date,
            approved_at=cohort_student.approved_at
        ))
    
    # Get simulations - only include active (non-draft, non-deleted) simulations
    simulations_query = db.query(CohortSimulation).join(
        Scenario, CohortSimulation.simulation_id == Scenario.id
    ).filter(
        CohortSimulation.cohort_id == cohort.id,
        Scenario.deleted_at.is_(None),  # Exclude soft-deleted scenarios
        Scenario.is_draft == False,  # Only show active simulations
        Scenario.status == "active"   # Ensure status is active (not draft or archived)
    )
    
    simulations = []
    for cohort_simulation in simulations_query:
        simulations.append(CohortSimulationResponse(
            id=cohort_simulation.id,
            simulation_id=cohort_simulation.simulation_id,
            assigned_by=cohort_simulation.assigned_by,
            assigned_at=cohort_simulation.assigned_at,
            due_date=cohort_simulation.due_date,
            is_required=cohort_simulation.is_required
        ))
    
    return CohortResponse(
        id=cohort.id,
        unique_id=cohort.unique_id,
        title=cohort.title,
        description=cohort.description,
        course_code=cohort.course_code,
        semester=cohort.semester,
        year=cohort.year,
        max_students=cohort.max_students,
        auto_approve=cohort.auto_approve,
        allow_self_enrollment=cohort.allow_self_enrollment,
        is_active=cohort.is_active,
        created_by=cohort.created_by,
        created_at=cohort.created_at,
        updated_at=cohort.updated_at,
        students=students,
        simulations=simulations
    )

@router.post("", response_model=CohortResponse)
@router.post("/", response_model=CohortResponse)
async def create_cohort(
    cohort_data: CohortCreate,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Create a new cohort"""
    # Validate max_students if provided
    if cohort_data.max_students is not None and cohort_data.max_students <= 0:
        raise HTTPException(status_code=400, detail="Max students must be positive")
    
    # Generate short, user-friendly ID for the cohort
    unique_id = generate_cohort_id()
    
    # Create cohort
    cohort = Cohort(
        unique_id=unique_id,
        title=cohort_data.title,
        description=cohort_data.description,
        course_code=cohort_data.course_code,
        semester=cohort_data.semester,
        year=cohort_data.year,
        max_students=cohort_data.max_students,
        auto_approve=cohort_data.auto_approve,
        allow_self_enrollment=cohort_data.allow_self_enrollment,
        created_by=current_user.id
    )
    
    db.add(cohort)
    db.commit()
    db.refresh(cohort)
    
    return CohortResponse(
        id=cohort.id,
        unique_id=cohort.unique_id,
        title=cohort.title,
        description=cohort.description,
        course_code=cohort.course_code,
        semester=cohort.semester,
        year=cohort.year,
        max_students=cohort.max_students,
        auto_approve=cohort.auto_approve,
        allow_self_enrollment=cohort.allow_self_enrollment,
        is_active=cohort.is_active,
        created_by=cohort.created_by,
        created_at=cohort.created_at,
        updated_at=cohort.updated_at,
        students=[],
        simulations=[]
    )

@router.put("/{cohort_unique_id}", response_model=CohortResponse)
async def update_cohort(
    cohort_unique_id: str,
    cohort_data: CohortUpdate,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Update a cohort"""
    cohort = db.query(Cohort).filter(Cohort.unique_id == cohort_unique_id).first()
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    # Check permissions
    if cohort.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to update this cohort")
    
    # Update fields
    update_data = cohort_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(cohort, field, value)
    
    db.commit()
    db.refresh(cohort)
    
    # Return updated cohort (simplified response)
    return CohortResponse(
        id=cohort.id,
        title=cohort.title,
        description=cohort.description,
        course_code=cohort.course_code,
        semester=cohort.semester,
        year=cohort.year,
        max_students=cohort.max_students,
        auto_approve=cohort.auto_approve,
        allow_self_enrollment=cohort.allow_self_enrollment,
        is_active=cohort.is_active,
        created_by=cohort.created_by,
        created_at=cohort.created_at,
        updated_at=cohort.updated_at,
        students=[],
        simulations=[]
    )

@router.delete("/{cohort_unique_id}")
async def delete_cohort(
    cohort_unique_id: str,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Delete a cohort and all related data"""
    cohort = db.query(Cohort).filter(Cohort.unique_id == cohort_unique_id).first()
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    # Check permissions
    if cohort.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to delete this cohort")
    
    try:
        # Get counts before deletion for logging
        student_count = db.query(CohortStudent).filter(CohortStudent.cohort_id == cohort.id).count()
        simulation_count = db.query(CohortSimulation).filter(CohortSimulation.cohort_id == cohort.id).count()
        
        # Check if there are any active simulations that might cause issues
        active_simulations = db.query(CohortSimulation).filter(
            CohortSimulation.cohort_id == cohort.id
        ).all()
        
        # Delete related records first to ensure clean deletion
        # This is more explicit than relying only on cascade
        for simulation in active_simulations:
            db.delete(simulation)
        
        # Delete student enrollments
        student_enrollments = db.query(CohortStudent).filter(CohortStudent.cohort_id == cohort.id).all()
        for enrollment in student_enrollments:
            db.delete(enrollment)
        
        # Finally delete the cohort itself
        db.delete(cohort)
        db.commit()
        
        # Log the deletion for audit purposes
        debug_log(f"Cohort '{cohort.title}' (ID: {cohort.unique_id}) deleted by user {current_user.id}")
        debug_log(f"Deleted {student_count} student enrollments and {simulation_count} simulation assignments")
        
        return {
            "message": "Cohort deleted successfully",
            "deleted_students": student_count,
            "deleted_simulations": simulation_count
        }
        
    except Exception as e:
        db.rollback()
        debug_log(f"Error deleting cohort {cohort.unique_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete cohort. Please try again.")

# --- STUDENT MANAGEMENT ENDPOINTS ---

@router.get("/{cohort_unique_id}/students", response_model=List[CohortStudentResponse])
async def get_cohort_students(
    cohort_unique_id: str,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get all students in a cohort"""
    # Check if cohort exists and user has access
    cohort = db.query(Cohort).filter(Cohort.unique_id == cohort_unique_id).first()
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    if cohort.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to view this cohort")
    
    # Get students
    students_query = db.query(CohortStudent, User).join(
        User, CohortStudent.student_id == User.id
    ).filter(CohortStudent.cohort_id == cohort.id)
    
    students = []
    for cohort_student, user in students_query:
        students.append(CohortStudentResponse(
            id=cohort_student.id,
            student_id=cohort_student.student_id,
            student_name=user.full_name,
            student_email=user.email,
            status=cohort_student.status,
            enrollment_date=cohort_student.enrollment_date,
            approved_at=cohort_student.approved_at
        ))
    
    return students

@router.post("/{cohort_id}/students", response_model=CohortStudentResponse)
async def add_student_to_cohort(
    cohort_id: int,
    student_data: CohortStudentCreate,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Add a student to a cohort"""
    # Check if cohort exists and user has access
    cohort = db.query(Cohort).filter(Cohort.id == cohort_id).first()
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    if cohort.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to manage this cohort")
    
    # Check if student exists
    student = db.query(User).filter(User.id == student_data.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    # Check if student is already enrolled
    existing_enrollment = db.query(CohortStudent).filter(
        CohortStudent.cohort_id == cohort_id,
        CohortStudent.student_id == student_data.student_id
    ).first()
    
    if existing_enrollment:
        raise HTTPException(status_code=400, detail="Student is already enrolled in this cohort")
    
    # Create enrollment
    cohort_student = CohortStudent(
        cohort_id=cohort_id,
        student_id=student_data.student_id,
        status=student_data.status
    )
    
    db.add(cohort_student)
    db.commit()
    db.refresh(cohort_student)
    
    return CohortStudentResponse(
        id=cohort_student.id,
        student_id=cohort_student.student_id,
        student_name=student.full_name,
        student_email=student.email,
        status=cohort_student.status,
        enrollment_date=cohort_student.enrollment_date,
        approved_at=cohort_student.approved_at
    )

@router.put("/{cohort_unique_id}/students/{student_id}", response_model=CohortStudentResponse)
async def update_student_enrollment(
    cohort_unique_id: str,
    student_id: int,
    student_data: CohortStudentUpdate,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Update a student's enrollment status in a cohort"""
    # Check if cohort exists and user has access
    cohort = db.query(Cohort).filter(Cohort.unique_id == cohort_unique_id).first()
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    if cohort.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to manage this cohort")
    
    # Check if student enrollment exists
    cohort_student = db.query(CohortStudent).filter(
        CohortStudent.cohort_id == cohort.id,
        CohortStudent.student_id == student_id
    ).first()
    
    if not cohort_student:
        raise HTTPException(status_code=404, detail="Student not enrolled in this cohort")
    
    # Get student user details
    student = db.query(User).filter(User.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    # Update enrollment status
    update_data = student_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(cohort_student, field, value)
    
    # Set approval timestamp if status is being changed to approved
    if student_data.status == "approved" and cohort_student.status != "approved":
        cohort_student.approved_at = datetime.utcnow()
        cohort_student.approved_by = current_user.id
    
    db.commit()
    db.refresh(cohort_student)
    
    return CohortStudentResponse(
        id=cohort_student.id,
        student_id=cohort_student.student_id,
        student_name=student.full_name,
        student_email=student.email,
        status=cohort_student.status,
        enrollment_date=cohort_student.enrollment_date,
        approved_at=cohort_student.approved_at
    )

@router.delete("/{cohort_unique_id}/students/{student_id}")
async def remove_student_from_cohort(
    cohort_unique_id: str,
    student_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Remove a student from a cohort"""
    try:
        logger.info(f"Removing student {student_id} from cohort {cohort_unique_id} by user {current_user.id}")
        
        # Check if cohort exists and user has access
        cohort = db.query(Cohort).filter(Cohort.unique_id == cohort_unique_id).first()
        if not cohort:
            logger.warning(f"Cohort {cohort_unique_id} not found")
            raise HTTPException(status_code=404, detail="Cohort not found")
        
        if cohort.created_by != current_user.id and current_user.role != "admin":
            logger.warning(f"User {current_user.id} not authorized for cohort {cohort_unique_id}")
            raise HTTPException(status_code=403, detail="Not authorized to manage this cohort")
        
        # Find the student enrollment
        enrollment = db.query(CohortStudent).filter(
            CohortStudent.cohort_id == cohort.id,
            CohortStudent.student_id == student_id
        ).first()
        
        if not enrollment:
            logger.warning(f"Student {student_id} not found in cohort {cohort_unique_id}")
            raise HTTPException(status_code=404, detail="Student not found in this cohort")
        
        # Get student name for logging
        student = db.query(User).filter(User.id == student_id).first()
        student_name = student.full_name if student else f"Student {student_id}"
        
        # Delete student simulation instances for this cohort first
        cohort_assignments = db.query(CohortSimulation).filter(
            CohortSimulation.cohort_id == cohort.id
        ).all()
        
        deleted_instances = 0
        for assignment in cohort_assignments:
            instances = db.query(StudentSimulationInstance).filter(
                StudentSimulationInstance.cohort_assignment_id == assignment.id,
                StudentSimulationInstance.student_id == student_id
            ).all()
            for instance in instances:
                db.delete(instance)
                deleted_instances += 1
        
        logger.info(f"Deleted {deleted_instances} simulation instances for student {student_id}")
        
        # Delete the enrollment
        db.delete(enrollment)
        db.commit()
        
        logger.info(f"Successfully removed {student_name} from cohort {cohort.title}")
        return {"message": "Student removed from cohort successfully"}
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error removing student from cohort: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to remove student: {str(e)}")
# --- SIMULATION MANAGEMENT ENDPOINTS ---

@router.get("/{cohort_unique_id}/simulations", response_model=List[CohortSimulationResponse])
async def get_cohort_simulations(
    cohort_unique_id: str,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get all simulations assigned to a cohort"""
    # Check if cohort exists and user has access
    cohort = db.query(Cohort).filter(Cohort.unique_id == cohort_unique_id).first()
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    if cohort.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to view this cohort")
    
    # Get simulations with scenario details - only include active (non-draft) simulations
    # Use selectinload to eager load scenario data to avoid N+1 queries
    simulations_query = db.query(CohortSimulation).options(
        selectinload(CohortSimulation.simulation)
    ).join(
        Scenario, CohortSimulation.simulation_id == Scenario.id
    ).filter(
        CohortSimulation.cohort_id == cohort.id,
        Scenario.is_draft == False,  # Only show active simulations
        Scenario.status == "active"   # Ensure status is active (not draft or archived)
    )
    
    simulations = simulations_query.all()
    
    debug_log(f"Found {len(simulations)} active simulations for cohort {cohort.id}")
    
    result = []
    for cohort_simulation in simulations:
        debug_log(f"Processing simulation {cohort_simulation.id} with simulation_id {cohort_simulation.simulation_id}")
        
        # Get the scenario details from the relationship (already loaded)
        scenario = cohort_simulation.simulation
        
        debug_log(f"Found scenario: {scenario}")
        
        simulation_data = {
            "id": cohort_simulation.id,
            "simulation_id": cohort_simulation.simulation_id,
            "assigned_by": cohort_simulation.assigned_by,
            "assigned_at": cohort_simulation.assigned_at,
            "due_date": cohort_simulation.due_date,
            "is_required": cohort_simulation.is_required,
        }
        
        if scenario:
            debug_log(f"Adding scenario details: {scenario.title}")
            simulation_data["simulation"] = {
                "id": scenario.id,
                "title": scenario.title,
                "description": scenario.description,
                "is_draft": scenario.is_draft,
                "status": scenario.status
            }
        else:
            debug_log(f"Scenario not found for ID {cohort_simulation.simulation_id}")
            # Fallback if scenario not found (shouldn't happen with join, but kept for safety)
            simulation_data["simulation"] = {
                "id": cohort_simulation.simulation_id,
                "title": f"Scenario {cohort_simulation.simulation_id}",
                "description": "Scenario details not found",
                "is_draft": False,
                "status": "unknown"
            }
        
        debug_log(f"Final simulation_data: {simulation_data}")
        result.append(simulation_data)
    
    debug_log(f"Returning {len(result)} simulations")
    return result

@router.post("/{cohort_id}/simulations", response_model=CohortSimulationResponse)
async def assign_simulation_to_cohort(
    cohort_id: int,
    simulation_data: CohortSimulationCreate,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Assign a simulation to a cohort"""
    # Check if cohort exists and user has access
    cohort = db.query(Cohort).filter(Cohort.id == cohort_id).first()
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    if cohort.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to manage this cohort")
    
    # Check if scenario exists and is not deleted
    scenario = db.query(Scenario).filter(
        Scenario.id == simulation_data.simulation_id,
        Scenario.deleted_at.is_(None)  # Exclude soft-deleted scenarios
    ).first()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found or has been deleted")
    
    # Only allow assigning published/active simulations (not drafts)
    if scenario.is_draft:
        raise HTTPException(status_code=400, detail="Cannot assign draft simulations. Please publish the simulation first.")
    
    # Create assignment
    cohort_simulation = CohortSimulation(
        cohort_id=cohort_id,
        simulation_id=simulation_data.simulation_id,
        assigned_by=current_user.id,
        due_date=simulation_data.due_date,
        is_required=simulation_data.is_required
    )
    
    db.add(cohort_simulation)
    db.commit()
    db.refresh(cohort_simulation)
    
    # Create student simulation instances and send notifications
    try:
        from services.notification_service import notification_service
        from database.models import StudentSimulationInstance, CohortStudent
        
        # Get all students in the cohort
        students = db.query(CohortStudent).filter(
            CohortStudent.cohort_id == cohort_id,
            CohortStudent.status == "approved"
        ).all()
        
        # Create student simulation instances and notifications for each student
        for student in students:
            # Create UserProgress record first
            user_progress = UserProgress(
                user_id=student.student_id,
                scenario_id=simulation_data.simulation_id,
                simulation_status="not_started"
            )
            db.add(user_progress)
            db.flush()  # Flush to get the ID
            
            # Create student simulation instance with user_progress_id
            student_instance = StudentSimulationInstance(
                cohort_assignment_id=cohort_simulation.id,
                student_id=student.student_id,
                user_progress_id=user_progress.id
            )
            db.add(student_instance)
            
            # Create notification
            notification_service.create_simulation_assignment_notification(
                db, 
                student.student_id, 
                cohort_simulation,
                scenario,
                cohort
            )
        
        db.commit()  # Commit the student instances
        logger.info(f"Created simulation instances and notifications for {len(students)} students in cohort {cohort_id}")
    except Exception as e:
        logger.error(f"Failed to create simulation instances and notifications: {str(e)}")
        db.rollback()
    
    return CohortSimulationResponse(
        id=cohort_simulation.id,
        simulation_id=cohort_simulation.simulation_id,
        assigned_by=cohort_simulation.assigned_by,
        assigned_at=cohort_simulation.assigned_at,
        due_date=cohort_simulation.due_date,
        is_required=cohort_simulation.is_required
    )

@router.delete("/{cohort_id}/simulations/{simulation_assignment_id}")
async def remove_simulation_from_cohort(
    cohort_id: int,
    simulation_assignment_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Remove a simulation assignment from a cohort"""
    try:
        logger.info(f"DELETE request: cohort_id={cohort_id}, simulation_assignment_id={simulation_assignment_id}, user_id={current_user.id}")
        
        # Check if cohort exists and user has access
        cohort = db.query(Cohort).filter(Cohort.id == cohort_id).first()
        if not cohort:
            logger.warning(f"Cohort {cohort_id} not found")
            raise HTTPException(status_code=404, detail="Cohort not found")
        
        if cohort.created_by != current_user.id and current_user.role != "admin":
            logger.warning(f"User {current_user.id} not authorized for cohort {cohort_id}")
            raise HTTPException(status_code=403, detail="Not authorized to manage this cohort")
        
        # Check if simulation assignment exists
        simulation_assignment = db.query(CohortSimulation).filter(
            CohortSimulation.id == simulation_assignment_id,
            CohortSimulation.cohort_id == cohort_id
        ).first()
        
        if not simulation_assignment:
            logger.warning(f"Simulation assignment {simulation_assignment_id} not found in cohort {cohort_id}")
            raise HTTPException(status_code=404, detail="Simulation assignment not found")
        
        # Delete any student simulation instances first to avoid foreign key constraints
        student_instances = db.query(StudentSimulationInstance).filter(
            StudentSimulationInstance.cohort_assignment_id == simulation_assignment_id
        ).all()
        
        for instance in student_instances:
            db.delete(instance)
        
        logger.info(f"Deleted {len(student_instances)} student instances for assignment {simulation_assignment_id}")
        
        # Delete the assignment
        db.delete(simulation_assignment)
        db.commit()
        
        logger.info(f"Successfully removed simulation assignment {simulation_assignment_id} from cohort {cohort_id}")
        return {"message": "Simulation removed from cohort successfully"}
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error removing simulation from cohort: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to remove simulation: {str(e)}")

@router.get("/debug/scenario/{scenario_id}")
async def debug_scenario(
    scenario_id: int,
    db: Session = Depends(get_db)
):
    """Debug endpoint to check if a scenario exists"""
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    
    if scenario:
        return {
            "found": True,
            "scenario": {
                "id": scenario.id,
                "title": scenario.title,
                "description": scenario.description,
                "is_draft": scenario.is_draft,
                "status": scenario.status
            }
        }
    else:
        return {
            "found": False,
            "scenario_id": scenario_id,
            "message": "Scenario not found"
        }
