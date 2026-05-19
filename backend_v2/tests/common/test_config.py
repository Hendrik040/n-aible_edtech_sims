"""Unit tests for ``common.config.Settings``.

Settings are instantiated directly (not via the ``lru_cache``-backed
``get_settings`` factory) so each test sees a fresh read of the
environment without cross-test caching.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from common.config import Settings


def _clear_ai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop AI-related env vars so defaults are observable.

    Also seeds ``SECRET_KEY`` deterministically because ``Settings`` marks
    it as required; without this, tests would depend on ambient env.
    """
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    for var in (
        "ANTHROPIC_API_KEY",
        "GOOGLE_GENAI_API_KEY",
        "PERSONA_MODEL",
        "GRADING_MODEL",
        "SUMMARIZATION_MODEL",
        "IMAGE_PROVIDER",
        "EMBEDDING_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)


def test_settings_reads_anthropic_api_key_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_ai_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-value")

    settings = Settings()

    assert settings.anthropic_api_key == "sk-ant-test-value"


def test_settings_default_persona_model_is_sonnet_4_6(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_ai_env(monkeypatch)

    settings = Settings()

    assert settings.persona_model == "claude-sonnet-4-6"
    assert settings.grading_model == "claude-haiku-4-5-20251001"
    assert settings.summarization_model == "claude-haiku-4-5-20251001"
    assert settings.image_provider == "gemini"
    assert settings.embedding_model == "text-embedding-3-small"
    assert settings.anthropic_api_key is None
    assert settings.google_genai_api_key is None


def test_settings_rejects_invalid_image_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_ai_env(monkeypatch)
    monkeypatch.setenv("IMAGE_PROVIDER", "stable-diffusion")

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    # Confirm the error is specifically about image_provider, not some
    # unrelated required field, so the test can't pass for the wrong reason.
    assert "image_provider" in str(exc_info.value).lower()


def test_settings_env_override_wins_over_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_ai_env(monkeypatch)
    monkeypatch.setenv("PERSONA_MODEL", "claude-opus-4-6")
    monkeypatch.setenv("GRADING_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("SUMMARIZATION_MODEL", "claude-haiku-3-5")
    monkeypatch.setenv("IMAGE_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-large")
    monkeypatch.setenv("GOOGLE_GENAI_API_KEY", "google-key-from-env")

    settings = Settings()

    assert settings.persona_model == "claude-opus-4-6"
    assert settings.grading_model == "claude-sonnet-4-6"
    assert settings.summarization_model == "claude-haiku-3-5"
    assert settings.image_provider == "openai"
    assert settings.embedding_model == "text-embedding-3-large"
    assert settings.google_genai_api_key == "google-key-from-env"
