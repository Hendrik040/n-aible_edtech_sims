"""
Analytics service - Business logic for cohort and assignment analytics

Builds the response payloads consumed by the professor analytics dashboard:
cohort overviews, grade distributions, weekly engagement trends, per-assignment
breakdowns, at-risk reports, and the flat grade export.
"""
import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Tuple

from sqlalchemy.orm import Session

from .repository import (
    AnalyticsRepository,
    COMPLETED_STATUSES,
    ACTIVE_STATUSES,
)
from .schemas import (
    StudentSummary,
    SimulationSummary,
    GradeBucket,
    GradeDistribution,
    CompletionFunnel,
    EngagementPoint,
    AtRiskStudent,
    AssignmentPerformance,
    CohortAnalyticsOverview,
    CohortEngagementResponse,
    AtRiskReportResponse,
    AssignmentAnalyticsResponse,
    AssignmentDetailResponse,
    ProfessorDashboardResponse,
    CohortRollup,
    GradeExportRow,
    GradeExportResponse,
)

logger = logging.getLogger(__name__)

# Grades are recorded on a 0-100 scale; the histogram groups them by decade.
GRADE_BUCKET_COUNT = 10
GRADE_BUCKET_WIDTH = 10

# At-risk heuristic weights. The individual signals are normalized to [0, 1]
# before weighting, so the resulting score is also in [0, 1].
RISK_WEIGHT_OVERDUE = 0.35
RISK_WEIGHT_INACTIVITY = 0.25
RISK_WEIGHT_LOW_GRADE = 0.25
RISK_WEIGHT_NOT_STARTED = 0.15

# A student with no activity for this many days maxes out the inactivity signal.
INACTIVITY_WINDOW_DAYS = 21

# Grades below this are considered failing for the at-risk heuristic.
PASSING_GRADE = 60.0

DEFAULT_RISK_THRESHOLD = 0.5
DEFAULT_ENGAGEMENT_WEEKS = 8
MAX_ENGAGEMENT_WEEKS = 26


class CohortNotFoundError(Exception):
    """Raised when a cohort does not exist or is not owned by the caller."""


class AssignmentNotFoundError(Exception):
    """Raised when an assignment does not exist within the given cohort."""


class AnalyticsService:
    """Service exposing read-only analytics for professors."""

    def __init__(self, db: Session):
        self.db = db
        self.repository = AnalyticsRepository(db)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_cohort(self, cohort_id: int, professor_id: int):
        """Fetch a cohort scoped to its owner or raise CohortNotFoundError."""
        cohort = self.repository.get_cohort_owned_by(cohort_id, professor_id)
        if not cohort:
            raise CohortNotFoundError(
                f"Cohort {cohort_id} not found for professor {professor_id}"
            )
        return cohort

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _as_minutes(seconds: Optional[float]) -> float:
        """Convert a seconds value (possibly None) to whole minutes."""
        if not seconds:
            return 0.0
        return round(seconds / 60.0, 1)

    @staticmethod
    def _safe_rate(numerator: int, denominator: int) -> float:
        """Divide defensively, returning 0.0 for an empty denominator."""
        if denominator <= 0:
            return 0.0
        return round(numerator / denominator, 4)

    # ------------------------------------------------------------------
    # Grade distribution
    # ------------------------------------------------------------------

    def build_grade_distribution(self, grades: List[float]) -> GradeDistribution:
        """Build a decade-bucketed histogram plus summary statistics.

        Grades are expected on a 0-100 scale. Values outside the scale are
        clamped so a stray negative grade cannot corrupt the histogram.
        """
        buckets = [
            GradeBucket(
                label=f"{i * GRADE_BUCKET_WIDTH}-{i * GRADE_BUCKET_WIDTH + GRADE_BUCKET_WIDTH - 1}"
                if i < GRADE_BUCKET_COUNT - 1
                else f"{i * GRADE_BUCKET_WIDTH}-100",
                lower_bound=float(i * GRADE_BUCKET_WIDTH),
                upper_bound=float(i * GRADE_BUCKET_WIDTH + GRADE_BUCKET_WIDTH - 1)
                if i < GRADE_BUCKET_COUNT - 1
                else 100.0,
                count=0,
            )
            for i in range(GRADE_BUCKET_COUNT)
        ]

        if not grades:
            return GradeDistribution(total_graded=0, buckets=buckets)

        for grade in grades:
            clamped = max(0.0, grade)
            bucket_index = int(clamped // GRADE_BUCKET_WIDTH)
            buckets[bucket_index].count += 1

        return GradeDistribution(
            total_graded=len(grades),
            mean=round(statistics.fmean(grades), 2),
            median=round(statistics.median(grades), 2),
            std_dev=round(statistics.pstdev(grades), 2) if len(grades) > 1 else 0.0,
            min_grade=min(grades),
            max_grade=max(grades),
            buckets=buckets,
        )

    # ------------------------------------------------------------------
    # Cohort overview
    # ------------------------------------------------------------------

    def get_cohort_overview(self, cohort_id: int, professor_id: int) -> CohortAnalyticsOverview:
        """Headline analytics card for a single cohort."""
        cohort = self._require_cohort(cohort_id, professor_id)

        status_counts = self.repository.count_students_by_status(cohort_id)
        enrolled = status_counts.get("approved", 0)
        pending = status_counts.get("pending", 0)

        total_assignments, required_assignments = self.repository.count_assignments(cohort_id)

        funnel = CompletionFunnel(
            enrolled=enrolled,
            started=self.repository.count_students_with_status_at_least(
                cohort_id, ACTIVE_STATUSES
            ),
            completed=self.repository.count_students_with_status_at_least(
                cohort_id, COMPLETED_STATUSES
            ),
            submitted=self.repository.count_students_with_status_at_least(
                cohort_id, ("submitted", "graded")
            ),
            graded=self.repository.count_students_with_grade(cohort_id),
        )

        grades = self.repository.get_final_grades(cohort_id)
        distribution = self.build_grade_distribution(grades)

        avg_completion, avg_time_seconds = self.repository.get_cohort_aggregates(cohort_id)
        overdue = self.repository.count_overdue_instances(cohort_id)

        return CohortAnalyticsOverview(
            cohort_id=cohort.id,
            cohort_unique_id=cohort.unique_id,
            cohort_title=cohort.title,
            generated_at=self._now(),
            enrolled_students=enrolled,
            pending_students=pending,
            total_assignments=total_assignments,
            required_assignments=required_assignments,
            funnel=funnel,
            grade_distribution=distribution,
            average_completion_percentage=round(avg_completion, 2),
            average_time_spent_minutes=self._as_minutes(avg_time_seconds),
            overdue_instances=overdue,
        )

    # ------------------------------------------------------------------
    # Engagement trend
    # ------------------------------------------------------------------

    def get_engagement_trend(
        self, cohort_id: int, professor_id: int, weeks: int = DEFAULT_ENGAGEMENT_WEEKS
    ) -> CohortEngagementResponse:
        """Weekly engagement points for the last `weeks` ISO weeks."""
        self._require_cohort(cohort_id, professor_id)

        weeks = max(1, min(weeks, MAX_ENGAGEMENT_WEEKS))
        now = self._now()
        # Snap to the start of the current ISO week (Monday 00:00 UTC).
        week_start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        points: List[EngagementPoint] = []
        for offset in range(weeks - 1, -1, -1):
            window_start = week_start - timedelta(weeks=offset)
            window_end = window_start + timedelta(weeks=1)

            started = self.repository.get_instances_started_between(
                cohort_id, window_start, window_end
            )
            submitted = self.repository.get_submissions_between(
                cohort_id, window_start, window_end
            )

            active_ids = {i.student_id for i in started} | {
                i.student_id for i in submitted
            }
            time_spent_seconds = sum(i.total_time_spent or 0 for i in started)

            points.append(
                EngagementPoint(
                    week_start=window_start,
                    active_students=len(active_ids),
                    sessions_started=len(started),
                    submissions=len(submitted),
                    total_time_spent_minutes=int(time_spent_seconds // 60),
                )
            )

        return CohortEngagementResponse(cohort_id=cohort_id, weeks=weeks, points=points)

    # ------------------------------------------------------------------
    # Per-assignment analytics
    # ------------------------------------------------------------------

    def _build_assignment_performance(
        self, assignment, enrolled_count: int
    ) -> AssignmentPerformance:
        """Aggregate one assignment into an AssignmentPerformance row."""
        status_counts = self.repository.get_instance_status_counts(assignment.id)
        avg_grade, avg_time, avg_attempts, overdue = (
            self.repository.get_assignment_aggregates(assignment.id)
        )

        completed = status_counts.get("completed", 0)
        submitted = status_counts.get("submitted", 0)
        graded = status_counts.get("graded", 0)
        finished = completed + submitted + graded

        # Students who never created an instance also count as not started.
        instances_total = sum(status_counts.values())
        implicit_not_started = max(0, enrolled_count - instances_total)

        return AssignmentPerformance(
            cohort_simulation_id=assignment.id,
            simulation=SimulationSummary.model_validate(assignment.simulation),
            due_date=assignment.due_date,
            is_required=assignment.is_required,
            total_students=enrolled_count,
            not_started=status_counts.get("not_started", 0) + implicit_not_started,
            in_progress=status_counts.get("in_progress", 0),
            completed=completed,
            submitted=submitted,
            graded=graded,
            overdue=overdue,
            completion_rate=self._safe_rate(finished, enrolled_count),
            average_grade=round(avg_grade, 2) if avg_grade is not None else None,
            average_time_spent_minutes=self._as_minutes(avg_time) if avg_time else None,
            average_attempts=round(avg_attempts, 2) if avg_attempts is not None else None,
        )

    def get_assignment_analytics(
        self, cohort_id: int, professor_id: int
    ) -> AssignmentAnalyticsResponse:
        """Per-assignment breakdown table for a cohort."""
        self._require_cohort(cohort_id, professor_id)

        enrolled = len(self.repository.get_approved_student_ids(cohort_id))
        assignments = self.repository.get_cohort_assignments(cohort_id)

        rows = [
            self._build_assignment_performance(assignment, enrolled)
            for assignment in assignments
        ]
        return AssignmentAnalyticsResponse(cohort_id=cohort_id, assignments=rows)

    def get_assignment_detail(
        self, cohort_id: int, cohort_simulation_id: int, professor_id: int
    ) -> AssignmentDetailResponse:
        """Deep-dive analytics for one assignment."""
        self._require_cohort(cohort_id, professor_id)

        assignment = self.repository.get_assignment_in_cohort(
            cohort_id, cohort_simulation_id
        )
        if not assignment:
            raise AssignmentNotFoundError(
                f"Assignment {cohort_simulation_id} not found in cohort {cohort_id}"
            )

        enrolled = len(self.repository.get_approved_student_ids(cohort_id))
        performance = self._build_assignment_performance(assignment, enrolled)

        grades = self.repository.get_assignment_grades(cohort_simulation_id)
        distribution = self.build_grade_distribution(grades)

        instances = self.repository.get_assignment_instances(cohort_simulation_id)
        submissions_by_day: Dict[str, int] = {}
        for instance in instances:
            if instance.submitted_at:
                day_key = instance.submitted_at.date().isoformat()
                submissions_by_day[day_key] = submissions_by_day.get(day_key, 0) + 1

        return AssignmentDetailResponse(
            assignment=performance,
            grade_distribution=distribution,
            submissions_by_day=dict(sorted(submissions_by_day.items())),
        )

    # ------------------------------------------------------------------
    # At-risk report
    # ------------------------------------------------------------------

    def _score_student_risk(
        self,
        instances: List,
        assigned_count: int,
        last_activity: Optional[datetime],
        now: datetime,
    ) -> Tuple[float, List[str], Dict[str, float]]:
        """Compute the weighted risk score and human-readable factors."""
        factors: List[str] = []

        overdue_count = sum(1 for i in instances if i.is_overdue)
        completed_count = sum(1 for i in instances if i.status in COMPLETED_STATUSES)
        graded = [i.grade for i in instances if i.grade is not None]

        # Signal 1: overdue assignments, normalized by how many were assigned.
        overdue_signal = min(1.0, overdue_count / assigned_count) if assigned_count else 0.0
        if overdue_count:
            factors.append(f"{overdue_count} overdue assignment(s)")

        # Signal 2: days since last activity, capped at the window.
        if last_activity is None:
            inactivity_signal = 1.0
            factors.append("no recorded activity")
        else:
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=timezone.utc)
            idle_days = (now - last_activity).days
            inactivity_signal = min(1.0, max(0, idle_days) / INACTIVITY_WINDOW_DAYS)
            if idle_days >= 7:
                factors.append(f"inactive for {idle_days} days")

        # Signal 3: average grade below passing.
        if graded:
            average_grade = statistics.fmean(graded)
            if average_grade < PASSING_GRADE:
                low_grade_signal = (PASSING_GRADE - average_grade) / PASSING_GRADE
                factors.append(f"average grade {average_grade:.1f} below passing")
            else:
                low_grade_signal = 0.0
        else:
            # No grades yet is mildly concerning but not conclusive.
            low_grade_signal = 0.3

        # Signal 4: share of assigned work never started.
        started_count = sum(1 for i in instances if i.status != "not_started")
        if assigned_count:
            not_started_signal = max(0.0, 1.0 - started_count / assigned_count)
        else:
            not_started_signal = 0.0
        if assigned_count and started_count == 0:
            factors.append("has not started any assignment")

        score = (
            RISK_WEIGHT_OVERDUE * overdue_signal
            + RISK_WEIGHT_INACTIVITY * inactivity_signal
            + RISK_WEIGHT_LOW_GRADE * low_grade_signal
            + RISK_WEIGHT_NOT_STARTED * not_started_signal
        )
        signals = {
            "overdue": overdue_signal,
            "inactivity": inactivity_signal,
            "low_grade": low_grade_signal,
            "not_started": not_started_signal,
        }
        return round(min(1.0, score), 4), factors, signals

    def get_at_risk_report(
        self,
        cohort_id: int,
        professor_id: int,
        threshold: float = DEFAULT_RISK_THRESHOLD,
    ) -> AtRiskReportResponse:
        """Students whose weighted risk score meets or exceeds the threshold."""
        self._require_cohort(cohort_id, professor_id)
        threshold = max(0.0, min(1.0, threshold))

        now = self._now()
        students = self.repository.get_approved_students(cohort_id)
        total_assignments, _ = self.repository.count_assignments(cohort_id)
        instance_map = self.repository.get_student_instance_map(cohort_id)
        last_activity_map = self.repository.get_last_activity_map(cohort_id)

        flagged: List[AtRiskStudent] = []
        for student in students:
            instances = instance_map.get(student.id, [])
            score, factors, _signals = self._score_student_risk(
                instances=instances,
                assigned_count=total_assignments,
                last_activity=last_activity_map.get(student.id),
                now=now,
            )
            if score < threshold:
                continue

            graded = [i.grade for i in instances if i.grade is not None]
            flagged.append(
                AtRiskStudent(
                    student=StudentSummary.model_validate(student),
                    risk_score=score,
                    risk_factors=factors,
                    assignments_assigned=total_assignments,
                    assignments_completed=sum(
                        1 for i in instances if i.status in COMPLETED_STATUSES
                    ),
                    assignments_overdue=sum(1 for i in instances if i.is_overdue),
                    average_grade=round(statistics.fmean(graded), 2) if graded else None,
                    last_activity_at=last_activity_map.get(student.id),
                )
            )

        flagged.sort(key=lambda s: s.risk_score, reverse=True)
        return AtRiskReportResponse(
            cohort_id=cohort_id,
            generated_at=now,
            threshold=threshold,
            students=flagged,
        )

    # ------------------------------------------------------------------
    # Professor dashboard rollup
    # ------------------------------------------------------------------

    def get_professor_dashboard(self, professor_id: int) -> ProfessorDashboardResponse:
        """Cross-cohort rollup powering the professor analytics landing page."""
        cohorts = self.repository.get_professor_cohorts(professor_id)

        rollups: List[CohortRollup] = []
        total_students = 0
        total_assignments = 0

        for cohort in cohorts:
            status_counts = self.repository.count_students_by_status(cohort.id)
            enrolled = status_counts.get("approved", 0)
            assignments, _ = self.repository.count_assignments(cohort.id)
            grades = self.repository.get_final_grades(cohort.id)
            overdue = self.repository.count_overdue_instances(cohort.id)

            completed_students = self.repository.count_students_with_status_at_least(
                cohort.id, COMPLETED_STATUSES
            )

            rollups.append(
                CohortRollup(
                    cohort_id=cohort.id,
                    cohort_unique_id=cohort.unique_id,
                    title=cohort.title,
                    is_active=cohort.is_active,
                    enrolled_students=enrolled,
                    assignments=assignments,
                    average_grade=round(statistics.fmean(grades), 2) if grades else None,
                    completion_rate=self._safe_rate(completed_students, enrolled),
                    overdue_instances=overdue,
                )
            )
            total_students += enrolled
            total_assignments += assignments

        return ProfessorDashboardResponse(
            professor_id=professor_id,
            generated_at=self._now(),
            total_cohorts=len(cohorts),
            active_cohorts=sum(1 for c in cohorts if c.is_active),
            total_students=total_students,
            total_assignments=total_assignments,
            pending_grading=self.repository.count_pending_grading(professor_id),
            cohorts=rollups,
        )

    # ------------------------------------------------------------------
    # Grade export
    # ------------------------------------------------------------------

    def get_grade_export(self, cohort_id: int, professor_id: int) -> GradeExportResponse:
        """Flat student x assignment grade rows, suitable for CSV download."""
        self._require_cohort(cohort_id, professor_id)

        instances = self.repository.get_cohort_instances(cohort_id)
        rows: List[GradeExportRow] = []
        for instance in instances:
            assignment = instance.cohort_assignment
            simulation_title = (
                assignment.simulation.title
                if assignment and assignment.simulation
                else "Unknown simulation"
            )
            rows.append(
                GradeExportRow(
                    student_id=instance.student_id,
                    student_name=instance.student.full_name if instance.student else "",
                    student_email=instance.student.email if instance.student else "",
                    simulation_title=simulation_title,
                    status=instance.status,
                    grade=instance.grade,
                    ai_grade=instance.ai_grade,
                    completion_percentage=instance.completion_percentage or 0.0,
                    submitted_at=instance.submitted_at,
                    graded_at=instance.graded_at,
                    is_overdue=instance.is_overdue,
                    days_late=instance.days_late or 0,
                )
            )

        rows.sort(key=lambda r: (r.student_name.lower(), r.simulation_title.lower()))
        return GradeExportResponse(
            cohort_id=cohort_id,
            generated_at=self._now(),
            rows=rows,
        )
