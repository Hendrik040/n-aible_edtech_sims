"""Project-wide configuration settings."""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration pulled from environment variables."""

    database_url: str = f"sqlite:///{BASE_DIR / 'app.db'}"
    secret_key: str = "super-secret-key"
    access_token_exp_minutes: int = 30

    class Config:
        env_file = BASE_DIR / ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
