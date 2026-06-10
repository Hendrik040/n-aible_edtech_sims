"""
Analytics-specific Pydantic schemas

Response models for cohort analytics, grade distributions, engagement
trends, assignment funnels, and at-risk student reports.
"""
from datetime import datetime
from typing import List, Optional, Dict
from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# Shared / leaf schemas
# ---------------------------------------------------------------------------

class StudentSummary(BaseModel):
    """Minimal student identity for embedding in analytics payloads."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str


class SimulationSummary(BaseModel):
    """Minimal simulation identity for embedding in analytics payloads."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    unique_id: str
    title: str


class GradeBucket(BaseModel):
    """A single histogram bucket of grades."""
    label: str = Field(..., description="Human readable bucket label, e.g. '70-79'")
    lower_bound: float = Field(..., description="Inclusive lower bound of the bucket")
    upper_bound: float = Field(..., description="Inclusive upper bound of the bucket")
    count: int = Field(0, description="Number of graded instances in this bucket")


class GradeDistribution(BaseModel):
    """Histogram of final grades for a cohort or an assignment."""
    total_graded: int = Field(0, description="Number of instances with a final grade")
    mean: Optional[float] = Field(None, description="Mean final grade")
    median: Optional[float] = Field(None, description="Median final grade")
    std_dev: Optional[float] = Field(None, description="Population standard deviation")
    min_grade: Optional[float] = None
    max_grade: Optional[float] = None
    buckets: List[GradeBucket] = Field(default_factory=list)


class CompletionFunnel(BaseModel):
    """Step-by-step funnel from enrollment to graded submission."""
    enrolled: int = Field(0, description="Approved students in the cohort")
    started: int = Field(0, description="Students who started at least one assignment")
    completed: int = Field(0, description="Students who completed at least one assignment")
    submitted: int = Field(0, description="Students who submitted at least one assignment")
    graded: int = Field(0, description="Students with at least one graded assignment")

    @property
    def started_rate(self) -> float:
        return round(self.started / self.enrolled, 4) if self.enrolled else 0.0


class EngagementPoint(BaseModel):
    """A single point on the weekly engagement trend line."""
    week_start: datetime = Field(..., description="UTC start of the ISO week")
    active_students: int = Field(0, description="Distinct students with activity in the week")
    sessions_started: int = Field(0, description="Simulation instances started in the week")
    submissions: int = Field(0, description="Submissions made in the week")
    total_time_spent_minutes: int = Field(0, description="Sum of recorded time across instances")


class AtRiskStudent(BaseModel):
    """A student flagged by the at-risk heuristic."""
    student: StudentSummary
    risk_score: float = Field(..., ge=0.0, le=1.0, description="0 (fine) to 1 (high risk)")
    risk_factors: List[str] = Field(default_factory=list)
    assignments_assigned: int = 0
    assignments_completed: int = 0
    assignments_overdue: int = 0
    average_grade: Optional[float] = None
    last_activity_at: Optional[datetime] = None


class AssignmentPerformance(BaseModel):
    """Aggregated performance for one cohort assignment."""
    cohort_simulation_id: int
    simulation: SimulationSummary
    due_date: Optional[datetime] = None
    is_required: bool = True
    total_students: int = 0
    not_started: int = 0
    in_progress: int = 0
    completed: int = 0
    submitted: int = 0
    graded: int = 0
    overdue: int = 0
    completion_rate: float = Field(0.0, description="completed+submitted+graded / total")
    average_grade: Optional[float] = None
    average_time_spent_minutes: Optional[float] = None
    average_attempts: Optional[float] = None


# ---------------------------------------------------------------------------
# Top-level response schemas
# ---------------------------------------------------------------------------

class CohortAnalyticsOverview(BaseModel):
    """Headline metrics for a single cohort."""
    cohort_id: int
    cohort_unique_id: str
    cohort_title: str
    generated_at: datetime

    enrolled_students: int = 0
    pending_students: int = 0
    total_assignments: int = 0
    required_assignments: int = 0

    funnel: CompletionFunnel
    grade_distribution: GradeDistribution

    average_completion_percentage: float = 0.0
    average_time_spent_minutes: float = 0.0
    overdue_instances: int = 0


class CohortEngagementResponse(BaseModel):
    """Weekly engagement trend for a cohort."""
    cohort_id: int
    weeks: int
    points: List[EngagementPoint] = Field(default_factory=list)


class AtRiskReportResponse(BaseModel):
    """At-risk student report for a cohort."""
    cohort_id: int
    generated_at: datetime
    threshold: float = Field(..., description="Risk score threshold used for inclusion")
    students: List[AtRiskStudent] = Field(default_factory=list)


class AssignmentAnalyticsResponse(BaseModel):
    """Per-assignment breakdown for a cohort."""
    cohort_id: int
    assignments: List[AssignmentPerformance] = Field(default_factory=list)


class AssignmentDetailResponse(BaseModel):
    """Deep-dive analytics for a single assignment."""
    assignment: AssignmentPerformance
    grade_distribution: GradeDistribution
    submissions_by_day: Dict[str, int] = Field(
        default_factory=dict,
        description="ISO date string -> number of submissions on that day",
    )


class ProfessorDashboardResponse(BaseModel):
    """Cross-cohort rollup for the professor landing page."""
    professor_id: int
    generated_at: datetime
    total_cohorts: int = 0
    active_cohorts: int = 0
    total_students: int = 0
    total_assignments: int = 0
    pending_grading: int = Field(0, description="Submitted instances awaiting a final grade")
    cohorts: List["CohortRollup"] = Field(default_factory=list)


class CohortRollup(BaseModel):
    """One row in the professor dashboard cohort table."""
    cohort_id: int
    cohort_unique_id: str
    title: str
    is_active: bool
    enrolled_students: int = 0
    assignments: int = 0
    average_grade: Optional[float] = None
    completion_rate: float = 0.0
    overdue_instances: int = 0


class GradeExportRow(BaseModel):
    """One row of the flat grade export."""
    student_id: int
    student_name: str
    student_email: str
    simulation_title: str
    status: str
    grade: Optional[float] = None
    ai_grade: Optional[float] = None
    completion_percentage: float = 0.0
    submitted_at: Optional[datetime] = None
    graded_at: Optional[datetime] = None
    is_overdue: bool = False
    days_late: int = 0


class GradeExportResponse(BaseModel):
    """Flat export of every student x assignment grade cell in a cohort."""
    cohort_id: int
    generated_at: datetime
    rows: List[GradeExportRow] = Field(default_factory=list)


# Resolve forward references
ProfessorDashboardResponse.model_rebuild()
