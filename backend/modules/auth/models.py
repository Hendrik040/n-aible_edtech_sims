"""SQLAlchemy models for authentication.

NOTE: User model is defined in common.db.models to match develop-v2 architecture.
This module re-exports it for convenience.
"""

# Re-export User from common.db.models to maintain backward compatibility
from common.db.models import User

__all__ = ["User"]

