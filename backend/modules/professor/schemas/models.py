from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from common.db.base import Base
from modules.simulation.schemas.models import generate_cohort_id


class Cohort(Base):
    __tablename__ = "cohorts"

    id = Column(Integer, primary_key=True, index=True)
    cohort_id = Column(String, unique=True, default=generate_cohort_id, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    professor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    institution = Column(String, nullable=True)
    program = Column(String, nullable=True)
    course_code = Column(String, nullable=True)
    max_students = Column(Integer, nullable=True)
    status = Column(String, default="active")
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    timezone = Column(String, default="UTC")
    meeting_link = Column(String, nullable=True)
    settings = Column(JSON, nullable=True)
    metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    creator = relationship("User", back_populates="created_cohorts")
    students = relationship("CohortStudent", back_populates="cohort")
    simulations = relationship("CohortSimulation", back_populates="cohort")

    __table_args__ = (
        Index("idx_cohorts_professor_id", "professor_id"),
        Index("idx_cohorts_status", "status"),
        Index("idx_cohorts_created_at", "created_at"),
    )


class CohortStudent(Base):
    __tablename__ = "cohort_students"

    id = Column(Integer, primary_key=True, index=True)
    cohort_id = Column(Integer, ForeignKey("cohorts.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String, default="active")
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    cohort = relationship("Cohort", back_populates="students")


class CohortSimulation(Base):
    __tablename__ = "cohort_simulations"

    id = Column(Integer, primary_key=True, index=True)
    cohort_id = Column(Integer, ForeignKey("cohorts.id"), nullable=False)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)
    assigned_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String, default="active")
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    deadline_at = Column(DateTime(timezone=True), nullable=True)
    grading_status = Column(String, default="not_started")
    availability_settings = Column(JSON, nullable=True)
    metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    cohort = relationship("Cohort", back_populates="simulations")


class CohortInvitation(Base):
    __tablename__ = "cohort_invitations"

    id = Column(Integer, primary_key=True, index=True)
    cohort_id = Column(Integer, ForeignKey("cohorts.id"), nullable=False)
    professor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    student_email = Column(String, nullable=False, index=True)
    invite_token = Column(String, unique=True, nullable=False, index=True)
    status = Column(String, default="pending")
    invitation_message = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    joined_at = Column(DateTime(timezone=True), nullable=True)
    metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    cohort = relationship("Cohort")


class CohortInvite(Base):
    __tablename__ = "cohort_invites"

    id = Column(Integer, primary_key=True, index=True)
    cohort_id = Column(Integer, ForeignKey("cohorts.id"), nullable=False)
    token = Column(String, unique=True, nullable=False)
    invite_url = Column(String, nullable=False)
    status = Column(String, default="active")
    max_uses = Column(Integer, nullable=True)
    uses = Column(Integer, default=0)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ProfessorStudentMessage(Base):
    __tablename__ = "professor_student_messages"

    id = Column(Integer, primary_key=True, index=True)
    cohort_id = Column(Integer, ForeignKey("cohorts.id"), nullable=False)
    professor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subject = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    message_type = Column(String, default="announcement")
    delivery_channels = Column(JSON, nullable=True)
    status = Column(String, default="sent")
    metadata = Column(JSON, nullable=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


__all__ = [
    "Cohort",
    "CohortInvitation",
    "CohortInvite",
    "CohortSimulation",
    "CohortStudent",
    "ProfessorStudentMessage",
]

