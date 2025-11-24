"""
Centralized application configuration using Pydantic settings.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional
import os

from pydantic_settings import BaseSettings


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application-wide configuration loaded from environment variables."""

    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://localhost:5432/ai_agent_platform"
    )
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    serper_api_key: str = os.getenv("SERPER_API_KEY", "")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    secret_key: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    environment: str = os.getenv("ENVIRONMENT", "development")
    cors_origins: str = os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
    )
    llamaparse_api_key: Optional[str] = os.getenv("LLAMAPARSE_API_KEY")
    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
    freepik_api_key: Optional[str] = os.getenv("FREEPIK_API_KEY")

    # AWS / Wasabi storage
    aws_access_key_id: Optional[str] = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_bucket_name: Optional[str] = os.getenv("AWS_BUCKET_NAME")
    aws_region: Optional[str] = os.getenv("AWS_REGION", "us-east-1")
    aws_public_read: bool = os.getenv("AWS_PUBLIC_READ", "false").lower() == "true"

    wasabi_access_key_id: Optional[str] = os.getenv("WASABI_ACCESS_KEY_ID")
    wasabi_secret_access_key: Optional[str] = os.getenv("WASABI_SECRET_ACCESS_KEY")
    wasabi_bucket_name: Optional[str] = os.getenv("WASABI_BUCKET_NAME")
    wasabi_endpoint_url: Optional[str] = os.getenv("WASABI_ENDPOINT_URL")
    wasabi_public_read: bool = os.getenv("WASABI_PUBLIC_READ", "false").lower() == "true"

    backend_url: str = os.getenv("BACKEND_URL", "http://localhost:8001")

    # OAuth
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri: str = os.getenv("GOOGLE_REDIRECT_URI", "")

    # Vector DB
    use_pgvector: bool = os.getenv("USE_PGVECTOR", "true").lower() == "true"

    class Config:
        env_file = PROJECT_ROOT / ".env"
        extra = "ignore"

    @property
    def s3_access_key_id(self) -> Optional[str]:
        return self.aws_access_key_id or self.wasabi_access_key_id

    @property
    def s3_secret_access_key(self) -> Optional[str]:
        return self.aws_secret_access_key or self.wasabi_secret_access_key

    @property
    def s3_bucket_name(self) -> Optional[str]:
        return self.aws_bucket_name or self.wasabi_bucket_name

    @property
    def s3_endpoint_url(self) -> Optional[str]:
        if self.aws_access_key_id:
            return None
        return self.wasabi_endpoint_url.rstrip("/") if self.wasabi_endpoint_url else None

    @property
    def s3_public_read(self) -> bool:
        return self.aws_public_read or self.wasabi_public_read

    @property
    def s3_region(self) -> str:
        return self.aws_region if self.aws_access_key_id else "us-east-1"

    @property
    def is_aws(self) -> bool:
        return bool(self.aws_access_key_id)


def validate_settings(settings: Settings) -> None:
    """Ensure critical configuration is present in production."""

    if settings.environment != "production":
        return

    required_pairs = {
        "GOOGLE_CLIENT_ID": settings.google_client_id,
        "GOOGLE_CLIENT_SECRET": settings.google_client_secret,
        "GOOGLE_REDIRECT_URI": settings.google_redirect_uri,
        "AWS/WASABI ACCESS KEY": settings.s3_access_key_id,
        "AWS/WASABI SECRET KEY": settings.s3_secret_access_key,
        "AWS/WASABI BUCKET NAME": settings.s3_bucket_name,
    }

    for name, value in required_pairs.items():
        if not value or not str(value).strip():
            raise RuntimeError(f"{name} is required in production environment")

    if not settings.is_aws:
        if not settings.s3_endpoint_url or not settings.s3_endpoint_url.strip():
            raise RuntimeError(
                "WASABI_ENDPOINT_URL is required in production when using Wasabi"
            )


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance."""

    return Settings()

