"""Project-wide configuration settings."""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration pulled from environment variables."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        extra="ignore"
    )

    # App Config
    environment: str = "development"
    database_url: str = f"sqlite:///{BASE_DIR / 'app.db'}"
    secret_key: str = "super-secret-key"
    access_token_exp_minutes: int = 30
    
    # OAuth Config
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_redirect_uri: str = "http://localhost:3000/auth/google/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()
