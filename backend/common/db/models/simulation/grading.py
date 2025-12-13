"""Grading material models for simulation runtime."""
from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy import Integer, String, ForeignKey, Text, JSON, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from common.db.base import Base


class GradingMaterial(Base):
    """Grading materials uploaded for simulations."""
    __tablename__ = "grading_materials"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    simulation_id: Mapped[int] = mapped_column(Integer, ForeignKey("simulations.id"), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processing_status: Mapped[str] = mapped_column(String, default="pending", nullable=False)  # e.g., "pending", "processing", "completed", "failed"
    processing_log: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class GradingMaterialChunk(Base):
    """Chunked grading materials with embeddings."""
    __tablename__ = "grading_material_chunks"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    material_id: Mapped[int] = mapped_column(Integer, ForeignKey("grading_materials.id"), index=True, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_vector: Mapped[Optional[List[float]]] = mapped_column(JSON, nullable=True)  # Store as JSON array for compatibility
    embedding_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    embedding_dimension: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

