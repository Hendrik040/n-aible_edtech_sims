"""Project-wide configuration settings."""

from functools import lru_cache
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
# Backend directory (where .env might be located)
BACKEND_DIR = Path(__file__).resolve().parents[1]

# Determine which .env file to use (prefer backend/.env, fallback to project root/.env)
# Railway doesn't use .env files - it uses environment variables directly
# But for local development, we check both locations
# Pydantic Settings reads env files in order, so we'll check backend first
_env_files = []
if (BACKEND_DIR / ".env").exists():
    _env_files.append(BACKEND_DIR / ".env")
if (BASE_DIR / ".env").exists():
    _env_files.append(BASE_DIR / ".env")


class Settings(BaseSettings):
    """Runtime configuration pulled from environment variables."""

    model_config = SettingsConfigDict(
        env_file=[str(f) for f in _env_files] if _env_files else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App Config
    environment: str = "development"
    # Railway provides DATABASE_URL automatically - Pydantic reads it case-insensitively
    # Default to SQLite for local development only
    database_url: str = f"sqlite:///{BASE_DIR / 'app.db'}"
    secret_key: str
    access_token_exp_minutes: int = 1440  # 24 hours
    
    # CORS Config
    # Default to None - must be set via CORS_ORIGINS environment variable
    # In development, can be set in .env file or defaults to localhost
    cors_origins: Optional[str] = None
    frontend_url: str = "http://localhost:3000"
    
    # OAuth Config
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_redirect_uri: str = "http://localhost:3001/auth/google/callback"
    
    # PDF Processing Config
    llamaparse_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    freepik_api_key: Optional[str] = None

    # Image generation (see common/services/image_service.py)
    image_provider: str = "gemini"
    google_genai_api_key: Optional[str] = None
    
    # AWS S3 Configuration
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_bucket_name: Optional[str] = None
    aws_region: str = "us-east-1"
    aws_public_read: bool = True

    # Redis Configuration
    redis_url: Optional[str] = "redis://localhost:6379"

    # Daytona Sandbox Configuration
    daytona_api_key: Optional[str] = None
    daytona_api_url: Optional[str] = None
    daytona_target: Optional[str] = "us"

    # SMTP / Email Configuration (used for password reset emails, etc.)
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    from_email: Optional[str] = None
    from_name: str = "n-aible"

    @property
    def worker_id(self) -> str:
        """
        Get unique worker ID for this instance.
        
        Railway automatically provides RAILWAY_REPLICA_ID for each replica.
        See: https://docs.railway.com/guides/optimize-performance#replica-id-environment-variable
        
        Priority: RAILWAY_REPLICA_ID > HOSTNAME > "local" (static fallback for local dev)
        
        Note: Using static "local" instead of random UUID because:
        - Local dev only has one replica anyway
        - Static ID survives server restarts without orphaning Redis keys
        - Simpler debugging with predictable worker ID
        """
        import os
        return (
            os.getenv("RAILWAY_REPLICA_ID") or
            os.getenv("HOSTNAME") or
            "local"
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


__all__ = ["Settings", "get_settings"]
