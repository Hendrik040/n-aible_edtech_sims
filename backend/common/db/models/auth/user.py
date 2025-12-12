"""User model for authentication and user management."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from common.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, default="student")
    
    # Profile fields
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    profile_public: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_contact: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # OAuth fields
    provider: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    google_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, unique=True)
    
    # Gamification/Stats
    reputation_score: Mapped[int] = mapped_column(Integer, default=0)
    total_simulations: Mapped[int] = mapped_column(Integer, default=0)
    published_simulations: Mapped[int] = mapped_column(Integer, name="published_scenarios", default=0)  # DB column name kept for compatibility
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    # Relationships would go here (e.g. simulations, progress)
    # simulations = relationship("Simulation", back_populates="author")
