"""
Scene image generation for the publishing pipeline.

Delegates actual generation to common.services.image_service (Gemini default,
OpenAI fallback). This module handles prompt construction and batch processing.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from common.services import image_service

logger = logging.getLogger(__name__)

MAX_CONCURRENT_IMAGES = 10

_image_semaphore: Optional[asyncio.Semaphore] = None


def _get_image_semaphore() -> asyncio.Semaphore:
    global _image_semaphore
    if _image_semaphore is None:
        _image_semaphore = asyncio.Semaphore(MAX_CONCURRENT_IMAGES)
    return _image_semaphore


async def generate_scene_image(
    scene_description: str,
    scene_title: str,
    simulation_id: int = 0,
    scene_id: Optional[int] = None,
) -> str:
    """Generate an image for a simulation scene."""
    logger.info("[IMAGE] Generating image for scene: %s", scene_title)

    async with _get_image_semaphore():
        prompt = (
            f"Professional business illustration: {scene_title}. "
            f"{scene_description[:100]}. "
            "Clean, modern corporate style, educational use."
        )
        return await image_service.generate_image(
            prompt[:400], size="1024x1024", quality="standard"
        )


async def generate_scenes_with_images(
    scenes: List[Dict[str, Any]],
    session_id: Optional[str] = None,
    simulation_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Generate images for multiple scenes in parallel."""
    if not scenes:
        logger.info("[IMAGE] No scenes to generate images for")
        return scenes

    logger.info("[IMAGE] Starting image generation for %d scenes", len(scenes))

    image_tasks = []
    for i, scene in enumerate(scenes):
        if isinstance(scene, dict) and "description" in scene and "title" in scene:
            scene_id = scene.get("id") or scene.get("scene_id")
            task = generate_scene_image(
                scene["description"],
                scene["title"],
                simulation_id or 0,
                scene_id,
            )
            image_tasks.append(task)
        else:
            logger.warning("[IMAGE] Skipping invalid scene %d: %s", i + 1, scene)

            async def empty_task():
                return ""

            image_tasks.append(empty_task())

    image_urls = await asyncio.gather(*image_tasks, return_exceptions=True)

    for i, scene in enumerate(scenes):
        if isinstance(scene, dict):
            url = (
                image_urls[i]
                if i < len(image_urls) and not isinstance(image_urls[i], Exception)
                else ""
            )
            scene["image_url"] = url
            if isinstance(image_urls[i], Exception):
                logger.error(
                    "[IMAGE] Scene %d failed: %s", i + 1, image_urls[i]
                )

    return scenes
