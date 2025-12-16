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

# Backwards compatibility aliases (old names -> new names)
Scenario = Simulation
ScenarioPersona = SimulationPersona
ScenarioScene = SimulationScene
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

__all__ = [
    # Auth
    "User",
    # Publishing
    "Simulation",
    "SimulationPersona",
    "SimulationScene",
    "scene_personas",
    "ScenarioReview",
    "SimulationFile",
    # Publishing (legacy aliases)
    "Scenario",
    "ScenarioPersona",
    "ScenarioScene",
    # Cohorts
    "Cohort",
    "CohortStudent",
    "CohortSimulation",
    "StudentSimulationInstance",
    "GradeHistory",
    "CohortInvitation",
    "CohortInvite",
]
