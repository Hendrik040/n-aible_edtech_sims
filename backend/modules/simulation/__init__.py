"""
Simulation Module.

Main module for simulation operations including orchestration, chat handling, and progress tracking.
"""

from .service import SimulationService
from .core import (
    SimulationState,
    ChatOrchestrator,
    OrchestratorManager,
    SceneProgressionHandler
)
from .handlers import ChatHandler
from .repository import SimulationRepository
from .services import (
    GradingService,
    ProgressService,
    LifecycleService
)

__all__ = [
    # Main service
    "SimulationService",
    # Core orchestration
    "SimulationState",
    "ChatOrchestrator",
    "OrchestratorManager",
    "SceneProgressionHandler",
    # Handlers
    "ChatHandler",
    # Repository
    "SimulationRepository",
    # Specialized services
    "GradingService",
    "ProgressService",
    "LifecycleService",
]
