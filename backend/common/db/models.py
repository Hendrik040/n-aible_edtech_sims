"""
Database Models

This file re-exports models from the new modular structure.
Models are organized in common/db/models/<module>/ directories.

For new code, import directly from the module-specific locations:
- from common.db.models.auth.user import User
- from common.db.models.publishing.simulation import Simulation
"""

# Re-export from new modular structure
from common.db.models.auth.user import User
from common.db.models.publishing.simulation import (
    Simulation,
    SimulationPersona,
    SimulationScene,
    scene_personas,
)
from common.db.models.publishing.review import ScenarioReview
from common.db.models.publishing.file import SimulationFile

__all__ = [
    "User",
    "Simulation",
    "SimulationPersona",
    "SimulationScene",
    "scene_personas",
    "ScenarioReview",
    "SimulationFile",
]


