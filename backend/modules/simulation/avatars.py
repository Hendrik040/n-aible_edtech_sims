"""
Persona avatar generation for the simulation module.

Delegates actual generation to common.services.image_service (Gemini default,
OpenAI fallback). This module handles prompt construction and batch processing.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from common.services import image_service

logger = logging.getLogger(__name__)


async def generate_persona_avatar(
    persona_name: str,
    persona_role: str,
    background: str = "",
    persona_id: Optional[int] = None,
) -> str:
    """Generate a professional avatar image for a persona."""
    logger.info("[IMAGE] Generating avatar for persona: %s (%s)", persona_name, persona_role)

    prompt = f"Professional business portrait of {persona_name}, {persona_role}. "
    if background:
        prompt += f"{background}. "
    prompt += (
        "Corporate headshot style, professional attire, "
        "neutral background, high quality, portrait photography."
    )

    return await image_service.generate_image(
        prompt[:500], size="1024x1024", quality="standard"
    )


async def generate_personas_with_avatars(
    personas: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Generate avatar images for multiple personas in parallel."""
    if not personas:
        logger.info("[IMAGE] No personas to generate avatars for")
        return personas

    logger.info("[IMAGE] Starting avatar generation for %d personas", len(personas))

    dynamic_limit = min(len(personas), 20)
    persona_semaphore = asyncio.Semaphore(dynamic_limit)

    async def generate_with_semaphore(
        name: str, role: str, bg: str, pid: Optional[int]
    ) -> str:
        async with persona_semaphore:
            return await generate_persona_avatar(name, role, bg, pid)

    avatar_tasks = []
    for i, persona in enumerate(personas):
        if isinstance(persona, dict) and "name" in persona and "role" in persona:
            persona_id = persona.get("id") or persona.get("persona_id")
            task = generate_with_semaphore(
                persona.get("name", ""),
                persona.get("role", ""),
                persona.get("background", ""),
                persona_id,
            )
            avatar_tasks.append(task)
        else:
            logger.warning("[IMAGE] Skipping invalid persona %d: %s", i + 1, persona)

            async def empty_task():
                return ""

            avatar_tasks.append(empty_task())

    avatar_urls = await asyncio.gather(*avatar_tasks, return_exceptions=True)

    for i, persona in enumerate(personas):
        if isinstance(persona, dict):
            url = (
                avatar_urls[i]
                if i < len(avatar_urls) and not isinstance(avatar_urls[i], Exception)
                else ""
            )
            persona["image_url"] = url
            if url:
                persona["avatar_url"] = url
            if isinstance(avatar_urls[i], Exception):
                logger.error(
                    "[IMAGE] Persona %d avatar failed: %s", i + 1, avatar_urls[i]
                )

    return personas
