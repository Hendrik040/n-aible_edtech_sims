"""
User progress model for tracking simulation progress.

This is a minimal model to support the foreign key from StudentSimulationInstance.
The full implementation may be elsewhere (e.g., simulation engine).
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Integer, String, DateTime, Text, Float, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from common.db.base import Base

if TYPE_CHECKING:
    from common.db.models.auth.user import User
    from common.db.models.publishing.simulation import Simulation


class UserProgress(Base):
    """Track user progress through simulations."""
    __tablename__ = "user_progress"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    scenario_id: Mapped[int] = mapped_column(Integer, ForeignKey("scenarios.id"), nullable=False, index=True)
    
    # Progress tracking
    simulation_status: Mapped[str] = mapped_column(String, default="not_started")  # not_started, in_progress, completed
    current_scene_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    progress_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    
    # Performance metrics
    total_time_spent: Mapped[int] = mapped_column(Integer, default=0)  # seconds
    messages_sent: Mapped[int] = mapped_column(Integer, default=0)
    hints_used: Mapped[int] = mapped_column(Integer, default=0)
    
    # State storage
    conversation_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string
    simulation_state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string
    
    # Timestamps
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    scenario: Mapped["Simulation"] = relationship("Simulation", foreign_keys=[scenario_id])

