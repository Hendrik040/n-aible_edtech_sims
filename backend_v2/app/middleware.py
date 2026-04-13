from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from common.config import get_settings

def configure_middleware(app: FastAPI):
    """
    Configure global API middleware.
    Includes CORS, error handling, etc.
    """
    settings = get_settings()
    is_production = settings.environment.lower() in ["production", "prod"]
    
    # CORS Configuration - Security Critical
    # NEVER use "*" with allow_credentials=True in production
    # Parse CORS origins from environment variable (comma-separated)
    if settings.cors_origins:
        # Split by comma and strip whitespace
        origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
    else:
        # Only allow localhost fallback in development
        if is_production:
            raise ValueError(
                "CORS_ORIGINS environment variable must be set in production. "
                "Cannot use default localhost origins for security reasons. "
                "Set CORS_ORIGINS to your production frontend URL(s)"
            )
        # Fallback to localhost for development only
        origins = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    
    # In production, we MUST have specific origins - never allow "*"
    if is_production and not origins:
        raise ValueError(
            "CORS_ORIGINS environment variable must be set in production. "
            "Cannot use wildcard '*' with allow_credentials=True for security reasons."
        )
    
    # Security: Never allow "*" with credentials in production
    if is_production and "*" in origins:
        raise ValueError(
            "Cannot use '*' as CORS origin in production when allow_credentials=True. "
            "This is a security vulnerability. Please set specific origins via CORS_ORIGINS."
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,  # Required for HttpOnly cookies
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "Cookie"],
        expose_headers=["*"]
    )
