"""
Cohort repository - Database operations for cohorts
"""
import secrets
import string
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import and_, or_, desc, func
from sqlalchemy.sql.functions import coalesce

logger = logging.getLogger(__name__)

# Import models - handle case where they might not exist yet
try:
    from common.db.models import (
        Cohort, CohortStudent, CohortSimulation, User, Scenario, 
        UserProgress, StudentSimulationInstance, ScenarioScene, SceneProgress
    )
    MODELS_AVAILABLE = True
except ImportError:
    logger.warning("Cohort models not found. They need to be added to common/db/models.py")
    MODELS_AVAILABLE = False
    Cohort = None
    CohortStudent = None
    CohortSimulation = None
    User = None
    Scenario = None
    UserProgress = None
    StudentSimulationInstance = None
    ScenarioScene = None
    SceneProgress = None


def generate_cohort_id() -> str:
    """Generate a short, user-friendly cohort ID like CH-MAN8P1QS"""
    chars = string.ascii_uppercase + string.digits
    random_part = ''.join(secrets.choice(chars) for _ in range(8))
    return f"CH-{random_part}"


class CohortRepository:
    """Repository for cohort database operations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_cohorts_with_counts(
        self,
        user_id: int,
        user_role: str,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Tuple]:
        """Get cohorts with student and simulation counts"""
        if not MODELS_AVAILABLE:
            raise ImportError("Cohort models not available")
        
        query = self.db.query(Cohort)
        
        # Filter by creator (users can only see their own cohorts unless admin)
        if user_role != "admin":
            query = query.filter(Cohort.created_by == user_id)
        
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
        
        # Create subqueries for counts
        student_count_subquery = self.db.query(
            CohortStudent.cohort_id,
            func.count(CohortStudent.id).label('student_count')
        ).filter(
            CohortStudent.status == "approved"
        ).group_by(CohortStudent.cohort_id).subquery()
        
        simulation_count_subquery = self.db.query(
            CohortSimulation.cohort_id,
            func.count(CohortSimulation.id).label('simulation_count')
        ).join(
            Scenario, CohortSimulation.simulation_id == Scenario.id
        ).filter(
            Scenario.deleted_at.is_(None),
            Scenario.is_draft == False,
            Scenario.status == "active"
        ).group_by(CohortSimulation.cohort_id).subquery()
        
        # Main query with left joins
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
        
        return cohorts_with_counts
    
    def get_cohort_by_unique_id(self, unique_id: str) -> Optional[Cohort]:
        """Get a cohort by its unique_id"""
        if not MODELS_AVAILABLE:
            return None
        return self.db.query(Cohort).filter(Cohort.unique_id == unique_id).first()
    
    def get_cohort_by_id(self, cohort_id: int) -> Optional[Cohort]:
        """Get a cohort by its id"""
        if not MODELS_AVAILABLE:
            return None
        return self.db.query(Cohort).filter(Cohort.id == cohort_id).first()
    
    def create_cohort(
        self,
        title: str,
        created_by: int,
        description: Optional[str] = None,
        course_code: Optional[str] = None,
        semester: Optional[str] = None,
        year: Optional[int] = None,
        max_students: Optional[int] = None,
        auto_approve: bool = True,
        allow_self_enrollment: bool = False
    ) -> Cohort:
        """Create a new cohort"""
        if not MODELS_AVAILABLE:
            raise ImportError("Cohort models not available")
        
        unique_id = generate_cohort_id()
        cohort = Cohort(
            unique_id=unique_id,
            title=title,
            description=description,
            course_code=course_code,
            semester=semester,
            year=year,
            max_students=max_students,
            auto_approve=auto_approve,
            allow_self_enrollment=allow_self_enrollment,
            created_by=created_by
        )
        self.db.add(cohort)
        self.db.commit()
        self.db.refresh(cohort)
        return cohort
    
    def update_cohort(self, cohort: Cohort, update_data: dict) -> Cohort:
        """Update a cohort"""
        for field, value in update_data.items():
            setattr(cohort, field, value)
        self.db.commit()
        self.db.refresh(cohort)
        return cohort
    
    def delete_cohort(self, cohort: Cohort) -> dict:
        """Delete a cohort and return deletion info"""
        student_count = self.db.query(CohortStudent).filter(
            CohortStudent.cohort_id == cohort.id
        ).count()
        simulation_count = self.db.query(CohortSimulation).filter(
            CohortSimulation.cohort_id == cohort.id
        ).count()
        
        # Delete related records
        active_simulations = self.db.query(CohortSimulation).filter(
            CohortSimulation.cohort_id == cohort.id
        ).all()
        for simulation in active_simulations:
            self.db.delete(simulation)
        
        student_enrollments = self.db.query(CohortStudent).filter(
            CohortStudent.cohort_id == cohort.id
        ).all()
        for enrollment in student_enrollments:
            self.db.delete(enrollment)
        
        self.db.delete(cohort)
        self.db.commit()
        
        return {
            "deleted_students": student_count,
            "deleted_simulations": simulation_count
        }
    
    def get_cohort_students(self, cohort_id: int) -> List[Tuple]:
        """Get all students in a cohort with user details"""
        if not MODELS_AVAILABLE:
            return []
        return self.db.query(CohortStudent, User).join(
            User, CohortStudent.student_id == User.id
        ).filter(CohortStudent.cohort_id == cohort_id).all()
    
    def get_student_enrollment(
        self, cohort_id: int, student_id: int
    ) -> Optional[CohortStudent]:
        """Get a student's enrollment in a cohort"""
        if not MODELS_AVAILABLE:
            return None
        return self.db.query(CohortStudent).filter(
            CohortStudent.cohort_id == cohort_id,
            CohortStudent.student_id == student_id
        ).first()
    
    def add_student_to_cohort(
        self, cohort_id: int, student_id: int, status: str = "pending"
    ) -> CohortStudent:
        """Add a student to a cohort"""
        if not MODELS_AVAILABLE:
            raise ImportError("Cohort models not available")
        
        cohort_student = CohortStudent(
            cohort_id=cohort_id,
            student_id=student_id,
            status=status
        )
        self.db.add(cohort_student)
        self.db.commit()
        self.db.refresh(cohort_student)
        return cohort_student
    
    def update_student_enrollment(
        self, cohort_student: CohortStudent, status: str, approved_by: Optional[int] = None
    ) -> CohortStudent:
        """Update a student's enrollment status"""
        cohort_student.status = status
        if status == "approved" and approved_by:
            cohort_student.approved_at = datetime.utcnow()
            if hasattr(cohort_student, 'approved_by'):
                cohort_student.approved_by = approved_by
        self.db.commit()
        self.db.refresh(cohort_student)
        return cohort_student
    
    def remove_student_from_cohort(
        self, cohort_id: int, student_id: int
    ) -> int:
        """Remove a student from a cohort and return number of deleted instances"""
        if not MODELS_AVAILABLE:
            return 0
        
        enrollment = self.db.query(CohortStudent).filter(
            CohortStudent.cohort_id == cohort_id,
            CohortStudent.student_id == student_id
        ).first()
        
        if not enrollment:
            return 0
        
        # Delete student simulation instances
        deleted_instances = 0
        if StudentSimulationInstance:
            cohort_assignments = self.db.query(CohortSimulation).filter(
                CohortSimulation.cohort_id == cohort_id
            ).all()
            
            for assignment in cohort_assignments:
                instances = self.db.query(StudentSimulationInstance).filter(
                    StudentSimulationInstance.cohort_assignment_id == assignment.id,
                    StudentSimulationInstance.student_id == student_id
                ).all()
                for instance in instances:
                    self.db.delete(instance)
                    deleted_instances += 1
        
        self.db.delete(enrollment)
        self.db.commit()
        return deleted_instances
    
    def remove_multiple_students_from_cohort(
        self, cohort_id: int, student_ids: List[int]
    ) -> dict:
        """Remove multiple students from a cohort"""
        if not MODELS_AVAILABLE:
            return {"removed_count": 0, "deleted_instances": 0}
        
        enrollments = self.db.query(CohortStudent).filter(
            CohortStudent.cohort_id == cohort_id,
            CohortStudent.student_id.in_(student_ids)
        ).all()
        
        if not enrollments:
            return {"removed_count": 0, "deleted_instances": 0}
        
        enrolled_student_ids = [e.student_id for e in enrollments]
        deleted_instances = 0
        
        if StudentSimulationInstance:
            cohort_assignments = self.db.query(CohortSimulation).filter(
                CohortSimulation.cohort_id == cohort_id
            ).all()
            
            for assignment in cohort_assignments:
                instances = self.db.query(StudentSimulationInstance).filter(
                    StudentSimulationInstance.cohort_assignment_id == assignment.id,
                    StudentSimulationInstance.student_id.in_(enrolled_student_ids)
                ).all()
                for instance in instances:
                    self.db.delete(instance)
                    deleted_instances += 1
        
        for enrollment in enrollments:
            self.db.delete(enrollment)
        
        self.db.commit()
        return {
            "removed_count": len(enrollments),
            "deleted_instances": deleted_instances
        }
    
    def get_cohort_simulations(self, cohort_id: int) -> List[CohortSimulation]:
        """Get all simulations assigned to a cohort"""
        if not MODELS_AVAILABLE:
            return []
        
        return self.db.query(CohortSimulation).options(
            selectinload(CohortSimulation.simulation)
        ).join(
            Scenario, CohortSimulation.simulation_id == Scenario.id
        ).filter(
            CohortSimulation.cohort_id == cohort_id,
            Scenario.is_draft == False,
            Scenario.status == "active"
        ).all()
    
    def assign_simulation_to_cohort(
        self,
        cohort_id: int,
        simulation_id: int,
        assigned_by: int,
        due_date: Optional[datetime] = None,
        is_required: bool = True
    ) -> CohortSimulation:
        """Assign a simulation to a cohort"""
        if not MODELS_AVAILABLE:
            raise ImportError("Cohort models not available")
        
        cohort_simulation = CohortSimulation(
            cohort_id=cohort_id,
            simulation_id=simulation_id,
            assigned_by=assigned_by,
            due_date=due_date,
            is_required=is_required
        )
        self.db.add(cohort_simulation)
        self.db.commit()
        self.db.refresh(cohort_simulation)
        return cohort_simulation
    
    def remove_simulation_from_cohort(
        self, cohort_id: int, simulation_assignment_id: int
    ) -> dict:
        """Remove a simulation assignment from a cohort"""
        if not MODELS_AVAILABLE:
            return {"deleted_instances": 0}
        
        simulation_assignment = self.db.query(CohortSimulation).filter(
            CohortSimulation.id == simulation_assignment_id,
            CohortSimulation.cohort_id == cohort_id
        ).first()
        
        if not simulation_assignment:
            return {"deleted_instances": 0}
        
        deleted_instances = 0
        if StudentSimulationInstance:
            # Try to import GradeHistory if available
            try:
                from common.db.models import GradeHistory
            except ImportError:
                GradeHistory = None
            
            student_instances = self.db.query(StudentSimulationInstance).filter(
                StudentSimulationInstance.cohort_assignment_id == simulation_assignment_id
            ).all()
            
            # Delete grade_history records first
            if GradeHistory:
                instance_ids = [instance.id for instance in student_instances]
                if instance_ids:
                    grade_history_records = self.db.query(GradeHistory).filter(
                        GradeHistory.instance_id.in_(instance_ids)
                    ).all()
                    for record in grade_history_records:
                        self.db.delete(record)
            
            # Delete student instances
            for instance in student_instances:
                self.db.delete(instance)
                deleted_instances += 1
        
        self.db.delete(simulation_assignment)
        self.db.commit()
        return {"deleted_instances": deleted_instances}
    
    def get_student_cohorts(self, student_id: int) -> List[Tuple]:
        """Get cohorts where a student is enrolled with counts"""
        if not MODELS_AVAILABLE:
            return []
        
        student_count_subquery = self.db.query(
            CohortStudent.cohort_id,
            func.count(CohortStudent.id).label('student_count')
        ).filter(
            CohortStudent.status == "approved"
        ).group_by(CohortStudent.cohort_id).subquery()
        
        simulation_count_subquery = self.db.query(
            CohortSimulation.cohort_id,
            func.count(CohortSimulation.id).label('simulation_count')
        ).join(
            Scenario, CohortSimulation.simulation_id == Scenario.id
        ).filter(
            Scenario.is_draft == False,
            Scenario.status == "active"
        ).group_by(CohortSimulation.cohort_id).subquery()
        
        return self.db.query(Cohort, CohortStudent).options(
            selectinload(Cohort.creator)
        ).join(
            CohortStudent, Cohort.id == CohortStudent.cohort_id
        ).outerjoin(
            student_count_subquery,
            Cohort.id == student_count_subquery.c.cohort_id
        ).outerjoin(
            simulation_count_subquery,
            Cohort.id == simulation_count_subquery.c.cohort_id
        ).add_columns(
            coalesce(student_count_subquery.c.student_count, 0).label('student_count'),
            coalesce(simulation_count_subquery.c.simulation_count, 0).label('simulation_count')
        ).filter(
            CohortStudent.student_id == student_id,
            CohortStudent.status == "approved"
        ).all()
    
    def get_student_cohort_simulations(
        self, cohort_id: int, student_id: int
    ) -> List[Tuple]:
        """Get simulations assigned to a cohort that a student is enrolled in"""
        if not MODELS_AVAILABLE:
            return []
        
        # Verify student is enrolled
        enrollment = self.db.query(CohortStudent).filter(
            CohortStudent.cohort_id == cohort_id,
            CohortStudent.student_id == student_id,
            CohortStudent.status == "approved"
        ).first()
        
        if not enrollment:
            return []
        
        return self.db.query(CohortSimulation, Scenario).join(
            Scenario, CohortSimulation.simulation_id == Scenario.id
        ).filter(
            CohortSimulation.cohort_id == cohort_id,
            Scenario.is_draft == False,
            Scenario.status == "active"
        ).all()
    
    def refresh_assigned_simulations(self, professor_id: int) -> dict:
        """Recalculate time_spent for all student instances in professor's cohorts"""
        if not MODELS_AVAILABLE:
            return {"refreshed": False}
        
        cohorts = self.db.query(Cohort).filter(Cohort.created_by == professor_id).all()
        refreshed_count = 0
        
        for cohort in cohorts:
            assignments = self.db.query(CohortSimulation).filter(
                CohortSimulation.cohort_id == cohort.id
            ).all()
            
            for assignment in assignments:
                if not StudentSimulationInstance:
                    continue
                
                instances = self.db.query(StudentSimulationInstance).filter(
                    StudentSimulationInstance.cohort_assignment_id == assignment.id
                ).all()
                
                for instance in instances:
                    start_dt = instance.started_at
                    end_dt = instance.completed_at
                    
                    if instance.user_progress_id and UserProgress:
                        up = self.db.query(UserProgress).filter(
                            UserProgress.id == instance.user_progress_id
                        ).first()
                        
                        if not start_dt and up:
                            start_dt = up.created_at
                        if not end_dt and up:
                            end_dt = (getattr(up, 'last_activity', None) or up.updated_at)
                        
                        # Recompute completion percentage
                        if up:
                            if (hasattr(up, 'simulation_status') and 
                                up.simulation_status in ["completed", "graded"]) or \
                               instance.status in ["completed", "graded", "submitted"]:
                                if instance.completion_percentage != 100.0:
                                    instance.completion_percentage = 100.0
                            elif SceneProgress and ScenarioScene:
                                total_scenes = self.db.query(ScenarioScene).filter(
                                    ScenarioScene.scenario_id == up.scenario_id
                                ).count()
                                completed_scenes = self.db.query(SceneProgress).filter(
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
                        refreshed_count += 1
        
        self.db.commit()
        return {"refreshed": True, "refreshed_count": refreshed_count}

