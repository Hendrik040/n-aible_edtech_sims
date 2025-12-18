"""
Student simulation instance models for tracking individual student progress.

Contains:
- StudentSimulationInstance: Individual student's simulation progress
- GradeHistory: Audit trail for grade changes
"""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import (
    Boolean, DateTime, Float, Integer, String, Text, ForeignKey, Index, UniqueConstraint, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from common.db.base import Base

if TYPE_CHECKING:
    from common.db.models.auth.user import User
    from .cohort import CohortSimulation


class StudentSimulationInstance(Base):
    """Individual student simulation instances for cohort assignments."""
    __tablename__ = "student_simulation_instances"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    unique_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    # cohort_assignment_id is nullable to support test simulations (professor/test-simulations)
    # Real cohort simulations will have this set, test simulations will have None
    cohort_assignment_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("cohort_simulations.id"), nullable=True, index=True
    )
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # FK to user_progress - use_alter=True defers FK creation so table doesn't need to exist yet
    user_progress_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_progress.id", use_alter=True, name="fk_student_sim_instances_user_progress"), 
        nullable=True, index=True
    )
    
    # Instance status
    status: Mapped[str] = mapped_column(String, default="not_started")  # not_started, in_progress, completed, submitted, graded
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # AI Grading fields
    ai_grade: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_graded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Professor Grading fields (final grade)
    grade: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    graded_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    graded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Grade status tracking
    grade_status: Mapped[str] = mapped_column(String, default="not_graded", index=True)
    
    # Performance metrics
    completion_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    total_time_spent: Mapped[int] = mapped_column(Integer, default=0)  # seconds
    attempts_count: Mapped[int] = mapped_column(Integer, default=0)
    hints_used: Mapped[int] = mapped_column(Integer, default=0)
    
    # Due date tracking
    is_overdue: Mapped[bool] = mapped_column(Boolean, default=False)
    days_late: Mapped[int] = mapped_column(Integer, default=0)
    
    # Generic JSON data field for backward compatibility with test simulations
    instance_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    cohort_assignment: Mapped[Optional["CohortSimulation"]] = relationship("CohortSimulation", back_populates="student_instances")
    student: Mapped["User"] = relationship("User", foreign_keys=[student_id])
    grader: Mapped[Optional["User"]] = relationship("User", foreign_keys=[graded_by])
    grade_history_records: Mapped[List["GradeHistory"]] = relationship(
        "GradeHistory", back_populates="instance", cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        Index('idx_student_sim_instances_cohort_assignment', 'cohort_assignment_id'),
        Index('idx_student_sim_instances_student_id', 'student_id'),
        Index('idx_student_sim_instances_user_progress', 'user_progress_id'),
        Index('idx_student_sim_instances_status', 'status'),
        Index('idx_student_sim_instances_grade', 'grade'),
        Index('idx_student_sim_instances_completed_at', 'completed_at'),
        UniqueConstraint('student_id', 'cohort_assignment_id', name='unique_student_cohort_assignment'),
    )


class GradeHistory(Base):
    """Grade history log for audit trail of all grading changes."""
    __tablename__ = "grade_history"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    instance_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("student_simulation_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    grade_type: Mapped[str] = mapped_column(String, nullable=False, index=True)  # 'ai' or 'professor'
    grade_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    graded_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    previous_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    new_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationships
    instance: Mapped["StudentSimulationInstance"] = relationship("StudentSimulationInstance", back_populates="grade_history_records")
    grader: Mapped[Optional["User"]] = relationship("User", foreign_keys=[graded_by])
    
    __table_args__ = (
        Index('idx_grade_history_instance_id', 'instance_id'),
        Index('idx_grade_history_graded_by', 'graded_by'),
        Index('idx_grade_history_created_at', 'created_at'),
        Index('idx_grade_history_grade_type', 'grade_type'),
    )

