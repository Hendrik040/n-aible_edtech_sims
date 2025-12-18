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
from .publishing.review import SimulationReview
from .publishing.file import SimulationFile
from .cohorts import (
    Cohort,
    CohortStudent,
    CohortSimulation,
    StudentSimulationInstance,
    GradeHistory,
    CohortInvitation,
    CohortInvite,
)

# Simulation runtime models
from .simulation import (
    UserProgress,
    SceneProgress,
    ConversationLog,
    ConversationSummaries,
    AgentSessions,
    SessionMemory,
    VectorEmbeddings,
    GradingMaterial,
    GradingMaterialChunk,
)

# Backwards compatibility aliases (old names -> new names)
Scenario = Simulation
ScenarioPersona = SimulationPersona
ScenarioScene = SimulationScene
ScenarioReview = SimulationReview

__all__ = [
    # Auth models
    "User",
    # Publishing models
    "Simulation",
    "SimulationPersona",
    "SimulationScene",
    "scene_personas",
    "SimulationReview",
    "SimulationFile",
    # Cohort models
    "Cohort",
    "CohortStudent",
    "CohortSimulation",
    "StudentSimulationInstance",
    "GradeHistory",
    "CohortInvitation",
    "CohortInvite",
    # Simulation runtime models
    "UserProgress",
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
    "ScenarioReview",
]
