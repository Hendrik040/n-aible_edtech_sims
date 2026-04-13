"""
Database Models

This module re-exports all models from their module-specific subdirectories.
Models are organized by feature module.
"""

# Import from module-specific subdirectories
from .auth.user import User
from .auth.password_reset_token import PasswordResetToken
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
from .notifications import Notification

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
    PromptTrace,
)

# Admin-only models
from .admin import RalphPipelineEvent

# Backwards compatibility aliases (old names -> new names)
Scenario = Simulation
ScenarioPersona = SimulationPersona
ScenarioScene = SimulationScene
ScenarioReview = SimulationReview

__all__ = [
    # Auth models
    "User",
    "PasswordResetToken",
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
    # Notification models
    "Notification",
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
    "PromptTrace",
    # Admin-only models
    "RalphPipelineEvent",
    # Aliases for backward compatibility
    "Scenario",
    "ScenarioScene",
    "ScenarioPersona",
    "ScenarioReview",
]
