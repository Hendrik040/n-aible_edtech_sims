"""
Cohort-specific Pydantic schemas
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# --- INVITE LINK SCHEMAS ---

class InviteLinkCreate(BaseModel):
    """Schema for creating a new invite link"""
    type: str = Field(default="SINGLE_USE", description="SINGLE_USE or MULTI_USE")
    max_uses: Optional[int] = Field(default=None, ge=1, description="Maximum uses (only for MULTI_USE)")
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=90, description="Days until expiration (leave empty for no expiry)")


class InviteLinkResponse(BaseModel):
    """Schema for invite link response"""
    invite_id: int
    invite_url: str
    token: str
    invite_type: str
    max_uses: Optional[int]
    uses_count: int
    uses_left: Optional[int]
    expires_at: datetime
    created_at: datetime
    is_expired: bool
    is_used_up: bool
    status: str


class InviteLinksListResponse(BaseModel):
    """Schema for list of invite links"""
    invites: List[InviteLinkResponse]
    total: int


class ClearExpiredResponse(BaseModel):
    """Schema for clear expired invites response"""
    deleted_count: int
    message: str


# --- COHORT CRUD SCHEMAS ---

class CohortCreate(BaseModel):
    title: str
    description: Optional[str] = None
    course_code: Optional[str] = None
    semester: Optional[str] = None
    year: Optional[int] = None
    max_students: Optional[int] = None
    auto_approve: bool = True
    allow_self_enrollment: bool = False


class CohortUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    course_code: Optional[str] = None
    semester: Optional[str] = None
    year: Optional[int] = None
    max_students: Optional[int] = None
    auto_approve: Optional[bool] = None
    allow_self_enrollment: Optional[bool] = None
    is_active: Optional[bool] = None


class CohortStudentResponse(BaseModel):
    id: int
    student_id: int
    student_name: str
    student_email: str
    status: str
    enrollment_date: datetime
    approved_at: Optional[datetime] = None


class SimulationDetails(BaseModel):
    """Simulation details included in cohort simulation response"""
    id: int
    title: str
    description: Optional[str] = None
    is_draft: bool = False
    status: Optional[str] = None


class CohortSimulationResponse(BaseModel):
    id: int
    simulation_id: int
    assigned_by: int
    assigned_at: datetime
    due_date: Optional[datetime] = None
    is_required: bool
    simulation: Optional[SimulationDetails] = None


class CohortResponse(BaseModel):
    id: int
    unique_id: str
    title: str
    description: Optional[str]
    course_code: Optional[str]
    semester: Optional[str]
    year: Optional[int]
    max_students: Optional[int]
    auto_approve: bool
    allow_self_enrollment: bool
    is_active: bool
    created_by: int
    created_at: datetime
    updated_at: datetime
    students: List[CohortStudentResponse] = []
    simulations: List[CohortSimulationResponse] = []


class CohortListResponse(BaseModel):
    id: int
    unique_id: str
    title: str
    description: Optional[str]
    course_code: Optional[str]
    semester: Optional[str]
    year: Optional[int]
    max_students: Optional[int]
    is_active: bool
    created_by: int
    created_at: datetime
    student_count: int = 0
    simulation_count: int = 0


class CohortStudentCreate(BaseModel):
    student_id: int
    status: str = "pending"


class CohortStudentUpdate(BaseModel):
    status: str


class CohortSimulationCreate(BaseModel):
    simulation_id: int
    due_date: Optional[datetime] = None
    is_required: bool = True


class CohortSimulationUpdate(BaseModel):
    due_date: Optional[datetime] = None
    is_required: Optional[bool] = None


class BulkRemoveStudentsRequest(BaseModel):
    student_ids: List[int]


# --- COMPLETION SUMMARY SCHEMAS ---

class SimulationCompletionItem(BaseModel):
    """Completion stats for a single simulation in a cohort"""
    simulation_assignment_id: int
    simulation_id: int
    simulation_title: str
    completed_count: int
    graded_count: int
    total_students: int


class CohortCompletionSummaryResponse(BaseModel):
    """Batched completion summary for all simulations in a cohort"""
    cohort_id: int
    simulations: List[SimulationCompletionItem]

