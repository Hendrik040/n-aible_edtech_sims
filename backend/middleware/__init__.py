"""
Middleware package for request/response processing
"""

from .role_auth import (
    require_role,
    require_professor,
    require_student,
    require_admin_or_professor,
    require_admin,
    get_user_role,
    is_professor,
    is_student,
    is_admin,
    can_access_cohort,
    require_cohort_access,
    require_ownership_or_admin
)

__all__ = [
    "require_role",
    "require_professor", 
    "require_student",
    "require_admin_or_professor",
    "require_admin",
    "get_user_role",
    "is_professor",
    "is_student", 
    "is_admin",
    "can_access_cohort",
    "require_cohort_access",
    "require_ownership_or_admin"
]

