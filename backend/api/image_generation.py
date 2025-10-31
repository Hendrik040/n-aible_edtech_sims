"""
Image Generation API Module

Handles DALL-E image generation for simulation scenes using OpenAI's API,
and FreePik AI image generation for persona avatars.
"""
import asyncio
import time
import openai
import httpx
from typing import List, Dict, Any, Optional
from utilities.debug_logging import debug_log
from database.connection import settings

# Image generation configuration
OPENAI_API_KEY = settings.openai_api_key
FREEPIK_API_KEY = settings.freepik_api_key
MAX_CONCURRENT_IMAGES = 4  # Limit concurrent image generations
FREEPIK_BASE_URL = "https://api.freepik.com"

# Global semaphore for image generation rate limiting
_image_semaphore = asyncio.Semaphore(MAX_CONCURRENT_IMAGES)
_freepik_semaphore = asyncio.Semaphore(MAX_CONCURRENT_IMAGES)

# Log configuration on module load
debug_log(f"[FREEPIK] FreePik configuration loaded: API Key available = {bool(FREEPIK_API_KEY)}")


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


async def generate_persona_avatar_freepik(persona_name: str, persona_role: str, background: str = "") -> str:
    """
    Generate a professional avatar image for a persona using FreePik AI (Mystic model).
    
    Args:
        persona_name: Name of the persona
        persona_role: Professional role/title
        background: Background description (optional)
        
    Returns:
        URL of the generated image, or empty string on failure
    """
    debug_log(f"[FREEPIK] Generating avatar for persona: {persona_name} ({persona_role})")
    debug_log(f"[FREEPIK] FreePik API key check: {bool(FREEPIK_API_KEY)}")
    start_time = time.time()
    
    if not FREEPIK_API_KEY:
        debug_log("[FREEPIK] ERROR: FreePik API key not configured")
        return ""
    
    async with _freepik_semaphore:  # Rate limiting
        try:
            # Create a professional avatar prompt
            avatar_prompt = f"Professional business portrait of {persona_name}, {persona_role}. "
            if background:
                avatar_prompt += f"{background}. "
            avatar_prompt += "Corporate headshot style, professional attire, neutral background, high quality, portrait photography."
            
            # Trim prompt to reasonable length
            avatar_prompt = avatar_prompt[:500]
            
            debug_log(f"[FREEPIK] Prompt: {avatar_prompt}")
            
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
                
                debug_log(f"[FREEPIK] API response status: {response.status_code}")
                debug_log(f"[FREEPIK] API response headers: {dict(response.headers)}")
                
                if response.status_code == 200:
                    result = response.json()
                    debug_log(f"[FREEPIK] Response keys: {result.keys() if isinstance(result, dict) else 'not a dict'}")
                    debug_log(f"[FREEPIK] Response body: {result}")
                    
                    # FreePik Mystic returns task_id nested in "data" for async processing
                    if "data" in result and "task_id" in result["data"]:
                        task_id = result["data"]["task_id"]
                        debug_log(f"[FREEPIK] Task created: {task_id}, polling for result...")
                        
                        # Poll for completion (max 90 seconds for Mystic)
                        max_wait = 90
                        poll_interval = 3
                        waited = 0
                        
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
                            
                            if status_response.status_code == 200:
                                status_data = status_response.json()
                                debug_log(f"[FREEPIK] Poll response: {status_data}")
                                
                                # Check if completed - status is nested in "data"
                                if "data" in status_data:
                                    task_data = status_data["data"]
                                    status = task_data.get("status", "").upper()
                                    if status == "COMPLETED":
                                        image_urls = task_data.get("generated", [])
                                        if image_urls and len(image_urls) > 0:
                                            # generated is a list of URL strings, not objects
                                            image_url = image_urls[0] if isinstance(image_urls[0], str) else image_urls[0].get("url", "")
                                            generation_time = time.time() - start_time
                                            debug_log(f"[FREEPIK] Generated avatar for '{persona_name}' in {generation_time:.2f}s")
                                            debug_log(f"[FREEPIK] Avatar URL: {image_url}")
                                            return image_url
                                        
                                    elif status == "FAILED":
                                        debug_log(f"[FREEPIK] Task {task_id} failed")
                                        break
                        
                        debug_log(f"[FREEPIK] Task {task_id} timed out after {max_wait}s")
                        return ""
                    else:
                        debug_log("[FREEPIK] No task_id in response data")
                        return ""
                else:
                    debug_log(f"[FREEPIK] API request failed with status {response.status_code}")
                    debug_log(f"[FREEPIK] Response headers: {dict(response.headers)}")
                    debug_log(f"[FREEPIK] Response body: {response.text}")
                    return ""
                    
        except Exception as e:
            debug_log(f"[FREEPIK] Avatar generation failed for '{persona_name}': {str(e)}")
            return ""


async def generate_personas_with_avatars(personas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate avatar images for multiple personas in parallel using FreePik AI.
    
    Args:
        personas: List of persona dictionaries with 'name', 'role', and optionally 'background'
        
    Returns:
        List of personas with 'avatar_url' added to each persona
    """
    if not personas:
        debug_log("[FREEPIK] No personas to generate avatars for")
        return personas
    
    debug_log(f"[FREEPIK] Starting avatar generation for {len(personas)} personas")
    debug_log(f"[FREEPIK] FreePik API key available: {bool(FREEPIK_API_KEY)}")
    
    avatar_tasks = []
    for i, persona in enumerate(personas):
        if isinstance(persona, dict) and "name" in persona and "role" in persona:
            debug_log(f"[FREEPIK] Creating avatar task for persona {i+1}: {persona.get('name', 'Unknown')}")
            task = generate_persona_avatar_freepik(
                persona.get("name", ""), 
                persona.get("role", ""), 
                persona.get("background", "")
            )
            avatar_tasks.append(task)
        else:
            debug_log(f"[FREEPIK] Skipping invalid persona {i+1}: {persona}")
            async def empty_task():
                return ""
            avatar_tasks.append(empty_task())
    
    # Wait for all avatar generations to complete
    debug_log(f"[FREEPIK] Waiting for {len(avatar_tasks)} avatar generation tasks...")
    avatar_urls = await asyncio.gather(*avatar_tasks, return_exceptions=True)
    
    # Update personas with avatar URLs (using image_url to match database schema)
    for i, persona in enumerate(personas):
        if isinstance(persona, dict):
            avatar_url = avatar_urls[i] if i < len(avatar_urls) and not isinstance(avatar_urls[i], Exception) else ""
            persona["image_url"] = avatar_url
            if isinstance(avatar_urls[i], Exception):
                debug_log(f"[FREEPIK] Persona {i+1}: {persona.get('name', 'Unknown')} - Avatar FAILED: {avatar_urls[i]}")
            else:
                debug_log(f"[FREEPIK] Persona {i+1}: {persona.get('name', 'Unknown')} - Avatar: {'Generated' if avatar_url else 'Failed'}")
    
    return personas

