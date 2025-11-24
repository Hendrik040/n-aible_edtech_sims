from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from common.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(15), unique=True, nullable=True, index=True)
    email = Column(String, unique=True, index=True)
    full_name = Column(String)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    avatar_url = Column(String, nullable=True)
    role = Column(String, default="user")

    google_id = Column(String, unique=True, nullable=True, index=True)
    provider = Column(String, default="password")

    published_scenarios = Column(Integer, default=0)
    total_simulations = Column(Integer, default=0)
    reputation_score = Column(Float, default=0.0)

    profile_public = Column(Boolean, default=True)
    allow_contact = Column(Boolean, default=True)

    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

    last_activity = Column(DateTime(timezone=True), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    scenarios = relationship("Scenario", back_populates="creator", foreign_keys="Scenario.created_by")
    scenario_reviews = relationship("ScenarioReview", back_populates="reviewer")
    user_progress = relationship("UserProgress", back_populates="user")
    created_cohorts = relationship("Cohort", back_populates="creator")

    sent_invitations = relationship(
        "CohortInvitation", foreign_keys="CohortInvitation.professor_id", back_populates=None
    )
    received_invitations = relationship(
        "CohortInvitation", foreign_keys="CohortInvitation.student_id", back_populates=None
    )
    notifications = relationship("Notification", back_populates="user")

    __table_args__ = (
        Index("idx_users_email", "email"),
        Index("idx_users_username", "username"),
        Index("idx_users_role", "role"),
        Index("idx_users_created_at", "created_at"),
        Index("idx_users_google_id", "google_id"),
        Index("idx_users_provider", "provider"),
    )


__all__ = ["User"]

