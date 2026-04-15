"""
Tests for the simulation avatars module.

Covers persona avatar generation, batch processing, and backwards-compat keys.
"""

import pytest
from unittest.mock import AsyncMock, patch

from modules.simulation.avatars import (
    generate_persona_avatar,
    generate_personas_with_avatars,
)


@pytest.mark.asyncio
async def test_persona_avatar_calls_image_service():
    """generate_persona_avatar delegates to image_service.generate_image with correct prompt."""
    mock_generate = AsyncMock(return_value="https://example.com/avatar.png")

    with patch("common.services.image_service.generate_image", mock_generate):
        result = await generate_persona_avatar(
            persona_name="Jane Doe",
            persona_role="CEO",
            background="Tech industry veteran",
        )

    assert result == "https://example.com/avatar.png"
    mock_generate.assert_called_once()
    call_args = mock_generate.call_args
    prompt = call_args[0][0]
    assert "Jane Doe" in prompt
    assert "CEO" in prompt
    assert "Tech industry veteran" in prompt
    assert call_args[1]["size"] == "1024x1024"
    assert call_args[1]["quality"] == "standard"


@pytest.mark.asyncio
async def test_generate_personas_with_avatars_empty_list():
    """Empty persona list returns immediately."""
    result = await generate_personas_with_avatars([])
    assert result == []


@pytest.mark.asyncio
async def test_generate_personas_with_avatars_invalid_dicts():
    """Invalid persona dicts get empty image_url."""
    mock_generate = AsyncMock(return_value="https://example.com/avatar.png")

    with patch("common.services.image_service.generate_image", mock_generate):
        personas = [
            {"name": "Alice", "role": "CFO"},
            {"invalid": "no name or role"},
            {"name": "Bob", "role": "CTO", "background": "Engineering"},
        ]
        result = await generate_personas_with_avatars(personas)

    assert result[0]["image_url"] == "https://example.com/avatar.png"
    assert result[1]["image_url"] == ""
    assert result[2]["image_url"] == "https://example.com/avatar.png"


@pytest.mark.asyncio
async def test_generate_personas_with_avatars_parallel():
    """Valid personas get avatar URLs via parallel generation."""
    mock_generate = AsyncMock(return_value="https://example.com/avatar.png")

    with patch("common.services.image_service.generate_image", mock_generate):
        personas = [
            {"name": "Alice", "role": "CFO", "id": 1},
            {"name": "Bob", "role": "CTO", "persona_id": 2},
        ]
        result = await generate_personas_with_avatars(personas)

    assert len(result) == 2
    assert all(p["image_url"] == "https://example.com/avatar.png" for p in result)
    assert mock_generate.call_count == 2


@pytest.mark.asyncio
async def test_generate_personas_with_avatars_sets_both_url_keys():
    """Both image_url and avatar_url are set for backwards compatibility."""
    mock_generate = AsyncMock(return_value="https://example.com/avatar.png")

    with patch("common.services.image_service.generate_image", mock_generate):
        personas = [{"name": "Alice", "role": "CFO"}]
        result = await generate_personas_with_avatars(personas)

    assert result[0]["image_url"] == "https://example.com/avatar.png"
    assert result[0]["avatar_url"] == "https://example.com/avatar.png"
