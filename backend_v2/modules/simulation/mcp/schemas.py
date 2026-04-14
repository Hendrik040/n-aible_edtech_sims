"""Pydantic v2 schemas for MCP extraction tool validation.

These schemas reflect the full JSON structures produced by Claude when
extracting personas, scenes, and learning objectives from a case-study PDF.
They are intentionally separate from the legacy ``backend/`` schemas to
give the v2 architecture a clean slate.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PersonaSchema(BaseModel):
    """A single persona extracted from a case-study PDF."""

    name: str
    role: str
    background: Optional[str] = None
    current_context: Optional[str] = None
    correlation: Optional[str] = None
    personality_traits: Optional[dict[str, int]] = None
    primary_goals: Optional[list[str]] = None
    knowledge_areas: Optional[list[str]] = None
    communication_style: Optional[str] = None
    is_main_character: Optional[bool] = None


class PersonaExtractionResult(BaseModel):
    """Full envelope returned by the persona extraction prompt."""

    title: str
    description: str
    student_role: str
    key_figures: list[PersonaSchema]


class SceneSchema(BaseModel):
    """A single scene extracted from a case-study PDF."""

    title: str
    description: str
    personas_involved: Optional[list[str]] = None
    user_goal: Optional[str] = None
    goal: Optional[str] = None
    success_metric: Optional[str] = None
    sequence_order: int = Field(ge=0)
