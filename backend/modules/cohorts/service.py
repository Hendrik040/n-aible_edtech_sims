"""
Cohort service - Business logic for cohort management
"""
import logging
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session

from .repository import CohortRepository
from .schemas import (
    CohortCreate, CohortUpdate, CohortResponse, CohortListResponse,
    CohortStudentCreate, CohortStudentUpdate, CohortStudentResponse,
    CohortSimulationCreate, CohortSimulationResponse
)

logger = logging.getLogger(__name__)

# Import models for validation
try:
    from common.db.models import (
        User, Scenario, UserProgress, StudentSimulationInstance
    )
    MODELS_AVAILABLE = True
except ImportError:
    MODELS_AVAILABLE = False
    User = None
    Scenario = None
    UserProgress = None
    StudentSimulationInstance = None


class CohortService:
    """Service for cohort business logic"""
    
    def __init__(self, db: Session):
        self.db = db
        self.repository = CohortRepository(db)
    
    def get_cohorts(
        self,
        user_id: int,
        user_role: str,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[CohortListResponse]:
        """Get cohorts with counts"""
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
        
        return result
    
    def get_cohort(self, unique_id: str, user_id: int, user_role: str) -> CohortResponse:
        """Get a specific cohort with students and simulations"""
        cohort = self.repository.get_cohort_by_unique_id(unique_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        # Check permissions
        if cohort.created_by != user_id and user_role != "admin":
            raise PermissionError("Not authorized to view this cohort")
        
        # Get students
        students_data = self.repository.get_cohort_students(cohort.id)
        students = []
        for cohort_student, user in students_data:
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
        simulations_data = self.repository.get_cohort_simulations(cohort.id)
        simulations = []
        for cohort_simulation in simulations_data:
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
        if cohort.created_by != user_id and user_role != "admin":
            raise PermissionError("Not authorized to update this cohort")
        
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
        if cohort.created_by != user_id and user_role != "admin":
            raise PermissionError("Not authorized to delete this cohort")
        
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
    
    def add_student_to_cohort(
        self, cohort_id: int, student_data: CohortStudentCreate, user_id: int, user_role: str
    ) -> CohortStudentResponse:
        """Add a student to a cohort"""
        cohort = self.repository.get_cohort_by_id(cohort_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        if cohort.created_by != user_id and user_role != "admin":
            raise PermissionError("Not authorized to manage this cohort")
        
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
        
        return CohortStudentResponse(
            id=cohort_student.id,
            student_id=cohort_student.student_id,
            student_name=student.full_name if student else f"Student {student_data.student_id}",
            student_email=student.email if student else "",
            status=cohort_student.status,
            enrollment_date=cohort_student.enrollment_date,
            approved_at=cohort_student.approved_at
        )
    
    def update_student_enrollment(
        self, unique_id: str, student_id: int, student_data: CohortStudentUpdate,
        user_id: int, user_role: str
    ) -> CohortStudentResponse:
        """Update a student's enrollment status"""
        cohort = self.repository.get_cohort_by_unique_id(unique_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        if cohort.created_by != user_id and user_role != "admin":
            raise PermissionError("Not authorized to manage this cohort")
        
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
        
        # Update enrollment
        approved_by = user_id if student_data.status == "approved" else None
        cohort_student = self.repository.update_student_enrollment(
            cohort_student, student_data.status, approved_by
        )
        
        return CohortStudentResponse(
            id=cohort_student.id,
            student_id=cohort_student.student_id,
            student_name=student.full_name if student else f"Student {student_id}",
            student_email=student.email if student else "",
            status=cohort_student.status,
            enrollment_date=cohort_student.enrollment_date,
            approved_at=cohort_student.approved_at
        )
    
    def remove_student_from_cohort(
        self, unique_id: str, student_id: int, user_id: int, user_role: str
    ) -> dict:
        """Remove a student from a cohort"""
        cohort = self.repository.get_cohort_by_unique_id(unique_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        if cohort.created_by != user_id and user_role != "admin":
            raise PermissionError("Not authorized to manage this cohort")
        
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
        
        if cohort.created_by != user_id and user_role != "admin":
            raise PermissionError("Not authorized to manage this cohort")
        
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
            simulations.append(CohortSimulationResponse(
                id=cohort_simulation.id,
                simulation_id=cohort_simulation.simulation_id,
                assigned_by=cohort_simulation.assigned_by,
                assigned_at=cohort_simulation.assigned_at,
                due_date=cohort_simulation.due_date,
                is_required=cohort_simulation.is_required
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
        
        if cohort.created_by != user_id and user_role != "admin":
            raise PermissionError("Not authorized to manage this cohort")
        
        # Check if scenario exists and is not deleted
        scenario = None
        if MODELS_AVAILABLE and Scenario:
            scenario = self.db.query(Scenario).filter(
                Scenario.id == simulation_data.simulation_id,
                Scenario.deleted_at.is_(None)
            ).first()
            if not scenario:
                raise ValueError("Scenario not found or has been deleted")
            
            if scenario.is_draft:
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
                if MODELS_AVAILABLE and UserProgress:
                    user_progress = UserProgress(
                        user_id=student.student_id,
                        scenario_id=simulation_data.simulation_id,
                        simulation_status="not_started"
                    )
                    self.db.add(user_progress)
                    self.db.flush()
                    
                    if StudentSimulationInstance:
                        student_instance = StudentSimulationInstance(
                            cohort_assignment_id=cohort_simulation.id,
                            student_id=student.student_id,
                            user_progress_id=user_progress.id
                        )
                        self.db.add(student_instance)
                
                # Create notification if service is available
                if notification_service and MODELS_AVAILABLE and Scenario:
                    try:
                        notification_service.create_simulation_assignment_notification(
                            self.db,
                            student.student_id,
                            cohort_simulation,
                            scenario,
                            cohort
                        )
                    except Exception as e:
                        logger.warning(f"Failed to create notification: {e}")
            
            # Step 5: Commit everything at once
            self.db.commit()
            logger.info(f"Assigned simulation {simulation_data.simulation_id} to cohort {cohort_id} with {len(students)} student instances")
            
            # Step 6: Return success response
            return CohortSimulationResponse(
                id=cohort_simulation.id,
                simulation_id=cohort_simulation.simulation_id,
                assigned_by=cohort_simulation.assigned_by,
                assigned_at=cohort_simulation.assigned_at,
                due_date=cohort_simulation.due_date,
                is_required=cohort_simulation.is_required
            )
            
        except Exception as e:
            logger.error(f"Failed to assign simulation to cohort: {str(e)}", exc_info=True)
            self.db.rollback()
            raise
    
    def remove_simulation_from_cohort(
        self, cohort_id: int, simulation_assignment_id: int, user_id: int, user_role: str
    ) -> dict:
        """Remove a simulation assignment from a cohort"""
        cohort = self.repository.get_cohort_by_id(cohort_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        if cohort.created_by != user_id and user_role != "admin":
            raise PermissionError("Not authorized to manage this cohort")
        
        result = self.repository.remove_simulation_from_cohort(cohort_id, simulation_assignment_id)
        logger.info(f"Successfully removed simulation assignment {simulation_assignment_id} from cohort {cohort_id}")
        return {"message": "Simulation removed from cohort successfully"}
    
    def refresh_assigned_simulations(self, professor_id: int) -> dict:
        """Refresh assigned simulations for a professor's cohorts"""
        return self.repository.refresh_assigned_simulations(professor_id)
    
    def get_student_cohorts(self, student_id: int) -> List[dict]:
        """Get cohorts that a student is enrolled in"""
        cohorts_data = self.repository.get_student_cohorts(student_id)
        
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
                "created_at": cohort.created_at,
                "enrollment_date": cohort_student.enrollment_date,
                "status": cohort_student.status,
                "professor": {
                    "id": professor.id if professor else None,
                    "name": professor.full_name if professor else "Unknown",
                    "email": professor.email if professor else "Unknown"
                },
                "student_count": student_count,
                "simulation_count": simulation_count
            })
        
        return cohorts
    
    def get_student_cohort_simulations(
        self, cohort_unique_id: str, student_id: int
    ) -> List[dict]:
        """Get simulations assigned to a cohort that a student is enrolled in"""
        cohort = self.repository.get_cohort_by_unique_id(cohort_unique_id)
        if not cohort:
            raise ValueError("Cohort not found")
        
        # Verify enrollment
        enrollment = self.repository.get_student_enrollment(cohort.id, student_id)
        if not enrollment or enrollment.status != "approved":
            raise PermissionError("Not enrolled in this cohort")
        
        simulations_data = self.repository.get_student_cohort_simulations(cohort.id, student_id)
        simulations = []
        for cohort_simulation, scenario in simulations_data:
            simulations.append({
                "id": cohort_simulation.id,
                "simulation_id": scenario.id,
                "title": scenario.title,
                "description": scenario.description,
                "assigned_at": cohort_simulation.assigned_at,
                "due_date": cohort_simulation.due_date,
                "is_required": cohort_simulation.is_required,
                "assigned_by": cohort_simulation.assigned_by
            })
        
        return simulations

