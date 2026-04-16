"""
Tests for the publishing image generation module.

Covers scene image generation, batch processing, and image_service delegation.
"""

import sys
import types

import pytest
from unittest.mock import AsyncMock, patch

# Pre-register a stub for modules.publishing to avoid the circular-import
# chain triggered by its __init__.py (router → app.dependencies → auth → …).
# The actual image_generation submodule only depends on common.services.
if "modules.publishing" not in sys.modules:
    import os as _os
    _stub = types.ModuleType("modules.publishing")
    _stub.__path__ = [_os.path.join(_os.path.dirname(__file__), "..", "..", "..", "modules", "publishing")]
    _stub.__package__ = "modules.publishing"
    sys.modules["modules.publishing"] = _stub

from modules.publishing.image_generation import (
    generate_scene_image,
    generate_scenes_with_images,
)


@pytest.mark.asyncio
async def test_scene_image_calls_image_service():
    """generate_scene_image delegates to image_service.generate_image with correct prompt."""
    mock_generate = AsyncMock(return_value="https://example.com/scene.png")

    with patch("common.services.image_service.generate_image", mock_generate):
        result = await generate_scene_image(
            scene_description="A board meeting about quarterly results",
            scene_title="Board Meeting",
        )

    assert result == "https://example.com/scene.png"
    mock_generate.assert_called_once()
    call_args = mock_generate.call_args
    assert "Board Meeting" in call_args[0][0]
    assert call_args[1]["size"] == "1024x1024"
    assert call_args[1]["quality"] == "standard"


@pytest.mark.asyncio
async def test_image_provider_env_flag_respected():
    """IMAGE_PROVIDER setting controls which provider is attempted first."""
    from common.config import Settings

    openai_mock = AsyncMock(return_value="https://oai.example.com/img.png")
    gemini_mock = AsyncMock(return_value="https://gemini.example.com/img.png")

    # Test openai provider path
    with (
        patch("common.services.image_service._generate_with_openai", openai_mock),
        patch("common.services.image_service._generate_with_gemini", gemini_mock),
        patch(
            "common.services.image_service.get_settings",
            return_value=Settings(
                image_provider="openai",
                openai_api_key="test-key",
                gemini_api_key=None,
            ),
        ),
    ):
        from common.services.image_service import generate_image

        result = await generate_image("test prompt")

    assert result == "https://oai.example.com/img.png"
    gemini_mock.assert_not_called()
    openai_mock.assert_called_once()

    # Test gemini provider path
    openai_mock.reset_mock()
    gemini_mock.reset_mock()

    with (
        patch("common.services.image_service._generate_with_openai", openai_mock),
        patch("common.services.image_service._generate_with_gemini", gemini_mock),
        patch(
            "common.services.image_service.get_settings",
            return_value=Settings(
                image_provider="gemini",
                openai_api_key="test-key",
                gemini_api_key="gemini-key",
            ),
        ),
    ):
        from common.services.image_service import generate_image

        result = await generate_image("test prompt")

    assert result == "https://gemini.example.com/img.png"
    gemini_mock.assert_called_once()
    openai_mock.assert_not_called()


@pytest.mark.asyncio
async def test_generate_scenes_with_images_empty_list():
    """Empty scene list returns immediately."""
    result = await generate_scenes_with_images([], None, None)
    assert result == []


@pytest.mark.asyncio
async def test_generate_scenes_with_images_invalid_dicts():
    """Invalid scene dicts get empty image_url."""
    mock_generate = AsyncMock(return_value="https://example.com/img.png")

    with patch("common.services.image_service.generate_image", mock_generate):
        scenes = [
            {"description": "desc", "title": "title"},
            {"invalid": "no title or description"},
            {"description": "desc2", "title": "title2"},
        ]
        result = await generate_scenes_with_images(scenes, None, None)

    assert result[0]["image_url"] == "https://example.com/img.png"
    assert result[1]["image_url"] == ""
    assert result[2]["image_url"] == "https://example.com/img.png"


@pytest.mark.asyncio
async def test_generate_scenes_with_images_parallel():
    """Valid scenes get image URLs via parallel generation."""
    mock_generate = AsyncMock(return_value="https://example.com/generated.png")

    with patch("common.services.image_service.generate_image", mock_generate):
        scenes = [
            {"description": "Scene one", "title": "Intro", "id": 1},
            {"description": "Scene two", "title": "Climax", "scene_id": 2},
        ]
        result = await generate_scenes_with_images(scenes, "session-1", 42)

    assert len(result) == 2
    assert all(s["image_url"] == "https://example.com/generated.png" for s in result)
    assert mock_generate.call_count == 2
