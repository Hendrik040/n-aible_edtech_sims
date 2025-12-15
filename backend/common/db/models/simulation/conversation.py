"""Conversation models for simulation runtime."""
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import Integer, String, ForeignKey, Text, JSON, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from common.db.base import Base


class ConversationLog(Base):
    """Individual messages in simulations."""
    __tablename__ = "conversation_logs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_progress_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_progress.id"), index=True, nullable=False)
    scene_id: Mapped[int] = mapped_column(Integer, ForeignKey("simulation_scenes.id"), index=True, nullable=False)
    persona_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("simulation_personas.id"), nullable=True)
    message_type: Mapped[str] = mapped_column(String, nullable=False)  # e.g., "user", "ai_persona", "system"
    sender_name: Mapped[str] = mapped_column(String, nullable=False)
    message_content: Mapped[str] = mapped_column(Text, nullable=False)
    message_order: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ai_model_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    processing_time: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConversationSummaries(Base):
    """LLM-generated summaries of conversations."""
    __tablename__ = "conversation_summaries"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_progress_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_progress.id"), index=True, nullable=False)
    scene_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("simulation_scenes.id"), nullable=True)
    summary_type: Mapped[str] = mapped_column(String, nullable=False)  # e.g., "scene", "scene_transition", "overall"
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    key_points: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    learning_moments: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    insights: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    recommendations: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    summary_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    quality_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

