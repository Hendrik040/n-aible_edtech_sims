#!/usr/bin/env python3
"""
Image storage utilities for DALL-E generated images
"""

import os
import aiohttp
import aiofiles
from pathlib import Path
from datetime import datetime
import hashlib
from typing import Optional

# Create images directory
IMAGES_DIR = Path("static/images/scenes")
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

async def download_and_save_image(image_url: str, scene_title: str, scenario_id: int) -> Optional[str]:
    """
    Download DALL-E image and save locally
    Returns full backend URL or None if failed
    """
    if not image_url:
        return None
        
    try:
        # Create filename from scene title and scenario ID
        safe_title = "".join(c for c in scene_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_title = safe_title.replace(' ', '_').lower()
        
        # Add hash for uniqueness
        url_hash = hashlib.md5(image_url.encode()).hexdigest()[:8]
        timestamp = int(datetime.now().timestamp())
        filename = f"scenario_{scenario_id}_{safe_title}_{timestamp}_{url_hash}.png"
        
        file_path = IMAGES_DIR / filename
        
        # Download image
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as response:
                if response.status == 200:
                    async with aiofiles.open(file_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
                    
                    # Return full URL with backend base URL from environment
                    # In production (Railway), this should be set to the Railway backend URL
                    # In development, it defaults to localhost
                    backend_url = os.getenv('BACKEND_URL', 'http://localhost:8001')
                    full_url = f"{backend_url}/static/images/scenes/{filename}"
                    print(f"[DEBUG] Saved image: {full_url}")
                    return full_url
                else:
                    print(f"[ERROR] Failed to download image: HTTP {response.status}")
                    return None
                    
    except Exception as e:
        print(f"[ERROR] Error downloading image: {e}")
        return None

async def cleanup_old_images(days_old: int = 30):
    """Clean up images older than specified days"""
    try:
        cutoff_time = datetime.now().timestamp() - (days_old * 24 * 60 * 60)
        
        for image_file in IMAGES_DIR.glob("*.png"):
            if image_file.stat().st_mtime < cutoff_time:
                image_file.unlink()
                print(f"[DEBUG] Cleaned up old image: {image_file.name}")
                
    except Exception as e:
        print(f"[ERROR] Error cleaning up images: {e}")

def get_image_url(local_path: str) -> str:
    """Convert local path to accessible URL"""
    if local_path and local_path.startswith("/static/"):
        return f"http://127.0.0.1:8001{local_path}"
    return local_path or "" 