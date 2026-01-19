"""Custom exception hierarchy shared across modules.

Exceptions should be raised by services and caught by routers to convert to appropriate HTTP responses.
"""


class DomainError(Exception):
    """Base exception for domain errors."""
    pass


class NotFoundError(DomainError):
    """Raised when a requested resource is not found (maps to HTTP 404)."""
    pass


class ForbiddenError(DomainError):
    """Raised when access to a resource is forbidden (maps to HTTP 403)."""
    pass


class ValidationError(DomainError):
    """Raised when validation fails (maps to HTTP 400)."""
    pass


class UnauthorizedError(DomainError):
    """Raised when authentication is required or failed (maps to HTTP 401)."""
    pass
