"""
Cohort service - Business logic for cohort management
"""
import logging
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import os

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .repository import CohortRepository
from .schemas import (
    CohortCreate, CohortUpdate, CohortResponse, CohortListResponse,
    CohortStudentCreate, CohortStudentUpdate, CohortStudentResponse,
    CohortSimulationCreate, CohortSimulationResponse, SimulationDetails,
    InviteLinkCreate, InviteLinkResponse, InviteLinksListResponse, ClearExpiredResponse
)

# Import models for validation
try:
    from common.db.models import (
        User, Simulation, UserProgress, StudentSimulationInstance
    )
    MODELS_AVAILABLE = True
except ImportError:
    MODELS_AVAILABLE = False
    User = None
    Simulation = None
    UserProgress = None
    StudentSimulationInstance = None

logger = logging.getLogger(__name__)


def generate_instance_id() -> str:
    """Generate a short, user-friendly instance ID like SI-MAN8P1QS"""
    chars = string.ascii_uppercase + string.digits
    random_part = ''.join(secrets.choice(chars) for _ in range(8))
    return f"SI-{random_part}"


class CohortService:
    """Service for cohort business logic"""
    
    def __init__(self, db: Session):
        self.db = db
        self.repository = CohortRepository(db)
    
    # --- Helper Methods ---
    
    def _check_cohort_permission(self, cohort, user_id: int, user_role: str, action: str = "access") -> None:
        """Check if user has permission to access/modify a cohort"""
        if cohort.created_by != user_id and user_role != "admin":
            raise PermissionError(f"Not authorized to {action} this cohort")
    
    def _build_simulation_details(self, sim) -> Optional[SimulationDetails]:
        """Build SimulationDetails from a simulation model"""
        if not sim or not hasattr(sim, 'id'):
            return None
        return SimulationDetails(
            id=sim.id,
            title=sim.title,
            description=sim.description,
            is_draft=sim.is_draft if hasattr(sim, 'is_draft') else False,
            status=sim.status if hasattr(sim, 'status') else None
        )
    
    def _build_cohort_student_response(self, cohort_student, user=None, student_id: Optional[int] = None) -> CohortStudentResponse:
        """Build CohortStudentResponse from cohort_student and user models"""
        return CohortStudentResponse(
            id=cohort_student.id,
            student_id=cohort_student.student_id,
            student_name=user.full_name if user else f"Student {student_id or cohort_student.student_id}",
            student_email=user.email if user else "",
            status=cohort_student.status,
            enrollment_date=cohort_student.enrollment_date,
            approved_at=cohort_student.approved_at
        )
    
    def _create_student_instance_with_retry(
        self, 
        user_progress, 
        cohort_simulation_id: int, 
        student_id: int,
        max_retries: int = 5
    ) -> bool:
        """Create a StudentSimulationInstance with retry logic for unique_id collisions.
        
        Returns True if instance was created, False otherwise.
        Raises ValueError if all retries are exhausted.
        """
        if not StudentSimulationInstance:
            return False
        
        retry_count = 0
        instance_created = False
        
        while retry_count < max_retries and not instance_created:
            try:
                student_instance = StudentSimulationInstance(
                    unique_id=generate_instance_id(),
                    cohort_assignment_id=cohort_simulation_id,
                    student_id=student_id,
                    user_progress_id=user_progress.id
                )
                self.db.add(student_instance)
                self.db.flush()  # Flush to check for unique constraint violation
                instance_created = True
            except IntegrityError as e:
                # Check if it's a unique constraint violation on unique_id
                if 'unique_id' in str(e.orig) or 'unique constraint' in str(e.orig).lower():
                    retry_count += 1
                    self.db.rollback()  # Rollback only the failed instance creation
                    # Re-flush user_progress since we rolled back
                    self.db.add(user_progress)
                    self.db.flush()
                    if retry_count >= max_retries:
                        logger.error(
                            f"Failed to create StudentSimulationInstance after {max_retries} "
                            f"retries due to unique_id collisions for student {student_id}, "
                            f"cohort_simulation {cohort_simulation_id}"
                        )
                        raise ValueError(
                            f"Failed to generate unique instance ID after {max_retries} attempts"
                        ) from e
                else:
                    # Not a unique constraint violation, re-raise
                    raise
        
        return instance_created
    
    def get_cohorts(
        self,
        user_id: int,
        user_role: str,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[CohortListResponse]:
        """Get cohorts with counts - cached for 120 seconds"""
        from common.services.cache_service import redis_manager
        
        # Build cache key including all filter parameters
        cache_key = f"professor_cohorts:{user_id}:{user_role}:{skip}:{limit}:{search or 'none'}:{status or 'none'}"
        
        # Check Redis cache first
        cached_result = redis_manager.get(cache_key)
        
        if cached_result is not None:
            logger.debug(f"Returning cached cohorts for user {user_id}")
            # Convert cached dicts back to Pydantic models
            return [CohortListResponse(**item) for item in cached_result]
        
        # Cache miss - query database
        cohorts_with_counts = self.repository.get_cohorts_with_counts(
            user_id, user_role, skip, limit, search, status
        )
        
        result = []
        for cohort_row in cohorts_with_counts:
            cohort = cohort_row[0]
            student_count = cohort_row[1]
            simulation_count = cohort_row[2]
            
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
        
        # Cache result for 120 seconds (2 minutes)
        # Convert Pydantic models to dicts for JSON serialization
        # Use mode='json' to ensure datetime objects are serialized as ISO strings
        cache_data = [item.model_dump(mode='json') for item in result]
        redis_manager.set(cache_key, cache_data, ttl=120)
        
        return result
    
    def get_cohort(self, unique_id: str, user_id: int, user_role: str) -> CohortResponse:
        """Get a specific cohort with students and simulations"""
        cohort = self.repository.get_cohort_by_unique_id(unique_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        # Check permissions
        self._check_cohort_permission(cohort, user_id, user_role, "view")
        
        # Get students
        students_data = self.repository.get_cohort_students(cohort.id)
        students = []
        for cohort_student, user in students_data:
            students.append(self._build_cohort_student_response(cohort_student, user))
        
        # Get simulations
        simulations_data = self.repository.get_cohort_simulations(cohort.id)
        simulations = []
        for cohort_simulation in simulations_data:
            # Build simulation details if available
            simulation_details = None
            if hasattr(cohort_simulation, 'simulation') and cohort_simulation.simulation:
                simulation_details = self._build_simulation_details(cohort_simulation.simulation)
            
            simulations.append(CohortSimulationResponse(
                id=cohort_simulation.id,
                simulation_id=cohort_simulation.simulation_id,
                assigned_by=cohort_simulation.assigned_by,
                assigned_at=cohort_simulation.assigned_at,
                due_date=cohort_simulation.due_date,
                is_required=cohort_simulation.is_required,
                simulation=simulation_details
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
    
    def create_cohort(
        self, cohort_data: CohortCreate, created_by: int
    ) -> CohortResponse:
        """Create a new cohort"""
        # Validate max_students
        if cohort_data.max_students is not None and cohort_data.max_students <= 0:
            raise ValueError("Max students must be positive")
        
        cohort = self.repository.create_cohort(
            title=cohort_data.title,
            created_by=created_by,
            description=cohort_data.description,
            course_code=cohort_data.course_code,
            semester=cohort_data.semester,
            year=cohort_data.year,
            max_students=cohort_data.max_students,
            auto_approve=cohort_data.auto_approve,
            allow_self_enrollment=cohort_data.allow_self_enrollment
        )
        
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
    
    def update_cohort(
        self, unique_id: str, cohort_data: CohortUpdate, user_id: int, user_role: str
    ) -> CohortResponse:
        """Update a cohort"""
        cohort = self.repository.get_cohort_by_unique_id(unique_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        # Check permissions
        self._check_cohort_permission(cohort, user_id, user_role, "update")
        
        update_data = cohort_data.model_dump(exclude_unset=True)
        cohort = self.repository.update_cohort(cohort, update_data)
        
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
    
    def delete_cohort(
        self, unique_id: str, user_id: int, user_role: str
    ) -> dict:
        """Delete a cohort"""
        cohort = self.repository.get_cohort_by_unique_id(unique_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        # Check permissions
        self._check_cohort_permission(cohort, user_id, user_role, "delete")
        
        deletion_info = self.repository.delete_cohort(cohort)
        logger.info(f"Cohort '{cohort.title}' (ID: {cohort.unique_id}) deleted by user {user_id}")
        return deletion_info
    
    def get_cohort_students(
        self, unique_id: str, user_id: int, user_role: str
    ) -> List[CohortStudentResponse]:
        """Get all students in a cohort"""
        cohort = self.repository.get_cohort_by_unique_id(unique_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        if cohort.created_by != user_id and user_role != "admin":
            raise PermissionError("Not authorized to view this cohort")
        
        students_data = self.repository.get_cohort_students(cohort.id)
        students = []
        for cohort_student, user in students_data:
            students.append(self._build_cohort_student_response(cohort_student, user))
        
        return students
    
    def add_student_to_cohort(
        self, cohort_id: int, student_data: CohortStudentCreate, user_id: int, user_role: str
    ) -> CohortStudentResponse:
        """Add a student to a cohort"""
        cohort = self.repository.get_cohort_by_id(cohort_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        self._check_cohort_permission(cohort, user_id, user_role, "manage")
        
        # Check if student exists
        if MODELS_AVAILABLE and User:
            student = self.db.query(User).filter(User.id == student_data.student_id).first()
            if not student:
                raise ValueError("Student not found")
        else:
            student = None
        
        # Check if already enrolled
        existing = self.repository.get_student_enrollment(cohort_id, student_data.student_id)
        if existing:
            raise ValueError("Student is already enrolled in this cohort")
        
        cohort_student = self.repository.add_student_to_cohort(
            cohort_id, student_data.student_id, student_data.status
        )
        
        return self._build_cohort_student_response(cohort_student, student, student_data.student_id)
    
    def update_student_enrollment(
        self, unique_id: str, student_id: int, student_data: CohortStudentUpdate,
        user_id: int, user_role: str
    ) -> CohortStudentResponse:
        """Update a student's enrollment status"""
        cohort = self.repository.get_cohort_by_unique_id(unique_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        self._check_cohort_permission(cohort, user_id, user_role, "manage")
        
        cohort_student = self.repository.get_student_enrollment(cohort.id, student_id)
        if not cohort_student:
            raise ValueError("Student not enrolled in this cohort")
        
        # Get student user details
        if MODELS_AVAILABLE and User:
            student = self.db.query(User).filter(User.id == student_id).first()
            if not student:
                raise ValueError("Student not found")
        else:
            student = None
        
        # Track if this is a new approval (to create simulation instances)
        was_not_approved = cohort_student.status != "approved"
        is_becoming_approved = student_data.status == "approved"
        
        try:
            # Update enrollment
            approved_by = user_id if student_data.status == "approved" else None
            cohort_student = self.repository.update_student_enrollment(
                cohort_student, student_data.status, approved_by
            )
            
            # If student is being approved, create simulation instances for existing cohort simulations
            if was_not_approved and is_becoming_approved:
                self._create_simulation_instances_for_student(cohort.id, student_id)
            
            # Commit all changes in a single transaction
            self.db.commit()
            
            return self._build_cohort_student_response(cohort_student, student, student_id)
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating student enrollment: {str(e)}", exc_info=True)
            raise
    
    def _create_simulation_instances_for_student(self, cohort_id: int, student_id: int) -> int:
        """Create simulation instances for a student for all existing cohort simulations.
        
        This is called when a student is approved to ensure they have access to all
        simulations that were assigned before they joined or were approved.
        
        Returns the number of instances created.
        """
        try:
            from common.db.models import CohortSimulation
        except ImportError:
            return 0
        
        # Get all simulations assigned to this cohort
        cohort_simulations = self.db.query(CohortSimulation).filter(
            CohortSimulation.cohort_id == cohort_id
        ).all()
        
        instances_created = 0
        for cohort_simulation in cohort_simulations:
            # Check if instance already exists
            if StudentSimulationInstance:
                existing = self.db.query(StudentSimulationInstance).filter(
                    StudentSimulationInstance.cohort_assignment_id == cohort_simulation.id,
                    StudentSimulationInstance.student_id == student_id
                ).first()
                
                if existing:
                    continue
            
            # Create StudentSimulationInstance WITHOUT UserProgress
            # UserProgress will be created when student actually starts the simulation
            # Creating it here without orchestrator_data causes "Simulation not properly initialized" errors
            if StudentSimulationInstance:
                # Check if instance already exists
                existing = self.db.query(StudentSimulationInstance).filter(
                    StudentSimulationInstance.cohort_assignment_id == cohort_simulation.id,
                    StudentSimulationInstance.student_id == student_id
                ).first()
                
                if not existing:
                    import secrets
                    unique_id = f"SI-{secrets.token_urlsafe(8).upper()}"
                    instance = StudentSimulationInstance(
                        unique_id=unique_id,
                        student_id=student_id,
                        cohort_assignment_id=cohort_simulation.id,
                        status="not_started",
                        user_progress_id=None  # Will be set when student starts simulation
                    )
                    self.db.add(instance)
                    self.db.flush()
                    instances_created += 1
        
        # Note: No commit here - let the caller control the transaction
        if instances_created > 0:
            logger.info(f"Created {instances_created} simulation instances for student {student_id} in cohort {cohort_id}")
        
        return instances_created
    
    def remove_student_from_cohort(
        self, unique_id: str, student_id: int, user_id: int, user_role: str
    ) -> dict:
        """Remove a student from a cohort"""
        cohort = self.repository.get_cohort_by_unique_id(unique_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        self._check_cohort_permission(cohort, user_id, user_role, "manage")
        
        deleted_instances = self.repository.remove_student_from_cohort(cohort.id, student_id)
        
        if MODELS_AVAILABLE and User:
            student = self.db.query(User).filter(User.id == student_id).first()
            student_name = student.full_name if student else f"Student {student_id}"
        else:
            student_name = f"Student {student_id}"
        
        logger.info(f"Successfully removed {student_name} from cohort {cohort.title}")
        return {"message": "Student removed from cohort successfully"}
    
    def remove_multiple_students_from_cohort(
        self, unique_id: str, student_ids: List[int], user_id: int, user_role: str
    ) -> dict:
        """Remove multiple students from a cohort"""
        cohort = self.repository.get_cohort_by_unique_id(unique_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        self._check_cohort_permission(cohort, user_id, user_role, "manage")
        
        if not student_ids:
            raise ValueError("No student IDs provided")
        
        result = self.repository.remove_multiple_students_from_cohort(cohort.id, student_ids)
        
        logger.info(f"Successfully removed {result['removed_count']} students from cohort {cohort.title}")
        return {
            "message": f"Successfully removed {result['removed_count']} student(s) from cohort",
            "removed_count": result['removed_count']
        }
    
    def get_cohort_simulations(
        self, unique_id: str, user_id: int, user_role: str
    ) -> List[CohortSimulationResponse]:
        """Get all simulations assigned to a cohort"""
        cohort = self.repository.get_cohort_by_unique_id(unique_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        if cohort.created_by != user_id and user_role != "admin":
            raise PermissionError("Not authorized to view this cohort")
        
        simulations_data = self.repository.get_cohort_simulations(cohort.id)
        simulations = []
        for cohort_simulation in simulations_data:
            # Build simulation details if available
            simulation_details = None
            if hasattr(cohort_simulation, 'simulation') and cohort_simulation.simulation:
                simulation_details = self._build_simulation_details(cohort_simulation.simulation)
            
            simulations.append(CohortSimulationResponse(
                id=cohort_simulation.id,
                simulation_id=cohort_simulation.simulation_id,
                assigned_by=cohort_simulation.assigned_by,
                assigned_at=cohort_simulation.assigned_at,
                due_date=cohort_simulation.due_date,
                is_required=cohort_simulation.is_required,
                simulation=simulation_details
            ))
        
        return simulations
    
    def assign_simulation_to_cohort(
        self, cohort_id: int, simulation_data: CohortSimulationCreate,
        user_id: int, user_role: str
    ) -> CohortSimulationResponse:
        """Assign a simulation to a cohort.
        
        Creates the cohort simulation assignment and student instances in a single
        transaction. If any part fails, the entire operation is rolled back.
        """
        cohort = self.repository.get_cohort_by_id(cohort_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        self._check_cohort_permission(cohort, user_id, user_role, "manage")
        
        # Check if simulation exists and is not deleted
        simulation = None
        if MODELS_AVAILABLE and Simulation:
            simulation = self.db.query(Simulation).filter(
                Simulation.id == simulation_data.simulation_id,
                Simulation.deleted_at.is_(None)
            ).first()
            if not simulation:
                raise ValueError("Simulation not found or has been deleted")
            
            if simulation.is_draft:
                raise ValueError("Cannot assign draft simulations. Please publish the simulation first.")
        
        # Single transaction for all operations
        try:
            # Step 1: Create cohort simulation (no longer commits)
            cohort_simulation = self.repository.assign_simulation_to_cohort(
                cohort_id=cohort_id,
                simulation_id=simulation_data.simulation_id,
                assigned_by=user_id,
                due_date=simulation_data.due_date,
                is_required=simulation_data.is_required
            )
            
            # Step 2: Import notification service if available
            try:
                from modules.notifications.service import notification_service
            except ImportError:
                notification_service = None
            
            # Step 3: Get all approved students in the cohort
            try:
                from common.db.models import CohortStudent
            except ImportError:
                raise ValueError("Cohort models not available")
            
            students = self.db.query(CohortStudent).filter(
                CohortStudent.cohort_id == cohort_id,
                CohortStudent.status == "approved"
            ).all()
            
            # Step 4: Create student simulation instances
            for student in students:
                # Check if instance already exists for this student and assignment
                if StudentSimulationInstance:
                    existing_instance = self.db.query(StudentSimulationInstance).filter(
                        StudentSimulationInstance.cohort_assignment_id == cohort_simulation.id,
                        StudentSimulationInstance.student_id == student.student_id
                    ).first()
                    
                    if existing_instance:
                        # Reset existing instance when reassigning
                        logger.info(f"Resetting existing instance {existing_instance.unique_id} for student {student.student_id} when reassigning simulation")
                        
                        # Delete existing user_progress if linked
                        if existing_instance.user_progress_id and UserProgress:
                            try:
                                from modules.simulation.repository import SimulationRepository
                                repo = SimulationRepository(self.db)
                                repo.delete_user_progress_and_related(existing_instance.user_progress_id)
                            except Exception as e:
                                logger.warning(f"Error deleting user_progress for instance {existing_instance.unique_id}: {e}", exc_info=True)
                        
                        # Reset instance fields
                        # Nullable fields can be set to None
                        existing_instance.user_progress_id = None
                        existing_instance.started_at = None
                        existing_instance.completed_at = None
                        existing_instance.submitted_at = None
                        existing_instance.grade = None
                        existing_instance.ai_grade = None
                        existing_instance.feedback = None
                        existing_instance.ai_feedback = None
                        existing_instance.ai_graded_at = None
                        existing_instance.graded_by = None
                        existing_instance.graded_at = None
                        
                        # Non-nullable fields must use safe defaults
                        existing_instance.status = "not_started"
                        existing_instance.completion_percentage = 0.0
                        existing_instance.total_time_spent = 0
                        existing_instance.grade_status = "not_graded"
                        existing_instance.attempts_count = 0
                        existing_instance.hints_used = 0
                        existing_instance.is_overdue = False
                        existing_instance.days_late = 0
                        
                        # Only clear instance_data if the attribute exists (column may not be in all databases)
                        if hasattr(existing_instance, "instance_data"):
                            existing_instance.instance_data = None
                        
                        # Don't flush here - will be committed with the transaction
                        
                        continue  # Skip creating new instance
                
                # Create new instance if it doesn't exist
                # NOTE: Do NOT create UserProgress here - it will be created when student starts the simulation
                # Creating it here without orchestrator_data causes issues when resuming
                if StudentSimulationInstance:
                    # Create instance without user_progress_id - it will be linked when simulation starts
                    unique_id = generate_instance_id()
                    instance = StudentSimulationInstance(
                        unique_id=unique_id,
                        student_id=student.student_id,
                        cohort_assignment_id=cohort_simulation.id,
                        status="not_started",
                        user_progress_id=None  # Will be set when student starts simulation
                    )
                    self.db.add(instance)
                    self.db.flush()
                
                # Create notification if service is available
                if notification_service and MODELS_AVAILABLE and Simulation:
                    try:
                        notification_service.create_simulation_assignment_notification(
                            self.db,
                            student.student_id,
                            cohort_simulation,
                            simulation,
                            cohort
                        )
                    except Exception as e:
                        logger.warning(f"Failed to create notification: {e}")
            
            # Step 5: Commit everything at once
            self.db.commit()
            logger.info(f"Assigned simulation {simulation_data.simulation_id} to cohort {cohort_id} with {len(students)} student instances")
            
            # Step 6: Build simulation details for response
            simulation_details = self._build_simulation_details(simulation)
            
            # Step 7: Return success response
            return CohortSimulationResponse(
                id=cohort_simulation.id,
                simulation_id=cohort_simulation.simulation_id,
                assigned_by=cohort_simulation.assigned_by,
                assigned_at=cohort_simulation.assigned_at,
                due_date=cohort_simulation.due_date,
                is_required=cohort_simulation.is_required,
                simulation=simulation_details
            )
            
        except Exception as e:
            logger.error(f"Failed to assign simulation to cohort: {str(e)}", exc_info=True)
            self.db.rollback()
            raise
    
    def remove_simulation_from_cohort(
        self, cohort_id: int, simulation_assignment_id: int, user_id: int, user_role: str
    ) -> dict:
        """Remove a simulation assignment from a cohort"""
        try:
            cohort = self.repository.get_cohort_by_id(cohort_id)
            if not cohort:
                raise ValueError("Cohort not found")
            
            if cohort.created_by != user_id and user_role != "admin":
                raise PermissionError("Not authorized to manage this cohort")
            
            result = self.repository.remove_simulation_from_cohort(cohort_id, simulation_assignment_id)
            logger.info(f"Successfully removed simulation assignment {simulation_assignment_id} from cohort {cohort_id}. Deleted {result.get('deleted_instances', 0)} student instances")
            return {
                "message": "Simulation removed from cohort successfully",
                "deleted_instances": result.get("deleted_instances", 0)
            }
        except Exception as e:
            logger.error(f"Error removing simulation from cohort: {str(e)}", exc_info=True)
            raise
    
    def refresh_assigned_simulations(self, professor_id: int) -> dict:
        """Refresh assigned simulations for a professor's cohorts"""
        return self.repository.refresh_assigned_simulations(professor_id)
    
    def get_student_cohorts(self, student_id: int) -> List[dict]:
        """Get cohorts that a student is enrolled in"""
        import time
        import logging
        from common.services.cache_service import redis_manager
        
        logger = logging.getLogger(__name__)
        
        # Check Redis cache first (short TTL for dashboard data freshness)
        cache_key = f"student_cohorts:{student_id}"
        cached_result = redis_manager.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Returning cached student cohorts for student {student_id}")
            return cached_result
        
        query_start = time.time()
        try:
            cohorts_data = self.repository.get_student_cohorts(student_id)
            query_elapsed = time.time() - query_start
            if query_elapsed > 2.0:  # Log slow queries
                logger.warning(f"get_student_cohorts repository query took {query_elapsed:.2f}s for student {student_id}")
        except Exception as e:
            query_elapsed = time.time() - query_start
            logger.error(
                f"Error in get_student_cohorts repository query for student {student_id} "
                f"(took {query_elapsed:.2f}s): {e!r}",
                exc_info=True
            )
            raise
        
        cohorts = []
        for row in cohorts_data:
            cohort = row[0]
            cohort_student = row[1]
            student_count = row[2]
            simulation_count = row[3]
            
            professor = cohort.creator if hasattr(cohort, 'creator') else None
            
            cohorts.append({
                "id": cohort.id,
                "unique_id": cohort.unique_id,
                "title": cohort.title,
                "description": cohort.description,
                "course_code": cohort.course_code,
                "semester": cohort.semester,
                "year": cohort.year,
                "max_students": cohort.max_students,
                "is_active": cohort.is_active,
                "created_at": cohort.created_at.isoformat() if cohort.created_at else None,
                "enrollment_date": cohort_student.enrollment_date.isoformat() if cohort_student.enrollment_date else None,
                "status": cohort_student.status,
                "professor": {
                    "id": professor.id if professor else None,
                    "name": professor.full_name if professor else "Unknown",
                    "email": professor.email if professor else "Unknown"
                },
                "student_count": student_count,
                "simulation_count": simulation_count
            })
        
        # Cache result for 30 seconds (short TTL for dashboard freshness)
        redis_manager.set(cache_key, cohorts, ttl=30)
        
        return cohorts
    
    def get_student_cohort_simulations(
        self, cohort_unique_id: str, student_id: int
    ) -> List[dict]:
        """Get simulations assigned to a cohort that a student is enrolled in - cached for 120 seconds"""
        from common.services.cache_service import redis_manager
        
        # Check Redis cache first
        cache_key = f"student_cohort_simulations:{cohort_unique_id}:{student_id}"
        cached_result = redis_manager.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Returning cached cohort simulations for cohort {cohort_unique_id}, student {student_id}")
            return cached_result
        
        cohort = self.repository.get_cohort_by_unique_id(cohort_unique_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        # Verify enrollment
        enrollment = self.repository.get_student_enrollment(cohort.id, student_id)
        if not enrollment or enrollment.status != "approved":
            raise PermissionError("Not enrolled in this cohort")
        
        simulations_data = self.repository.get_student_cohort_simulations(cohort.id, student_id)
        simulations = []
        for cohort_simulation, simulation in simulations_data:
            simulations.append({
                "id": cohort_simulation.id,
                "simulation_id": simulation.id,
                "title": simulation.title,
                "description": simulation.description,
                "assigned_at": cohort_simulation.assigned_at.isoformat() if cohort_simulation.assigned_at else None,
                "due_date": cohort_simulation.due_date.isoformat() if cohort_simulation.due_date else None,
                "is_required": cohort_simulation.is_required,
                "assigned_by": cohort_simulation.assigned_by
            })
        
        # Cache result for 120 seconds (2 minutes)
        redis_manager.set(cache_key, simulations, ttl=120)
        
        return simulations
    
    # --- INVITE LINK METHODS ---
    
    def _build_invite_url(self, token: str) -> str:
        """Build the full invite URL"""
        # Get frontend URL from environment variable or config
        frontend_url = os.getenv('FRONTEND_BASE_URL')
        if not frontend_url:
            try:
                from common.config import get_settings
                settings = get_settings()
                frontend_url = getattr(settings, 'frontend_url', None) or "http://localhost:3000"
            except Exception:
                frontend_url = "http://localhost:3000"
        
        # Remove trailing slash if present to avoid double slashes
        frontend_url = frontend_url.rstrip('/')
        return f"{frontend_url}/invite/{token}"
    
    def _invite_to_response(self, invite) -> InviteLinkResponse:
        """Convert an invite model to response schema"""
        now = datetime.now(timezone.utc)
        expires_at = invite.expires_at
        
        # Ensure timezone-aware comparison
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        
        is_expired = expires_at < now
        
        # Calculate if used up
        if invite.invite_type == "SINGLE_USE":
            is_used_up = invite.uses_count >= 1
            uses_left = 0 if is_used_up else 1
        else:
            if invite.max_uses is None:
                is_used_up = False
                uses_left = None  # Unlimited
            else:
                is_used_up = invite.uses_count >= invite.max_uses
                uses_left = max(0, invite.max_uses - invite.uses_count)
        
        # Determine status
        if is_expired:
            status = "expired"
        elif is_used_up:
            status = "used"
        else:
            status = "active"
        
        return InviteLinkResponse(
            invite_id=invite.id,
            invite_url=self._build_invite_url(invite.token),
            token=invite.token,
            invite_type=invite.invite_type,
            max_uses=invite.max_uses,
            uses_count=invite.uses_count,
            uses_left=uses_left,
            expires_at=invite.expires_at,
            created_at=invite.created_at,
            is_expired=is_expired,
            is_used_up=is_used_up,
            status=status
        )
    
    def get_invite_links(
        self, cohort_id: int, user_id: int, user_role: str
    ) -> InviteLinksListResponse:
        """Get all invite links for a cohort"""
        cohort = self.repository.get_cohort_by_id(cohort_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        self._check_cohort_permission(cohort, user_id, user_role, "view this cohort's invite links")
        
        invites = self.repository.get_cohort_invites(cohort_id)
        invite_responses = [self._invite_to_response(inv) for inv in invites]
        
        return InviteLinksListResponse(
            invites=invite_responses,
            total=len(invite_responses)
        )
    
    def create_invite_link(
        self, cohort_id: int, invite_data: InviteLinkCreate, user_id: int, user_role: str
    ) -> InviteLinkResponse:
        """Create a new invite link for a cohort"""
        cohort = self.repository.get_cohort_by_id(cohort_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        self._check_cohort_permission(cohort, user_id, user_role, "create invite links for this cohort")
        
        # Validate invite type
        invite_type = invite_data.type.upper()
        if invite_type not in ["SINGLE_USE", "MULTI_USE"]:
            raise ValueError("Invalid invite type. Must be SINGLE_USE or MULTI_USE")
        
        # Calculate expiration
        expires_at = datetime.now(timezone.utc) + timedelta(days=invite_data.expires_in_days)
        
        # Create the invite
        invite = self.repository.create_invite(
            cohort_id=cohort_id,
            created_by=user_id,
            invite_type=invite_type,
            expires_at=expires_at,
            max_uses=invite_data.max_uses if invite_type == "MULTI_USE" else None
        )
        
        logger.info(f"Created {invite_type} invite link for cohort {cohort_id} by user {user_id}")
        return self._invite_to_response(invite)
    
    def delete_invite_link(
        self, cohort_id: int, invite_id: int, user_id: int, user_role: str
    ) -> dict:
        """Delete a specific invite link"""
        cohort = self.repository.get_cohort_by_id(cohort_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        self._check_cohort_permission(cohort, user_id, user_role, "delete invite links for this cohort")
        
        invite = self.repository.get_invite_by_id(invite_id)
        if not invite or invite.cohort_id != cohort_id:
            raise ValueError("Invite link not found")
        
        self.repository.delete_invite(invite)
        logger.info(f"Deleted invite link {invite_id} for cohort {cohort_id} by user {user_id}")
        return {"message": "Invite link deleted successfully"}
    
    def clear_expired_invites(
        self, cohort_id: int, user_id: int, user_role: str
    ) -> ClearExpiredResponse:
        """Clear all expired and used invite links for a cohort"""
        cohort = self.repository.get_cohort_by_id(cohort_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        self._check_cohort_permission(cohort, user_id, user_role, "clear invite links for this cohort")
        
        deleted_count = self.repository.delete_expired_invites(cohort_id)
        logger.info(f"Cleared {deleted_count} expired invite links for cohort {cohort_id} by user {user_id}")
        
        return ClearExpiredResponse(
            deleted_count=deleted_count,
            message=f"Deleted {deleted_count} expired or used invite link(s)"
        )

