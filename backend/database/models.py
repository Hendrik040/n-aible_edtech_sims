"""
Legacy compatibility layer for code that still imports from `database.models`.

All ORM classes now live alongside their owning modules or in `common.db.models`.
New code should import from those locations directly.
"""

from common.db.models.cache import CacheEntries
from common.db.models.notifications import EmailQueue, Notification
from common.db.models.user import User
from modules.professor.schemas.models import (
    Cohort,
    CohortInvitation,
    CohortInvite,
    CohortSimulation,
    CohortStudent,
    ProfessorStudentMessage,
)
from modules.simulation.schemas.models import (
    AgentSessions,
    ConversationLog,
    ConversationSummaries,
    GradeHistory,
    GradingMaterial,
    GradingMaterialChunk,
    Scenario,
    ScenarioFile,
    ScenarioPersona,
    ScenarioReview,
    ScenarioScene,
    SceneProgress,
    SessionMemory,
    StudentSimulationInstance,
    UserProgress,
    VectorEmbeddings,
    generate_cohort_id,
    get_vector_column_type,
    scene_personas,
)

__all__ = [
    "AgentSessions",
    "CacheEntries",
    "Cohort",
    "CohortInvitation",
    "CohortInvite",
    "CohortSimulation",
    "CohortStudent",
    "ConversationLog",
    "ConversationSummaries",
    "EmailQueue",
    "GradeHistory",
    "GradingMaterial",
    "GradingMaterialChunk",
    "Notification",
    "ProfessorStudentMessage",
    "Scenario",
    "ScenarioFile",
    "ScenarioPersona",
    "ScenarioReview",
    "ScenarioScene",
    "SceneProgress",
    "SessionMemory",
    "StudentSimulationInstance",
    "User",
    "UserProgress",
    "VectorEmbeddings",
    "generate_cohort_id",
    "get_vector_column_type",
    "scene_personas",
]

