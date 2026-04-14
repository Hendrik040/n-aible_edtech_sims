"""Temporary Protocol stub for SimulationPersona.

Defines the structural interface that build_persona_system_prompt expects.
Will be replaced by the real Pydantic model once phase-1.4 lands.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class SimulationPersonaProtocol(Protocol):
    name: str
    role: str
    background: Optional[str]
    current_context: Optional[str]
    correlation: Optional[str]
    personality_traits: Optional[Dict[str, int]]
    primary_goals: Optional[List[str]]
    knowledge_areas: Optional[List[str]]
    communication_style: Optional[str]
    system_prompt: Optional[str]
