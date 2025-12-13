"""
Cohort models for educational group management.

Contains:
- Cohort: Main cohort entity (class groups)
- CohortStudent: Student enrollments in cohorts
- CohortSimulation: Simulations assigned to cohorts
"""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import (
    Boolean, DateTime, Integer, String, Text, ForeignKey, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from common.db.base import Base

if TYPE_CHECKING:
    from common.db.models.auth.user import User
    from common.db.models.publishing.simulation import Simulation
    from .student_instance import StudentSimulationInstance


class Cohort(Base):
    """Cohort management for educational groups."""
    __tablename__ = "cohorts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    unique_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    course_code: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    semester: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    max_students: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Settings
    auto_approve: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_self_enrollment: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    
    # Metadata
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    creator: Mapped["User"] = relationship("User", back_populates="created_cohorts", foreign_keys=[created_by])
    students: Mapped[List["CohortStudent"]] = relationship("CohortStudent", back_populates="cohort", cascade="all, delete-orphan")
    simulations: Mapped[List["CohortSimulation"]] = relationship("CohortSimulation", back_populates="cohort", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_cohorts_created_by', 'created_by'),
        Index('idx_cohorts_active', 'is_active'),
        Index('idx_cohorts_year', 'year'),
        Index('idx_cohorts_course_code', 'course_code'),
    )


class CohortStudent(Base):
    """Student enrollment in cohorts."""
    __tablename__ = "cohort_students"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cohort_id: Mapped[int] = mapped_column(Integer, ForeignKey("cohorts.id"), nullable=False, index=True)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Enrollment status
    status: Mapped[str] = mapped_column(String, default="pending")  # pending, approved, rejected, withdrawn
    enrollment_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    cohort: Mapped["Cohort"] = relationship("Cohort", back_populates="students")
    student: Mapped["User"] = relationship("User", foreign_keys=[student_id])
    approver: Mapped[Optional["User"]] = relationship("User", foreign_keys=[approved_by])
    
    __table_args__ = (
        Index('idx_cohort_students_cohort_id', 'cohort_id'),
        Index('idx_cohort_students_student_id', 'student_id'),
        Index('idx_cohort_students_status', 'status'),
        Index('idx_cohort_students_enrollment_date', 'enrollment_date'),
    )


class CohortSimulation(Base):
    """Simulations assigned to cohorts."""
    __tablename__ = "cohort_simulations"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cohort_id: Mapped[int] = mapped_column(Integer, ForeignKey("cohorts.id"), nullable=False, index=True)
    simulation_id: Mapped[int] = mapped_column(Integer, ForeignKey("scenarios.id"), nullable=False, index=True)
    
    # Assignment details
    assigned_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    cohort: Mapped["Cohort"] = relationship("Cohort", back_populates="simulations")
    simulation: Mapped["Simulation"] = relationship("Simulation")
    assigner: Mapped["User"] = relationship("User", foreign_keys=[assigned_by])
    student_instances: Mapped[List["StudentSimulationInstance"]] = relationship(
        "StudentSimulationInstance", back_populates="cohort_assignment", cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        Index('idx_cohort_simulations_cohort_id', 'cohort_id'),
        Index('idx_cohort_simulations_simulation_id', 'simulation_id'),
        Index('idx_cohort_simulations_assigned_by', 'assigned_by'),
        Index('idx_cohort_simulations_due_date', 'due_date'),
    )

