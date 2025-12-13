"""
Database Models

This module re-exports all models from their module-specific subdirectories.
Models are organized by feature module.
"""

# Import from module-specific subdirectories
from .auth.user import User
from .publishing.simulation import (
    Simulation,
    SimulationPersona,
    SimulationScene,
    scene_personas,
)
from .publishing.review import ScenarioReview
from .publishing.file import SimulationFile

# Simulation runtime models
from .simulation import (
    UserProgress,
    StudentSimulationInstance,
    SceneProgress,
    ConversationLog,
    ConversationSummaries,
    AgentSessions,
    SessionMemory,
    VectorEmbeddings,
    GradingMaterial,
    GradingMaterialChunk,
)

# Aliases for backward compatibility (Scenario -> Simulation)
Scenario = Simulation
ScenarioScene = SimulationScene
ScenarioPersona = SimulationPersona

__all__ = [
    # Auth models
    "User",
    # Publishing models
    "Simulation",
    "SimulationPersona",
    "SimulationScene",
    "scene_personas",
    "ScenarioReview",
    "SimulationFile",
    # Simulation runtime models
    "UserProgress",
    "StudentSimulationInstance",
    "SceneProgress",
    "ConversationLog",
    "ConversationSummaries",
    "AgentSessions",
    "SessionMemory",
    "VectorEmbeddings",
    "GradingMaterial",
    "GradingMaterialChunk",
    # Aliases for backward compatibility
    "Scenario",
    "ScenarioScene",
    "ScenarioPersona",
]
