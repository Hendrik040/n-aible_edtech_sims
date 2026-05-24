"""Agent session and memory models for simulation runtime."""
from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy import Integer, String, ForeignKey, Text, JSON, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from common.db.base import Base


class AgentSessions(Base):
    """Active agent sessions."""
    __tablename__ = "agent_sessions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    user_progress_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_progress.id"), index=True, nullable=False)
    persona_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("simulation_personas.id"), nullable=True)
    agent_type: Mapped[str] = mapped_column(String, nullable=False)  # e.g., "persona", "grading", "summarization"
    agent_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    session_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    session_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    session_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class SessionMemory(Base):
    """Agent memory storage (used by session_manager and memory_service)."""
    __tablename__ = "session_memory"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    memory_type: Mapped[str] = mapped_column(String, nullable=False)  # e.g., "conversation", "shared_insight", "learning_moment"
    memory_content: Mapped[str] = mapped_column(Text, nullable=False)
    user_progress_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_progress.id"), index=True, nullable=False)
    scene_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("simulation_scenes.id"), nullable=True)
    related_persona_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("simulation_personas.id"), nullable=True)
    importance_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    memory_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_accessed: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class VectorEmbeddings(Base):
    """Vector embeddings storage (if used separately from PGVector)."""
    __tablename__ = "vector_embeddings"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)  # e.g., "memory", "conversation", "scene"
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    embedding_vector: Mapped[Optional[List[float]]] = mapped_column(JSON, nullable=True)  # Store as JSON array for compatibility
    embedding_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    embedding_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)  # Renamed from 'metadata' (reserved in SQLAlchemy)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

