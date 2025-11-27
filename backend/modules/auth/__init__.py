"""Auth module exports."""

from modules.auth import models
from modules.auth.dependencies import (
    get_current_user,
    require_admin,
    require_professor,
    require_student,
)
from modules.auth.router import router

__all__ = [
    "models",
    "router",
    "get_current_user",
    "require_admin",
    "require_student",
    "require_professor",
]
