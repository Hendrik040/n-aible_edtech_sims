"""
Shared exception hierarchy for domain and infrastructure errors.
"""


class DomainError(Exception):
    """Base exception for domain/business logic failures."""


class NotFoundError(DomainError):
    """Raised when an entity cannot be located."""


class ValidationError(DomainError):
    """Raised when incoming data fails validation."""


class PermissionError(DomainError):
    """Raised when caller lacks required permissions."""


__all__ = ["DomainError", "NotFoundError", "PermissionError", "ValidationError"]

