"""Simulation-related models for publishing module."""
from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, JSON, Float, Table
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from common.db.base import Base


class Simulation(Base):
    __tablename__ = "simulations"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    unique_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    challenge: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    learning_objectives: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pdf_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    student_role: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pdf_title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pdf_source: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    processing_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_remixes: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String, default="draft")
    is_draft: Mapped[bool] = mapped_column(Boolean, default=True)
    published_version_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("simulations.id"), nullable=True)
    draft_of_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("simulations.id"), nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    clone_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Completion flags
    name_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    description_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    student_role_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    personas_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    scenes_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    images_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    learning_outcomes_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_enhancement_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    grading_config_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Grading config
    grading_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    grading_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Soft delete
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    deletion_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class SimulationPersona(Base):
    __tablename__ = "simulation_personas"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    simulation_id: Mapped[int] = mapped_column(Integer, ForeignKey("simulations.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    background: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Current responsibilities and challenges this persona faces in the case
    current_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Relationship of this persona to the student (protagonist) role
    correlation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Big Five personality model: openness, conscientiousness, extraversion, agreeableness, neuroticism (each 1–10)
    personality_traits: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    primary_goals: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    # Specific facts, data points, and domain knowledge this persona possesses
    knowledge_areas: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    # How this persona communicates: tone, style, register
    communication_style: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Soft delete
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


class SimulationScene(Base):
    __tablename__ = "simulation_scenes"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    simulation_id: Mapped[int] = mapped_column(Integer, ForeignKey("simulations.id"), index=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_goal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scene_order: Mapped[int] = mapped_column(Integer, default=0)
    timeout_turns: Mapped[int] = mapped_column(Integer, default=15)
    success_metric: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    max_attempts: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    success_threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    goal_criteria: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    hint_triggers: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    scene_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    persona_instructions: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    image_prompt: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Soft delete
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


# Association table for many-to-many relationship between scenes and personas
scene_personas = Table(
    "scene_personas",
    Base.metadata,
    Column("scene_id", Integer, ForeignKey("simulation_scenes.id", ondelete="CASCADE"), primary_key=True),
    Column("persona_id", Integer, ForeignKey("simulation_personas.id", ondelete="CASCADE"), primary_key=True),
    Column("involvement_level", String, default="participant"),  # key/participant/mentioned
    Column("created_at", DateTime(timezone=True), server_default=func.now())
)
