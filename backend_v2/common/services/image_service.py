"""Image generation service with strategy-pattern backends.

Two backends are supported, selected by the ``IMAGE_PROVIDER`` setting:

- ``gemini`` (default): Google Gemini 2.5 Flash Image via ``google-genai``.
- ``openai``: OpenAI DALL\u00b7E via the ``openai`` SDK.

Both providers expose the same async contract and return raw image bytes.
Callers are responsible for persisting the bytes (e.g. to S3) \u2014 this
module is a thin SDK wrapper and nothing more.
"""
from __future__ import annotations

import asyncio
import base64
from abc import ABC, abstractmethod
from typing import Any

from common.config import get_settings


__all__ = ["generate_image"]


_GEMINI_MODEL = "gemini-2.5-flash-image"
_OPENAI_MODEL = "dall-e-3"
_OPENAI_ALLOWED_SIZES = frozenset({"1024x1024", "1024x1792", "1792x1024"})


class ImageProvider(ABC):
    """Strategy interface implemented by each concrete image backend."""

    @abstractmethod
    async def generate(self, prompt: str, size: str) -> bytes:
        """Return the raw bytes for a single generated image."""


class GeminiImageProvider(ImageProvider):
    """Google Gemini 2.5 Flash Image backend."""

    def __init__(self, api_key: str, model: str = _GEMINI_MODEL) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def generate(self, prompt: str, size: str) -> bytes:
        # Gemini 2.5 Flash Image has no dedicated size parameter, so we
        # fold the requested dimensions into the prompt.
        sized_prompt = f"{prompt}\n\nRender at {size}."

        def _call() -> Any:
            return self._client.models.generate_content(
                model=self._model,
                contents=[sized_prompt],
            )

        response = await asyncio.get_running_loop().run_in_executor(None, _call)
        return _extract_gemini_bytes(response)


class OpenAIImageProvider(ImageProvider):
    """OpenAI DALL\u00b7E backend returning ``b64_json`` payloads."""

    def __init__(self, api_key: str, model: str = _OPENAI_MODEL) -> None:
        import openai

        self._client = openai.OpenAI(api_key=api_key)
        self._model = model

    async def generate(self, prompt: str, size: str) -> bytes:
        resolved_size = size if size in _OPENAI_ALLOWED_SIZES else "1024x1024"

        def _call() -> Any:
            return self._client.images.generate(
                model=self._model,
                prompt=prompt,
                size=resolved_size,
                response_format="b64_json",
                n=1,
            )

        response = await asyncio.get_running_loop().run_in_executor(None, _call)
        b64 = response.data[0].b64_json
        return base64.b64decode(b64)


def _extract_gemini_bytes(response: Any) -> bytes:
    """Pull the first ``inline_data.data`` payload out of a Gemini response."""
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None) if inline is not None else None
            if not data:
                continue
            if isinstance(data, bytes):
                return data
            if isinstance(data, str):
                return base64.b64decode(data)
    raise RuntimeError("Gemini response contained no inline image data")


def _get_provider() -> ImageProvider:
    """Build the provider selected by ``IMAGE_PROVIDER``.

    Raises ``ValueError`` for unknown provider names or when the API key for
    the selected provider is missing.
    """
    settings = get_settings()
    name = (settings.image_provider or "gemini").strip().lower()

    if name == "gemini":
        key = settings.google_genai_api_key
        if not key:
            raise ValueError(
                "IMAGE_PROVIDER=gemini but GOOGLE_GENAI_API_KEY is not configured"
            )
        return GeminiImageProvider(api_key=key)

    if name == "openai":
        key = settings.openai_api_key
        if not key:
            raise ValueError(
                "IMAGE_PROVIDER=openai but OPENAI_API_KEY is not configured"
            )
        return OpenAIImageProvider(api_key=key)

    raise ValueError(
        f"Unknown IMAGE_PROVIDER={settings.image_provider!r} "
        "(supported values: 'gemini', 'openai')"
    )


async def generate_image(prompt: str, size: str = "1024x1024") -> bytes:
    """Generate a single image using the configured backend.

    Returns raw image bytes. The caller handles persistence and any
    post-processing (thumbnailing, safety filters, etc.).
    """
    provider = _get_provider()
    return await provider.generate(prompt, size)
