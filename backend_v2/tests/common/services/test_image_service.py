"""Unit tests for ``common.services.image_service``.

All provider SDKs are mocked. No real network calls are made.
"""
from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from common.services import image_service
from common.services.image_service import (
    GeminiImageProvider,
    OpenAIImageProvider,
    generate_image,
)


def _fake_settings(
    *,
    provider: str = "gemini",
    gemini_key: str | None = "gemini-key",
    openai_key: str | None = "openai-key",
) -> SimpleNamespace:
    return SimpleNamespace(
        image_provider=provider,
        google_genai_api_key=gemini_key,
        openai_api_key=openai_key,
    )


def _gemini_response(payload: bytes) -> MagicMock:
    """Build a mock ``generate_content`` response carrying ``payload`` as image bytes."""
    inline = MagicMock()
    inline.data = payload
    part = MagicMock()
    part.inline_data = inline
    content = MagicMock()
    content.parts = [part]
    candidate = MagicMock()
    candidate.content = content
    response = MagicMock()
    response.candidates = [candidate]
    return response


def _openai_response(payload: bytes) -> MagicMock:
    item = MagicMock()
    item.b64_json = base64.b64encode(payload).decode("ascii")
    response = MagicMock()
    response.data = [item]
    return response


@pytest.mark.asyncio
async def test_generate_image_uses_gemini_by_default() -> None:
    expected = b"gemini-image-bytes"
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = _gemini_response(expected)

    with patch.object(image_service, "get_settings", return_value=_fake_settings()), \
         patch("google.genai.Client", return_value=fake_client) as client_cls:
        result = await generate_image("draw a cat")

    assert result == expected
    client_cls.assert_called_once_with(api_key="gemini-key")
    fake_client.models.generate_content.assert_called_once()
    call_kwargs = fake_client.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-2.5-flash-image"
    # Sizing is enforced via image_config.aspect_ratio, not prompt injection,
    # so the prompt must be forwarded verbatim.
    assert call_kwargs["contents"] == ["draw a cat"]
    assert call_kwargs["config"].image_config.aspect_ratio == "1:1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "size,expected_ratio",
    [
        ("1024x1024", "1:1"),
        ("1024x1536", "2:3"),
        ("1536x1024", "3:2"),
        ("1024x1792", "9:16"),
        ("1792x1024", "16:9"),
        ("nonsense", "1:1"),
    ],
)
async def test_gemini_provider_maps_size_to_aspect_ratio(
    size: str, expected_ratio: str
) -> None:
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = _gemini_response(b"x")

    with patch("google.genai.Client", return_value=fake_client):
        provider = GeminiImageProvider(api_key="k")
        await provider.generate("prompt", size=size)

    config = fake_client.models.generate_content.call_args.kwargs["config"]
    assert config.image_config.aspect_ratio == expected_ratio


@pytest.mark.asyncio
async def test_generate_image_falls_back_to_openai_when_configured() -> None:
    expected = b"openai-image-bytes"
    fake_client = MagicMock()
    fake_client.images.generate.return_value = _openai_response(expected)
    settings = _fake_settings(provider="openai")

    with patch.object(image_service, "get_settings", return_value=settings), \
         patch("openai.OpenAI", return_value=fake_client) as client_cls:
        result = await generate_image("draw a dog")

    assert result == expected
    client_cls.assert_called_once_with(api_key="openai-key")
    fake_client.images.generate.assert_called_once()
    call_kwargs = fake_client.images.generate.call_args.kwargs
    assert call_kwargs["prompt"] == "draw a dog"
    assert call_kwargs["response_format"] == "b64_json"
    assert call_kwargs["n"] == 1


@pytest.mark.asyncio
async def test_generate_image_raises_on_provider_misconfiguration() -> None:
    settings = _fake_settings(provider="wat")

    with patch.object(image_service, "get_settings", return_value=settings):
        with pytest.raises(ValueError, match="Unknown IMAGE_PROVIDER"):
            await generate_image("anything")


@pytest.mark.asyncio
async def test_generate_image_passes_size_to_provider() -> None:
    fake_client = MagicMock()
    fake_client.images.generate.return_value = _openai_response(b"x")
    settings = _fake_settings(provider="openai")

    with patch.object(image_service, "get_settings", return_value=settings), \
         patch("openai.OpenAI", return_value=fake_client):
        await generate_image("prompt", size="1024x1792")

    call_kwargs = fake_client.images.generate.call_args.kwargs
    assert call_kwargs["size"] == "1024x1792"


@pytest.mark.asyncio
async def test_generate_image_raises_when_api_key_missing() -> None:
    settings = _fake_settings(provider="gemini", gemini_key=None)

    with patch.object(image_service, "get_settings", return_value=settings):
        with pytest.raises(ValueError, match="GOOGLE_GENAI_API_KEY"):
            await generate_image("anything")

    settings = _fake_settings(provider="openai", openai_key=None)
    with patch.object(image_service, "get_settings", return_value=settings):
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            await generate_image("anything")


@pytest.mark.asyncio
async def test_openai_provider_clamps_unsupported_size() -> None:
    fake_client = MagicMock()
    fake_client.images.generate.return_value = _openai_response(b"y")

    with patch("openai.OpenAI", return_value=fake_client):
        provider = OpenAIImageProvider(api_key="k")
        await provider.generate("prompt", size="999x999")

    assert fake_client.images.generate.call_args.kwargs["size"] == "1024x1024"


@pytest.mark.asyncio
async def test_gemini_provider_raises_when_response_has_no_image() -> None:
    empty_response = MagicMock()
    empty_response.candidates = []
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = empty_response

    with patch("google.genai.Client", return_value=fake_client):
        provider = GeminiImageProvider(api_key="k")
        with pytest.raises(RuntimeError, match="no inline image data"):
            await provider.generate("prompt", size="1024x1024")


@pytest.mark.asyncio
async def test_gemini_provider_decodes_base64_string_payload() -> None:
    raw = b"decoded-bytes"
    inline = MagicMock()
    inline.data = base64.b64encode(raw).decode("ascii")
    part = MagicMock()
    part.inline_data = inline
    content = MagicMock()
    content.parts = [part]
    candidate = MagicMock()
    candidate.content = content
    response = MagicMock()
    response.candidates = [candidate]

    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = response

    with patch("google.genai.Client", return_value=fake_client):
        provider = GeminiImageProvider(api_key="k")
        assert await provider.generate("prompt", size="1024x1024") == raw
