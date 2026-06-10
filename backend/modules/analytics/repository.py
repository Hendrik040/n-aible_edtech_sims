"""
Analytics repository - Read-only database queries for cohort analytics

All methods are pure reads. Aggregation that is cheap to express in SQL is
done here; anything that needs Python-side shaping lives in the service.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple, Dict

from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import and_, or_, func, distinct, case

logger = logging.getLogger(__name__)

# Import models - handle missing models gracefully (mirrors cohorts module)
try:
    from common.db.models import (
        Cohort, CohortStudent, CohortSimulation, StudentSimulationInstance,
        GradeHistory,
    )
    MODELS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Analytics models not found: {e}. They need to be added to common/db/models.py")
    MODELS_AVAILABLE = False
    Cohort = None
    CohortStudent = None
    CohortSimulation = None
    StudentSimulationInstance = None
    GradeHistory = None

try:
    from common.db.models import User, Simulation
except ImportError:
    User = None
    Simulation = None

# Statuses that count as "the student finished the work"
COMPLETED_STATUSES = ("completed", "submitted", "graded")
# Statuses that count as "the student has at least opened the work"
ACTIVE_STATUSES = ("in_progress", "completed", "submitted", "graded")


class AnalyticsRepository:
    """Repository for read-only analytics queries."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Ownership / lookup helpers
    # ------------------------------------------------------------------

    def get_cohort_owned_by(self, cohort_id: int, professor_id: int) -> Optional[Cohort]:
        """Return the cohort only if it is owned by the given professor."""
        return self.db.query(Cohort).filter(
            and_(Cohort.id == cohort_id, Cohort.created_by == professor_id)
        ).first()

    def get_cohort_by_unique_id_owned_by(self, unique_id: str, professor_id: int) -> Optional[Cohort]:
        """Return the cohort by its public unique_id, scoped to the owner."""
        return self.db.query(Cohort).filter(
            and_(Cohort.unique_id == unique_id, Cohort.created_by == professor_id)
        ).first()

    def get_assignment_in_cohort(self, cohort_id: int, cohort_simulation_id: int) -> Optional[CohortSimulation]:
        """Return an assignment, verifying it belongs to the given cohort."""
        return (
            self.db.query(CohortSimulation)
            .options(joinedload(CohortSimulation.simulation))
            .filter(
                and_(
                    CohortSimulation.id == cohort_simulation_id,
                    CohortSimulation.cohort_id == cohort_id,
                )
            )
            .first()
        )

    def get_professor_cohorts(self, professor_id: int, active_only: bool = False) -> List[Cohort]:
        """All cohorts created by a professor."""
        query = self.db.query(Cohort).filter(Cohort.created_by == professor_id)
        if active_only:
            query = query.filter(Cohort.is_active.is_(True))
        return query.order_by(Cohort.created_at.desc()).all()

    # ------------------------------------------------------------------
    # Enrollment counts
    # ------------------------------------------------------------------

    def count_students_by_status(self, cohort_id: int) -> Dict[str, int]:
        """Return {status: count} for students in a cohort."""
        rows = (
            self.db.query(CohortStudent.status, func.count(CohortStudent.id))
            .filter(CohortStudent.cohort_id == cohort_id)
            .group_by(CohortStudent.status)
            .all()
        )
        return {status: count for status, count in rows}

    def get_approved_student_ids(self, cohort_id: int) -> List[int]:
        """IDs of students with an approved enrollment in the cohort."""
        rows = (
            self.db.query(CohortStudent.student_id)
            .filter(
                and_(
                    CohortStudent.cohort_id == cohort_id,
                    CohortStudent.status == "approved",
                )
            )
            .all()
        )
        return [row[0] for row in rows]

    def get_approved_students(self, cohort_id: int) -> List[User]:
        """Approved student User rows for a cohort."""
        return (
            self.db.query(User)
            .join(CohortStudent, CohortStudent.student_id == User.id)
            .filter(
                and_(
                    CohortStudent.cohort_id == cohort_id,
                    CohortStudent.status == "approved",
                )
            )
            .order_by(User.full_name.asc())
            .all()
        )

    # ------------------------------------------------------------------
    # Assignment queries
    # ------------------------------------------------------------------

    def get_cohort_assignments(self, cohort_id: int) -> List[CohortSimulation]:
        """All assignments for a cohort with their simulation eagerly loaded."""
        return (
            self.db.query(CohortSimulation)
            .options(joinedload(CohortSimulation.simulation))
            .filter(CohortSimulation.cohort_id == cohort_id)
            .order_by(CohortSimulation.assigned_at.asc())
            .all()
        )

    def count_assignments(self, cohort_id: int) -> Tuple[int, int]:
        """Return (total_assignments, required_assignments) for a cohort."""
        total = (
            self.db.query(func.count(CohortSimulation.id))
            .filter(CohortSimulation.cohort_id == cohort_id)
            .scalar()
        ) or 0
        required = (
            self.db.query(func.count(CohortSimulation.id))
            .filter(
                and_(
                    CohortSimulation.cohort_id == cohort_id,
                    CohortSimulation.is_required.is_(True),
                )
            )
            .scalar()
        ) or 0
        return total, required

    # ------------------------------------------------------------------
    # Instance queries
    # ------------------------------------------------------------------

    def get_cohort_instances(self, cohort_id: int) -> List[StudentSimulationInstance]:
        """All student simulation instances tied to a cohort's assignments."""
        return (
            self.db.query(StudentSimulationInstance)
            .join(
                CohortSimulation,
                StudentSimulationInstance.cohort_assignment_id == CohortSimulation.id,
            )
            .options(
                joinedload(StudentSimulationInstance.student),
                joinedload(StudentSimulationInstance.cohort_assignment)
                .joinedload(CohortSimulation.simulation),
            )
            .filter(CohortSimulation.cohort_id == cohort_id)
            .all()
        )

    def get_assignment_instances(self, cohort_simulation_id: int) -> List[StudentSimulationInstance]:
        """All instances for a single assignment."""
        return (
            self.db.query(StudentSimulationInstance)
            .options(joinedload(StudentSimulationInstance.student))
            .filter(StudentSimulationInstance.cohort_assignment_id == cohort_simulation_id)
            .all()
        )

    def get_instance_status_counts(self, cohort_simulation_id: int) -> Dict[str, int]:
        """Return {status: count} for a single assignment's instances."""
        rows = (
            self.db.query(
                StudentSimulationInstance.status,
                func.count(StudentSimulationInstance.id),
            )
            .filter(StudentSimulationInstance.cohort_assignment_id == cohort_simulation_id)
            .group_by(StudentSimulationInstance.status)
            .all()
        )
        return {status: count for status, count in rows}

    def get_final_grades(self, cohort_id: int) -> List[float]:
        """All non-null final grades across a cohort, in no particular order."""
        rows = (
            self.db.query(StudentSimulationInstance.grade)
            .join(
                CohortSimulation,
                StudentSimulationInstance.cohort_assignment_id == CohortSimulation.id,
            )
            .filter(
                and_(
                    CohortSimulation.cohort_id == cohort_id,
                    StudentSimulationInstance.grade.isnot(None),
                )
            )
            .all()
        )
        return [row[0] for row in rows]

    def get_assignment_grades(self, cohort_simulation_id: int) -> List[float]:
        """All non-null final grades for a single assignment."""
        rows = (
            self.db.query(StudentSimulationInstance.grade)
            .filter(
                and_(
                    StudentSimulationInstance.cohort_assignment_id == cohort_simulation_id,
                    StudentSimulationInstance.grade.isnot(None),
                )
            )
            .all()
        )
        return [row[0] for row in rows]

    def count_overdue_instances(self, cohort_id: int) -> int:
        """Number of overdue instances across the whole cohort."""
        return (
            self.db.query(func.count(StudentSimulationInstance.id))
            .join(
                CohortSimulation,
                StudentSimulationInstance.cohort_assignment_id == CohortSimulation.id,
            )
            .filter(
                and_(
                    CohortSimulation.cohort_id == cohort_id,
                    StudentSimulationInstance.is_overdue.is_(True),
                )
            )
            .scalar()
        ) or 0

    def count_pending_grading(self, professor_id: int) -> int:
        """Submitted-but-ungraded instances across all of a professor's cohorts."""
        return (
            self.db.query(func.count(StudentSimulationInstance.id))
            .join(
                CohortSimulation,
                StudentSimulationInstance.cohort_assignment_id == CohortSimulation.id,
            )
            .join(Cohort, CohortSimulation.cohort_id == Cohort.id)
            .filter(
                and_(
                    Cohort.created_by == professor_id,
                    StudentSimulationInstance.status == "submitted",
                    StudentSimulationInstance.grade.is_(None),
                )
            )
            .scalar()
        ) or 0

    # ------------------------------------------------------------------
    # Funnel queries (distinct students per stage)
    # ------------------------------------------------------------------

    def count_students_with_status_at_least(self, cohort_id: int, statuses: Tuple[str, ...]) -> int:
        """Distinct students in a cohort with at least one instance in `statuses`."""
        return (
            self.db.query(func.count(distinct(StudentSimulationInstance.student_id)))
            .join(
                CohortSimulation,
                StudentSimulationInstance.cohort_assignment_id == CohortSimulation.id,
            )
            .filter(
                and_(
                    CohortSimulation.cohort_id == cohort_id,
                    StudentSimulationInstance.status.in_(statuses),
                )
            )
            .scalar()
        ) or 0

    def count_students_with_grade(self, cohort_id: int) -> int:
        """Distinct students in a cohort with at least one final grade."""
        return (
            self.db.query(func.count(distinct(StudentSimulationInstance.student_id)))
            .join(
                CohortSimulation,
                StudentSimulationInstance.cohort_assignment_id == CohortSimulation.id,
            )
            .filter(
                and_(
                    CohortSimulation.cohort_id == cohort_id,
                    StudentSimulationInstance.grade.isnot(None),
                )
            )
            .scalar()
        ) or 0

    # ------------------------------------------------------------------
    # Engagement / time-window queries
    # ------------------------------------------------------------------

    def get_instances_started_between(
        self, cohort_id: int, start: datetime, end: datetime
    ) -> List[StudentSimulationInstance]:
        """Instances whose started_at falls inside [start, end)."""
        return (
            self.db.query(StudentSimulationInstance)
            .join(
                CohortSimulation,
                StudentSimulationInstance.cohort_assignment_id == CohortSimulation.id,
            )
            .filter(
                and_(
                    CohortSimulation.cohort_id == cohort_id,
                    StudentSimulationInstance.started_at.isnot(None),
                    StudentSimulationInstance.started_at >= start,
                    StudentSimulationInstance.started_at < end,
                )
            )
            .all()
        )

    def get_submissions_between(
        self, cohort_id: int, start: datetime, end: datetime
    ) -> List[StudentSimulationInstance]:
        """Instances whose submitted_at falls inside [start, end)."""
        return (
            self.db.query(StudentSimulationInstance)
            .join(
                CohortSimulation,
                StudentSimulationInstance.cohort_assignment_id == CohortSimulation.id,
            )
            .filter(
                and_(
                    CohortSimulation.cohort_id == cohort_id,
                    StudentSimulationInstance.submitted_at.isnot(None),
                    StudentSimulationInstance.submitted_at >= start,
                    StudentSimulationInstance.submitted_at < end,
                )
            )
            .all()
        )

    def get_last_activity_map(self, cohort_id: int) -> Dict[int, datetime]:
        """Map of student_id -> most recent updated_at across their instances."""
        rows = (
            self.db.query(
                StudentSimulationInstance.student_id,
                func.max(StudentSimulationInstance.updated_at),
            )
            .join(
                CohortSimulation,
                StudentSimulationInstance.cohort_assignment_id == CohortSimulation.id,
            )
            .filter(CohortSimulation.cohort_id == cohort_id)
            .group_by(StudentSimulationInstance.student_id)
            .all()
        )
        return {student_id: last_seen for student_id, last_seen in rows}

    def get_student_instance_map(
        self, cohort_id: int
    ) -> Dict[int, List[StudentSimulationInstance]]:
        """Map of student_id -> all of their instances in the cohort."""
        instances = self.get_cohort_instances(cohort_id)
        by_student: Dict[int, List[StudentSimulationInstance]] = {}
        for instance in instances:
            by_student.setdefault(instance.student_id, []).append(instance)
        return by_student

    # ------------------------------------------------------------------
    # Cohort aggregate scalars
    # ------------------------------------------------------------------

    def get_cohort_aggregates(self, cohort_id: int) -> Tuple[float, float]:
        """Return (avg_completion_percentage, avg_time_spent_seconds) for a cohort."""
        row = (
            self.db.query(
                func.avg(StudentSimulationInstance.completion_percentage),
                func.avg(StudentSimulationInstance.total_time_spent),
            )
            .join(
                CohortSimulation,
                StudentSimulationInstance.cohort_assignment_id == CohortSimulation.id,
            )
            .filter(CohortSimulation.cohort_id == cohort_id)
            .first()
        )
        avg_completion = float(row[0]) if row and row[0] is not None else 0.0
        avg_time = float(row[1]) if row and row[1] is not None else 0.0
        return avg_completion, avg_time

    def get_assignment_aggregates(
        self, cohort_simulation_id: int
    ) -> Tuple[Optional[float], Optional[float], Optional[float], int]:
        """Return (avg_grade, avg_time_seconds, avg_attempts, overdue_count)."""
        row = (
            self.db.query(
                func.avg(StudentSimulationInstance.grade),
                func.avg(StudentSimulationInstance.total_time_spent),
                func.avg(StudentSimulationInstance.attempts_count),
                func.sum(
                    case((StudentSimulationInstance.is_overdue.is_(True), 1), else_=0)
                ),
            )
            .filter(StudentSimulationInstance.cohort_assignment_id == cohort_simulation_id)
            .first()
        )
        if not row:
            return None, None, None, 0
        avg_grade = float(row[0]) if row[0] is not None else None
        avg_time = float(row[1]) if row[1] is not None else None
        avg_attempts = float(row[2]) if row[2] is not None else None
        overdue = int(row[3]) if row[3] is not None else 0
        return avg_grade, avg_time, avg_attempts, overdue
