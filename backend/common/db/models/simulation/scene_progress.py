"""Scene progress models for simulation runtime."""
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import Integer, String, ForeignKey, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from common.db.base import Base


class SceneProgress(Base):
    """Tracks progress within a specific scene."""
    __tablename__ = "scene_progress"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_progress_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_progress.id"), index=True, nullable=False)
    scene_id: Mapped[int] = mapped_column(Integer, ForeignKey("simulation_scenes.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String, default="in_progress", nullable=False)
    progress_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

