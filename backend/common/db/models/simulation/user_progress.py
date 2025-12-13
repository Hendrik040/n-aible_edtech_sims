"""User progress models for simulation runtime."""
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import Integer, String, ForeignKey, JSON, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from common.db.base import Base


class UserProgress(Base):
    """Tracks user's progress through a simulation."""
    __tablename__ = "user_progress"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    scenario_id: Mapped[int] = mapped_column(Integer, ForeignKey("scenarios.id"), index=True, nullable=False)
    current_scene_id: Mapped[int] = mapped_column(Integer, ForeignKey("scenario_scenes.id"), nullable=False)
    simulation_status: Mapped[str] = mapped_column(String, default="in_progress", nullable=False)
    orchestrator_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Progress tracking fields
    scenes_completed: Mapped[Optional[List[int]]] = mapped_column(JSON, nullable=True, default=None)
    session_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hints_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    forced_progressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_percentage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_time_spent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # in seconds
    final_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # Timestamp fields
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

