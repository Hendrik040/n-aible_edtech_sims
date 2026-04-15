"""
Tests for the core image service provider switching.

Covers Gemini path, OpenAI fallback, graceful degradation, and missing keys.
"""

import pytest
from unittest.mock import AsyncMock, patch

from common.config import Settings


def _settings(**overrides):
    defaults = {
        "image_provider": "gemini",
        "gemini_api_key": None,
        "openai_api_key": None,
    }
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.mark.asyncio
async def test_gemini_path_used_when_configured():
    """Gemini is used when IMAGE_PROVIDER=gemini and key is present."""
    gemini_mock = AsyncMock(return_value="https://gemini.example.com/img.png")
    openai_mock = AsyncMock(return_value="https://oai.example.com/img.png")

    with (
        patch("common.services.image_service._generate_with_gemini", gemini_mock),
        patch("common.services.image_service._generate_with_openai", openai_mock),
        patch(
            "common.services.image_service.get_settings",
            return_value=_settings(
                image_provider="gemini", gemini_api_key="gk"
            ),
        ),
    ):
        from common.services.image_service import generate_image

        result = await generate_image("test prompt")

    assert result == "https://gemini.example.com/img.png"
    gemini_mock.assert_called_once_with("test prompt", "gk")
    openai_mock.assert_not_called()


@pytest.mark.asyncio
async def test_openai_fallback_when_gemini_key_missing():
    """OpenAI is used when gemini_api_key is missing."""
    gemini_mock = AsyncMock()
    openai_mock = AsyncMock(return_value="https://oai.example.com/img.png")

    with (
        patch("common.services.image_service._generate_with_gemini", gemini_mock),
        patch("common.services.image_service._generate_with_openai", openai_mock),
        patch(
            "common.services.image_service.get_settings",
            return_value=_settings(
                image_provider="gemini",
                gemini_api_key=None,
                openai_api_key="ok",
            ),
        ),
    ):
        from common.services.image_service import generate_image

        result = await generate_image("test prompt")

    assert result == "https://oai.example.com/img.png"
    gemini_mock.assert_not_called()
    openai_mock.assert_called_once()


@pytest.mark.asyncio
async def test_openai_used_when_provider_is_openai():
    """OpenAI is used directly when IMAGE_PROVIDER=openai."""
    gemini_mock = AsyncMock()
    openai_mock = AsyncMock(return_value="https://oai.example.com/img.png")

    with (
        patch("common.services.image_service._generate_with_gemini", gemini_mock),
        patch("common.services.image_service._generate_with_openai", openai_mock),
        patch(
            "common.services.image_service.get_settings",
            return_value=_settings(
                image_provider="openai",
                gemini_api_key="gk",
                openai_api_key="ok",
            ),
        ),
    ):
        from common.services.image_service import generate_image

        result = await generate_image("test prompt")

    assert result == "https://oai.example.com/img.png"
    gemini_mock.assert_not_called()
    openai_mock.assert_called_once()


@pytest.mark.asyncio
async def test_openai_fallback_when_gemini_fails():
    """Falls back to OpenAI when Gemini returns None."""
    gemini_mock = AsyncMock(return_value=None)
    openai_mock = AsyncMock(return_value="https://oai.example.com/img.png")

    with (
        patch("common.services.image_service._generate_with_gemini", gemini_mock),
        patch("common.services.image_service._generate_with_openai", openai_mock),
        patch(
            "common.services.image_service.get_settings",
            return_value=_settings(
                image_provider="gemini",
                gemini_api_key="gk",
                openai_api_key="ok",
            ),
        ),
    ):
        from common.services.image_service import generate_image

        result = await generate_image("test prompt")

    assert result == "https://oai.example.com/img.png"
    gemini_mock.assert_called_once()
    openai_mock.assert_called_once()


@pytest.mark.asyncio
async def test_graceful_degradation_both_fail():
    """Returns empty string when both providers fail."""
    gemini_mock = AsyncMock(return_value=None)
    openai_mock = AsyncMock(return_value=None)

    with (
        patch("common.services.image_service._generate_with_gemini", gemini_mock),
        patch("common.services.image_service._generate_with_openai", openai_mock),
        patch(
            "common.services.image_service.get_settings",
            return_value=_settings(
                image_provider="gemini",
                gemini_api_key="gk",
                openai_api_key="ok",
            ),
        ),
    ):
        from common.services.image_service import generate_image

        result = await generate_image("test prompt")

    assert result == ""


@pytest.mark.asyncio
async def test_missing_api_keys_returns_empty():
    """Returns empty string without exceptions when no API keys configured."""
    with patch(
        "common.services.image_service.get_settings",
        return_value=_settings(
            image_provider="gemini",
            gemini_api_key=None,
            openai_api_key=None,
        ),
    ):
        from common.services.image_service import generate_image

        result = await generate_image("test prompt")

    assert result == ""
