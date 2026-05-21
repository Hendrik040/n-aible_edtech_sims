"""
Image Generation Service for PDF Processing

Handles DALL-E image generation for simulation scenes using OpenAI's API,
and FreePik AI image generation for persona avatars.
"""
import asyncio
import time
import logging
import openai
import httpx
from typing import List, Dict, Any, Optional
from common.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Image generation configuration
OPENAI_API_KEY = getattr(settings, 'openai_api_key', None)
FREEPIK_API_KEY = getattr(settings, 'freepik_api_key', None)
MAX_CONCURRENT_IMAGES = 10  # Limit concurrent image generations for scenes
FREEPIK_BASE_URL = "https://api.freepik.com"

# Global semaphore for image generation rate limiting (scenes) - lazily initialized
_image_semaphore: Optional[asyncio.Semaphore] = None

# Log configuration on module load
logger.info(f"[FREEPIK] FreePik configuration loaded: API Key available = {bool(FREEPIK_API_KEY)}")


def _get_image_semaphore() -> asyncio.Semaphore:
    """
    Get or create the image generation semaphore with lazy initialization.
    This ensures the semaphore is bound to the correct event loop at runtime.
    
    Returns:
        The semaphore instance for rate limiting scene image generation
    """
    global _image_semaphore
    if _image_semaphore is None:
        _image_semaphore = asyncio.Semaphore(MAX_CONCURRENT_IMAGES)
    return _image_semaphore


async def generate_scene_image(
    scene_description: str, 
    scene_title: str, 
    simulation_id: int = 0, 
    scene_id: Optional[int] = None
) -> str:
    """
    Generate an image for a scene using OpenAI's DALL-E API and return URL.
    
    Args:
        scene_description: Description of the scene for image generation
        scene_title: Title of the scene
        simulation_id: Simulation ID (for reference, not used for upload here)
        scene_id: Optional scene ID (for reference, not used for upload here)
        
    Returns:
        Temporary image URL from DALL-E, or empty string on failure.
        Permanent upload to AWS S3 happens later in the publishing flow.
    """
    logger.info(f"[IMAGE] Generating image for scene: {scene_title}")
    start_time = time.time()
    
    async with _get_image_semaphore():  # Rate limiting
        try:
            if not OPENAI_API_KEY:
                logger.error("[IMAGE] OpenAI API key not configured")
                return ""
            
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
            logger.info(f"[IMAGE] Generated image for '{scene_title}' in {generation_time:.2f}s")
            logger.info(f"[IMAGE] Temporary URL: {temp_image_url}")
            
            # Return temporary URL - permanent upload to AWS S3 happens later in publishing flow
            return temp_image_url
            
        except Exception as e:
            logger.error(f"[ERROR] Image generation failed for scene '{scene_title}': {str(e)}")
            return ""  # Return empty string on failure


async def generate_scenes_with_images(
    scenes: List[Dict[str, Any]], 
    session_id: Optional[str] = None,
    simulation_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Generate images for multiple scenes in parallel.
    
    Args:
        scenes: List of scene dictionaries with 'description' and 'title' keys
        session_id: Optional session ID for progress tracking
        simulation_id: Optional simulation ID (for reference, not used for upload here)
        
    Returns:
        List of scenes with 'image_url' added to each scene.
        URLs are temporary - permanent upload to AWS S3 happens later in publishing flow.
    """
    if not scenes:
        logger.info("[IMAGE] No scenes to generate images for")
        return scenes
    
    logger.info(f"[IMAGE] Starting image generation for {len(scenes)} scenes")
    logger.info(f"[IMAGE] OpenAI API key available: {bool(OPENAI_API_KEY)}")
    
    image_tasks = []
    for i, scene in enumerate(scenes):
        if isinstance(scene, dict) and "description" in scene and "title" in scene:
            scene_id = scene.get("id") or scene.get("scene_id")
            logger.info(f"[IMAGE] Creating image task for scene {i+1}: {scene.get('title', 'Untitled')}")
            task = generate_scene_image(
                scene["description"], 
                scene["title"], 
                simulation_id or 0,
                scene_id
            )
            image_tasks.append(task)
        else:
            logger.warning(f"[IMAGE] Skipping invalid scene {i+1}: {scene}")
            # Create a simple async function that returns empty string
            async def empty_task():
                return ""
            image_tasks.append(empty_task())
    
    # Wait for all image generations to complete
    logger.info(f"[IMAGE] Waiting for {len(image_tasks)} image generation tasks...")
    image_urls = await asyncio.gather(*image_tasks, return_exceptions=True)
    
    # Update scenes with image URLs
    for i, scene in enumerate(scenes):
        if isinstance(scene, dict):
            image_url = image_urls[i] if i < len(image_urls) and not isinstance(image_urls[i], Exception) else ""
            scene["image_url"] = image_url
            if isinstance(image_urls[i], Exception):
                logger.error(f"[IMAGE] Scene {i+1}: {scene.get('title', 'Untitled')} - Image FAILED: {image_urls[i]}")
            else:
                logger.info(f"[IMAGE] Scene {i+1}: {scene.get('title', 'Untitled')} - Image: {'Generated' if image_url else 'Failed'}")
    
    return scenes


async def _generate_persona_avatar_unsafe(
    persona_name: str, 
    persona_role: str, 
    background: str = "", 
    persona_id: Optional[int] = None
) -> str:
    """
    Generate a professional avatar image for a persona using FreePik AI (Mystic model).
    Internal function without semaphore - use via generate_personas_with_avatars.
    
    Args:
        persona_name: Name of the persona
        persona_role: Professional role/title
        background: Background description (optional)
        persona_id: Optional persona ID (for reference, not used for upload here)
        
    Returns:
        Temporary image URL from FreePik, or empty string on failure.
        Permanent upload to AWS S3 happens later in the publishing flow.
    """
    logger.info(f"[FREEPIK] Generating avatar for persona: {persona_name} ({persona_role})")
    start_time = time.time()
    
    if not FREEPIK_API_KEY:
        logger.error("[FREEPIK] ERROR: FreePik API key not configured")
        return ""
    
    try:
        # Create a professional avatar prompt
        avatar_prompt = f"Professional business portrait of {persona_name}, {persona_role}. "
        if background:
            avatar_prompt += f"{background}. "
        avatar_prompt += "Corporate headshot style, professional attire, neutral background, high quality, portrait photography."
        
        # Trim prompt to reasonable length
        avatar_prompt = avatar_prompt[:500]
        
        logger.info(f"[FREEPIK] Prompt: {avatar_prompt}")
        
        # Use FreePik Mystic model for ultra-realistic, high-resolution avatars
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{FREEPIK_BASE_URL}/v1/ai/mystic",
                headers={
                    "x-freepik-api-key": FREEPIK_API_KEY,
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                json={
                    "prompt": avatar_prompt,
                    "aspect_ratio": "square_1_1",  # Square format for avatars
                    "resolution": "1k"  # 1K resolution for faster generation
                }
            )
            
            logger.info(f"[FREEPIK] API response status: {response.status_code}")
            logger.debug(f"[FREEPIK] API response headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                result = response.json()
                logger.debug(f"[FREEPIK] Response keys: {result.keys() if isinstance(result, dict) else 'not a dict'}")
                logger.debug(f"[FREEPIK] Response body: {result}")
                
                # FreePik Mystic returns task_id nested in "data" for async processing
                if "data" in result and "task_id" in result["data"]:
                    task_id = result["data"]["task_id"]
                    logger.info(f"[FREEPIK] Task created: {task_id}, polling for result...")
                    
                    # Poll for completion (max 90 seconds for Mystic)
                    max_wait = 90
                    poll_interval = 3
                    waited = 0
                    task_failed = False
                    
                    while waited < max_wait:
                        await asyncio.sleep(poll_interval)
                        waited += poll_interval
                        
                        status_response = await client.get(
                            f"{FREEPIK_BASE_URL}/v1/ai/mystic/{task_id}",
                            headers={
                                "x-freepik-api-key": FREEPIK_API_KEY,
                                "Accept": "application/json"
                            }
                        )
                        
                        logger.info(f"[FREEPIK] Poll attempt for task {task_id}: status={status_response.status_code}")
                        
                        if status_response.status_code == 200:
                            status_data = status_response.json()
                            logger.debug(f"[FREEPIK] Poll response: {status_data}")
                            
                            # Check if completed - status is nested in "data"
                            if "data" in status_data:
                                task_data = status_data["data"]
                                status = task_data.get("status", "").upper()
                                logger.info(f"[FREEPIK] Task {task_id} status: {status}")
                                
                                if status == "COMPLETED":
                                    image_urls = task_data.get("generated", [])
                                    if image_urls and len(image_urls) > 0:
                                        # generated is a list of URL strings, not objects
                                        temp_image_url = image_urls[0] if isinstance(image_urls[0], str) else image_urls[0].get("url", "")
                                        generation_time = time.time() - start_time
                                        logger.info(f"[FREEPIK] Generated avatar for '{persona_name}' in {generation_time:.2f}s")
                                        logger.info(f"[FREEPIK] Temporary URL: {temp_image_url}")
                                        
                                        # Return temporary URL - permanent upload to AWS S3 happens later in publishing flow
                                        return temp_image_url
                                    
                                elif status == "FAILED":
                                    error_msg = task_data.get("error", "Unknown error")
                                    logger.error(f"[FREEPIK] Task {task_id} failed: {error_msg}")
                                    task_failed = True
                                    break
                            else:
                                logger.warning(f"[FREEPIK] No 'data' key in poll response: {status_data}")
                        else:
                            # Log non-200 polling responses
                            logger.warning(f"[FREEPIK] Poll request returned status {status_response.status_code}: {status_response.text[:500]}")
                    
                    # Only log timeout if loop exited due to max_wait, not due to task failure
                    if not task_failed:
                        logger.error(f"[FREEPIK] Task {task_id} timed out after {max_wait}s")
                    return ""
                else:
                    logger.error("[FREEPIK] No task_id in response data")
                    return ""
            else:
                logger.error(f"[FREEPIK] API request failed with status {response.status_code}")
                logger.debug(f"[FREEPIK] Response headers: {dict(response.headers)}")
                logger.debug(f"[FREEPIK] Response body: {response.text}")
                return ""
                
    except Exception as e:
        import traceback
        logger.error(f"[FREEPIK] Avatar generation failed for '{persona_name}': {type(e).__name__}: {str(e)}")
        logger.debug(f"[FREEPIK] Traceback: {traceback.format_exc()}")
        return ""


async def generate_personas_with_avatars(personas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate avatar images for multiple personas in parallel using FreePik AI.
    
    Args:
        personas: List of persona dictionaries with 'name', 'role', and optionally 'background'
        
    Returns:
        List of personas with 'image_url' added to each persona (or 'avatar_url' for compatibility)
    """
    if not personas:
        logger.info("[FREEPIK] No personas to generate avatars for")
        return personas
    
    logger.info(f"[FREEPIK] Starting avatar generation for {len(personas)} personas")
    logger.info(f"[FREEPIK] FreePik API key available: {bool(FREEPIK_API_KEY)}")
    
    # Create a dynamic semaphore based on the number of personas (max 20 to prevent API overload)
    dynamic_limit = min(len(personas), 20)
    persona_semaphore = asyncio.Semaphore(dynamic_limit)
    logger.info(f"[FREEPIK] Using dynamic semaphore limit: {dynamic_limit}")
    
    # Inner function that uses the dynamic semaphore
    async def generate_with_semaphore(persona_name: str, persona_role: str, background: str, persona_id: Optional[int] = None) -> str:
        async with persona_semaphore:
            return await _generate_persona_avatar_unsafe(persona_name, persona_role, background, persona_id)
    
    avatar_tasks = []
    for i, persona in enumerate(personas):
        if isinstance(persona, dict) and "name" in persona and "role" in persona:
            persona_id = persona.get("id") or persona.get("persona_id")
            logger.info(f"[FREEPIK] Creating avatar task for persona {i+1}: {persona.get('name', 'Unknown')}")
            task = generate_with_semaphore(
                persona.get("name", ""), 
                persona.get("role", ""), 
                persona.get("background", ""),
                persona_id
            )
            avatar_tasks.append(task)
        else:
            logger.warning(f"[FREEPIK] Skipping invalid persona {i+1}: {persona}")
            async def empty_task():
                return ""
            avatar_tasks.append(empty_task())
    
    # Wait for all avatar generations to complete
    logger.info(f"[FREEPIK] Waiting for {len(avatar_tasks)} avatar generation tasks...")
    avatar_urls = await asyncio.gather(*avatar_tasks, return_exceptions=True)
    
    # Update personas with avatar URLs (using image_url to match database schema)
    for i, persona in enumerate(personas):
        if isinstance(persona, dict):
            avatar_url = avatar_urls[i] if i < len(avatar_urls) and not isinstance(avatar_urls[i], Exception) else ""
            persona["image_url"] = avatar_url
            # Also set avatar_url for backwards compatibility
            if avatar_url:
                persona["avatar_url"] = avatar_url
            if isinstance(avatar_urls[i], Exception):
                logger.error(f"[FREEPIK] Persona {i+1}: {persona.get('name', 'Unknown')} - Avatar FAILED: {avatar_urls[i]}")
            else:
                logger.info(f"[FREEPIK] Persona {i+1}: {persona.get('name', 'Unknown')} - Avatar: {'Generated' if avatar_url else 'Failed'}")
    
    return personas

