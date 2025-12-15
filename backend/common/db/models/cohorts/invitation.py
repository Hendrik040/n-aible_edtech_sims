"""
Cohort invitation models for student enrollment.

Contains:
- CohortInvitation: Direct email invitations sent by professors
- CohortInvite: Shareable invite links (single or multi-use)
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import (
    DateTime, Integer, String, Text, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from common.db.base import Base

if TYPE_CHECKING:
    from common.db.models.auth.user import User
    from .cohort import Cohort


class CohortInvitation(Base):
    """Cohort invitations sent by professors to students via email."""
    __tablename__ = "cohort_invitations"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cohort_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False
    )
    professor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    student_email: Mapped[str] = mapped_column(String(255), nullable=False)
    student_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    invitation_token: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")  # pending, accepted, declined, expired
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    cohort: Mapped["Cohort"] = relationship("Cohort")
    professor: Mapped["User"] = relationship("User", foreign_keys=[professor_id])
    student: Mapped[Optional["User"]] = relationship("User", foreign_keys=[student_id])
    
    __table_args__ = (
        Index('idx_cohort_invitations_cohort_id', 'cohort_id'),
        Index('idx_cohort_invitations_professor_id', 'professor_id'),
        Index('idx_cohort_invitations_student_email', 'student_email'),
        Index('idx_cohort_invitations_token', 'invitation_token'),
        Index('idx_cohort_invitations_status', 'status'),
    )


class CohortInvite(Base):
    """Shareable invite links for cohorts (single-use or multi-use)."""
    __tablename__ = "cohort_invites"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cohort_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    invite_type: Mapped[str] = mapped_column(String(20), nullable=False, default="SINGLE_USE")  # SINGLE_USE or MULTI_USE
    max_uses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Only for MULTI_USE
    uses_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Single-use tracking
    used_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    cohort: Mapped["Cohort"] = relationship("Cohort")
    creator: Mapped["User"] = relationship("User", foreign_keys=[created_by])
    user_who_used: Mapped[Optional["User"]] = relationship("User", foreign_keys=[used_by])
    
    __table_args__ = (
        Index('idx_cohort_invites_cohort_id', 'cohort_id'),
        Index('idx_cohort_invites_token', 'token'),
        Index('idx_cohort_invites_token_hash', 'token_hash'),
        Index('idx_cohort_invites_type', 'invite_type'),
        Index('idx_cohort_invites_created_by', 'created_by'),
        Index('idx_cohort_invites_expires_at', 'expires_at'),
        UniqueConstraint('token_hash', name='unique_token_hash'),
        UniqueConstraint('token', name='unique_token'),
    )

