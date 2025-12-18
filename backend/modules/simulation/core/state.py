"""Simulation state management."""

from typing import Dict, Any
from dataclasses import dataclass, field


@dataclass
class SimulationState:
    """Tracks the current state of the simulation."""
    current_scene_id: str = ""
    current_scene_index: int = 0
    turn_count: int = 0
    max_turns_reached: bool = False
    scene_completed: bool = False
    simulation_started: bool = False
    user_ready: bool = False
    
    # LangChain-specific state (optional)
    session_id: str = ""
    agent_sessions: Dict[str, str] = field(default_factory=dict)  # agent_type -> session_id
    scene_memory_initialized: bool = False
    context_retrieved: bool = False
    langchain_enabled: bool = False
    
    # Dynamic state for objectives
    state_variables: Dict[str, Any] = field(default_factory=dict)
