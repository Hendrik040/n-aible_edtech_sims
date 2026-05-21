"""Simulation review model for publishing module."""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from common.db.base import Base


class SimulationReview(Base):
    __tablename__ = "simulation_reviews"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    simulation_id: Mapped[int] = mapped_column(Integer, ForeignKey("simulations.id"), index=True)
    reviewer_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    rating: Mapped[int] = mapped_column(Integer)  # Rating from 1-5
    review_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pros: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    cons: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    
    # Relationships
    reviewer = relationship("User", foreign_keys=[reviewer_id])
