"""Project-wide configuration settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration pulled from environment variables."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default_factory=lambda: f"sqlite:///{BASE_DIR / 'app.db'}",
        description="Database connection URL",
    )

    # Security - MUST be set via environment variable
    secret_key: str = Field(
        default="CHANGE_ME_GENERATE_RANDOM_SECRET_KEY_AT_LEAST_32_CHARS",
        description="Secret key for JWT tokens (minimum 32 characters)",
    )

    # Authentication
    access_token_exp_minutes: int = Field(
        default=30,
        ge=1,
        le=1440,
        description="Access token expiration time in minutes",
    )

    # Environment
    environment: str = Field(
        default="development",
        pattern="^(development|production|testing)$",
        description="Application environment",
    )

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Validate secret key strength."""
        if len(v) < 32:
            raise ValueError(
                f"SECRET_KEY must be at least 32 characters long (got {len(v)}). "
                "Set SECRET_KEY in your .env file with a secure random key."
            )
        # Check for common insecure defaults
        insecure_defaults = [
            "super-secret-key",
            "your-secret-key-here",
            "CHANGE_ME_GENERATE_RANDOM_SECRET_KEY",
            "CHANGE_ME_GENERATE_RANDOM_SECRET_KEY_AT_LEAST_32_CHARS",
        ]
        if v in insecure_defaults:
            raise ValueError(
                "SECRET_KEY must be changed from default value. "
                "Generate a secure random key and set it in your .env file:\n"
                "  SECRET_KEY=your-very-long-random-secret-key-at-least-32-characters\n\n"
                "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
            )
        return v

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


__all__ = ["Settings", "get_settings"]
