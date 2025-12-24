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
    secret_key: str = "super-secret-key"
    access_token_exp_minutes: int = 360
    
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
    
    # AWS S3 Configuration
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_bucket_name: Optional[str] = None
    aws_region: str = "us-east-1"
    aws_public_read: bool = True

    # Redis Configuration
    redis_url: Optional[str] = "redis://localhost:6379"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


__all__ = ["Settings", "get_settings"]
