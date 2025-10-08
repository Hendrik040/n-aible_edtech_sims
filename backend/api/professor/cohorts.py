"""
Cohorts API endpoints for educational group management
Handles cohort creation, student enrollment, and simulation assignments
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import and_, or_, desc, func
from sqlalchemy.sql.functions import coalesce
from typing import List, Optional
from datetime import datetime
import secrets
import logging

logger = logging.getLogger(__name__)

from database.connection import get_db
from utilities.auth import get_current_user, require_admin
from middleware.role_auth import require_professor
from utilities.debug_logging import debug_log
from database.models import (
    Cohort, CohortStudent, CohortSimulation, User, UserProgress, Scenario, generate_cohort_id
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
        
        # Get basic cohorts first
        cohorts = query.offset(skip).limit(limit).all()
        
        # Build response with simple counts
        result = []
        for cohort in cohorts:
            # Get student count
            student_count = db.query(CohortStudent).filter(
                CohortStudent.cohort_id == cohort.id,
                CohortStudent.status == "approved"
            ).count()
            
            # Get simulation count
            simulation_count = db.query(CohortSimulation).filter(
                CohortSimulation.cohort_id == cohort.id
            ).count()
            
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
    
    # Get simulations
    simulations_query = db.query(CohortSimulation).filter(
        CohortSimulation.cohort_id == cohort.id
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
    
    # Get simulations with scenario details
    simulations = db.query(CohortSimulation).filter(
        CohortSimulation.cohort_id == cohort.id
    ).all()
    
    debug_log(f"Found {len(simulations)} simulations for cohort {cohort.id}")
    
    result = []
    for cohort_simulation in simulations:
        debug_log(f"Processing simulation {cohort_simulation.id} with simulation_id {cohort_simulation.simulation_id}")
        
        # Get the scenario details
        scenario = db.query(Scenario).filter(Scenario.id == cohort_simulation.simulation_id).first()
        
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
            # Fallback if scenario not found
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
    
    # Check if scenario exists
    scenario = db.query(Scenario).filter(Scenario.id == simulation_data.simulation_id).first()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    
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
    # Check if cohort exists and user has access
    cohort = db.query(Cohort).filter(Cohort.id == cohort_id).first()
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    if cohort.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to manage this cohort")
    
    # Check if simulation assignment exists
    simulation_assignment = db.query(CohortSimulation).filter(
        CohortSimulation.id == simulation_assignment_id,
        CohortSimulation.cohort_id == cohort_id
    ).first()
    
    if not simulation_assignment:
        raise HTTPException(status_code=404, detail="Simulation assignment not found")
    
    # Delete the assignment
    db.delete(simulation_assignment)
    db.commit()
    
    return {"message": "Simulation removed from cohort successfully"}

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
