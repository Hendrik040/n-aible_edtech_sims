"""
Image Generation API Module

Handles DALL-E image generation for simulation scenes using OpenAI's API.
"""
import asyncio
import time
import openai
from typing import List, Dict, Any, Optional
from utilities.debug_logging import debug_log
from database.connection import settings

# Image generation configuration
OPENAI_API_KEY = settings.openai_api_key
MAX_CONCURRENT_IMAGES = 4  # Limit concurrent image generations

# Global semaphore for image generation rate limiting
_image_semaphore = asyncio.Semaphore(MAX_CONCURRENT_IMAGES)


async def generate_scene_image(scene_description: str, scene_title: str, scenario_id: int = 0) -> str:
    """
    Generate an image for a scene using OpenAI's DALL-E API and return temporary URL.
    
    Args:
        scene_description: Description of the scene for image generation
        scene_title: Title of the scene
        scenario_id: Optional scenario ID (for future use, currently unused)
        
    Returns:
        Temporary URL of the generated image, or empty string on failure
    """
    debug_log(f"[IMAGE] Generating image for scene: {scene_title}")
    start_time = time.time()
    
    async with _image_semaphore:  # Rate limiting
        try:
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            
            # Create an optimized prompt for image generation
            image_prompt = f"Professional business illustration: {scene_title}. {scene_description[:100]}. Clean, modern corporate style, educational use."
            
            # Use executor for blocking OpenAI call
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.images.generate(
                    model="dall-e-3",
                    prompt=image_prompt[:400],  # Truncate to stay within limits
                    size="1024x1024",
                    quality="standard",
                    n=1,
                )
            )
            
            temp_image_url = response.data[0].url
            generation_time = time.time() - start_time
            debug_log(f"[IMAGE] Generated image for '{scene_title}' in {generation_time:.2f}s")
            debug_log(f"[IMAGE] Returning temporary URL (will expire): {temp_image_url}")
            
            # Return temporary URL directly (no local storage)
            return temp_image_url
            
        except Exception as e:
            debug_log(f"[ERROR] Image generation failed for scene '{scene_title}': {str(e)}")
            return ""  # Return empty string on failure


async def generate_scenes_with_images(
    scenes: List[Dict[str, Any]], 
    session_id: str = None
) -> List[Dict[str, Any]]:
    """
    Generate images for multiple scenes in parallel.
    
    Args:
        scenes: List of scene dictionaries with 'description' and 'title' keys
        session_id: Optional session ID for progress tracking
        
    Returns:
        List of scenes with 'image_url' added to each scene
    """
    if not scenes:
        debug_log("[IMAGE] No scenes to generate images for")
        return scenes
    
    debug_log(f"[IMAGE] Starting image generation for {len(scenes)} scenes")
    debug_log(f"[IMAGE] OpenAI API key available: {bool(OPENAI_API_KEY)}")
    
    image_tasks = []
    for i, scene in enumerate(scenes):
        if isinstance(scene, dict) and "description" in scene and "title" in scene:
            debug_log(f"[IMAGE] Creating image task for scene {i+1}: {scene.get('title', 'Untitled')}")
            task = generate_scene_image(scene["description"], scene["title"], 0)
            image_tasks.append(task)
        else:
            debug_log(f"[IMAGE] Skipping invalid scene {i+1}: {scene}")
            # Create a simple async function that returns empty string
            async def empty_task():
                return ""
            image_tasks.append(empty_task())
    
    # Wait for all image generations to complete
    debug_log(f"[IMAGE] Waiting for {len(image_tasks)} image generation tasks...")
    image_urls = await asyncio.gather(*image_tasks, return_exceptions=True)
    
    # Update scenes with image URLs
    for i, scene in enumerate(scenes):
        if isinstance(scene, dict):
            image_url = image_urls[i] if i < len(image_urls) and not isinstance(image_urls[i], Exception) else ""
            scene["image_url"] = image_url
            if isinstance(image_urls[i], Exception):
                debug_log(f"[IMAGE] Scene {i+1}: {scene.get('title', 'Untitled')} - Image FAILED: {image_urls[i]}")
            else:
                debug_log(f"[IMAGE] Scene {i+1}: {scene.get('title', 'Untitled')} - Image: {'Generated' if image_url else 'Failed'}")
    
    return scenes

