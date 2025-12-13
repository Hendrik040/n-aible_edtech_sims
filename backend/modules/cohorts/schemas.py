"""
Cohort-specific Pydantic schemas
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


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


class CohortSimulationResponse(BaseModel):
    id: int
    simulation_id: int
    assigned_by: int
    assigned_at: datetime
    due_date: Optional[datetime] = None
    is_required: bool


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

