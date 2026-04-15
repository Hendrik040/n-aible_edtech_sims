"""
Centralized image generation service with provider abstraction.

Gemini Imagen is the default provider; falls back to OpenAI DALL-E
when the Gemini key is missing or the call fails.
"""

import asyncio
import logging
from typing import Optional

import httpx
import openai

from common.config import get_settings

logger = logging.getLogger(__name__)


async def _generate_with_gemini(
    prompt: str, api_key: str, aspect_ratio: str = "1:1"
) -> Optional[str]:
    """Generate an image via Google Gemini Imagen API."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict",
                params={"key": api_key},
                headers={"Content-Type": "application/json"},
                json={
                    "instances": [{"prompt": prompt}],
                    "parameters": {
                        "sampleCount": 1,
                        "aspectRatio": aspect_ratio,
                    },
                },
            )

            if response.status_code == 200:
                data = response.json()
                predictions = data.get("predictions", [])
                if predictions:
                    b64 = predictions[0].get("bytesBase64Encoded")
                    if b64:
                        mime = predictions[0].get("mimeType", "image/png")
                        return f"data:{mime};base64,{b64}"
                logger.warning("[IMAGE] Gemini returned 200 but no image data")
                return None

            logger.warning(
                "[IMAGE] Gemini API returned status %d: %s",
                response.status_code,
                response.text[:300],
            )
            return None

    except Exception as e:
        logger.warning("[IMAGE] Gemini generation failed: %s", e)
        return None


async def _generate_with_openai(
    prompt: str, api_key: str, size: str = "1024x1024", quality: str = "standard"
) -> Optional[str]:
    """Generate an image via OpenAI DALL-E 3."""
    try:
        client = openai.OpenAI(api_key=api_key)
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size=size,
                quality=quality,
                n=1,
            ),
        )
        return response.data[0].url
    except Exception as e:
        logger.warning("[IMAGE] OpenAI DALL-E generation failed: %s", e)
        return None


async def generate_image(
    prompt: str, size: str = "1024x1024", quality: str = "standard"
) -> str:
    """
    Generate an image using the configured provider (Gemini default, OpenAI fallback).

    Returns a temporary URL (or data-URI for Gemini) on success, empty string on failure.
    """
    settings = get_settings()
    provider = (settings.image_provider or "gemini").lower()

    if provider == "gemini" and settings.gemini_api_key:
        url = await _generate_with_gemini(prompt, settings.gemini_api_key)
        if url:
            logger.info("[IMAGE] Generated via Gemini")
            return url
        logger.info("[IMAGE] Gemini failed, falling back to OpenAI")

    if settings.openai_api_key:
        url = await _generate_with_openai(
            prompt, settings.openai_api_key, size, quality
        )
        if url:
            logger.info("[IMAGE] Generated via OpenAI DALL-E")
            return url

    logger.error("[IMAGE] All image providers failed or no API keys configured")
    return ""
