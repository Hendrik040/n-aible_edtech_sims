"""
User Behavior Classes for Load Testing

Each class represents a type of user with specific behavior patterns.
"""
from .base import BaseLoadTestUser
from .chat_user import ChatSimulationUser, STUDENT_MESSAGES

__all__ = ["BaseLoadTestUser", "ChatSimulationUser", "STUDENT_MESSAGES"]
