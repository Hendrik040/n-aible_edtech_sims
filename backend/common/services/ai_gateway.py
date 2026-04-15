"""
AI Gateway - Unified entry point for all simulation helper services.

This module provides a convenient wrapper that re-exports all simulation_helper services,
allowing for simpler imports throughout the codebase.
"""
# Re-export simulation_helper services
from .simulation_helper.langchain_service import (
    langchain_manager,
    LangChainManager,
    embeddings,
    cache,
    get_langchain_manager,
)
from .simulation_helper.session_manager import (
    session_manager,
    SessionManager,
)
from .simulation_helper.memory_service import (
    memory_service,
    MemoryService,
)
from .simulation_helper.conversation_service import (
    conversation_service,
    ConversationService,
)
from .simulation_helper.scene_memory_service import (
    scene_memory_manager,
    SceneMemoryManager,
)
from .simulation_helper.grading_embedding_service import (
    grading_embedding_service,
    GradingEmbeddingService,
)
from .simulation_helper.grading_vector_store import (
    grading_vector_store,
    GradingVectorStore,
    search_grading_materials_tool,
)
from . import image_service

__all__ = [
    # LangChain Service
    "langchain_manager",
    "LangChainManager",
    "embeddings",
    "cache",
    "get_langchain_manager",
    # Session Manager
    "session_manager",
    "SessionManager",
    # Memory Service
    "memory_service",
    "MemoryService",
    # Conversation Service
    "conversation_service",
    "ConversationService",
    # Scene Memory Service
    "scene_memory_manager",
    "SceneMemoryManager",
    # Grading Embedding Service
    "grading_embedding_service",
    "GradingEmbeddingService",
    # Grading Vector Store
    "grading_vector_store",
    "GradingVectorStore",
    "search_grading_materials_tool",
    # Image Service
    "image_service",
    "get_image_service",
]


def get_langchain_manager() -> LangChainManager:
    """Convenience function to get LangChain manager."""
    return langchain_manager


def get_session_manager() -> SessionManager:
    """Convenience function to get session manager."""
    return session_manager


def get_memory_service() -> MemoryService:
    """Convenience function to get memory service."""
    return memory_service


def get_conversation_service() -> ConversationService:
    """Convenience function to get conversation service."""
    return conversation_service


def get_scene_memory_manager() -> SceneMemoryManager:
    """Convenience function to get scene memory manager."""
    return scene_memory_manager


def get_image_service():
    """Convenience function to get image service module."""
    return image_service
