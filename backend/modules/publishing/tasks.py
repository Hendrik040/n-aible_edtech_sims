"""
Background tasks for image upload processing.

Worker process that continuously polls Redis queue and uploads images to S3.
Also contains helper functions for image upload queue management.
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from sqlalchemy.orm import Session

from common.db.core import SessionLocal
from common.services.cache_service import redis_manager
from common.services.s3_service import (
    s3_service,
    upload_persona_avatar_from_url,
    upload_scene_image_from_url
)
from common.db.models import SimulationPersona, SimulationScene

logger = logging.getLogger(__name__)

# Rate limiting: max 10 concurrent uploads
UPLOAD_SEMAPHORE = asyncio.Semaphore(10)
MAX_RETRIES = 3
QUEUE_KEY = "image_upload_queue"


# Helper functions for URL checking
def is_temporary_image_url(url: str) -> bool:
    """Check if a URL is a temporary URL that needs to be uploaded to S3."""
    if not url or not isinstance(url, str):
        return False
    
    # Permanent AWS URLs - don't upload these
    if 'amazonaws.com' in url or (url.startswith('http') and '/s3.' in url):
        return False
    
    # Temporary URLs from DALL-E or FreePik - these need uploading
    if 'oaidalleapiprodscus.blob.core.windows.net' in url or \
       'dalleprodsec.blob.core.windows.net' in url or \
       'cdn-magnific.freepik.com' in url:
        return True
    
    # If it's an HTTP URL but not AWS, assume it's temporary
    if url.startswith('http'):
        return True
    
    return False


def is_s3_url(url: str) -> bool:
    """Check if a URL is already an S3 URL."""
    if not url or not isinstance(url, str):
        return False
    
    url_lower = url.lower()
    # Check for AWS S3 patterns
    if 's3.amazonaws.com' in url_lower or 's3-' in url_lower and '.amazonaws.com' in url_lower:
        return True
    # Check if URL contains our bucket structure
    if 'scenarios/' in url_lower and ('personas/' in url_lower or 'scenes/' in url_lower):
        return True
    
    return False


# Image upload queue management functions
async def check_image_exists_in_s3(
    simulation_id: int,
    image_type: str,
    image_id: int
) -> Optional[str]:
    """Check if image already exists in S3, return S3 URL if found."""
    for ext in ['jpg', 'png', 'webp']:
        if image_type == 'persona':
            s3_key = s3_service.get_persona_avatar_key(simulation_id, image_id, ext)
        else:
            s3_key = s3_service.get_scene_image_key(simulation_id, image_id, ext)
        
        if await s3_service.file_exists(s3_key):
            return s3_service._build_public_url(s3_key)
    return None


def get_upload_status(simulation_id: int) -> Dict[str, Any]:
    """Get upload status for a simulation."""
    status_key = f"upload:status:{simulation_id}"
    
    # Safely get list lengths (handle case where key might be wrong type)
    try:
        pending = redis_manager.llen(f"{status_key}:pending")
    except Exception:
        # Key might be wrong type (set instead of list) - treat as 0
        pending = 0
    
    try:
        completed = redis_manager.llen(f"{status_key}:completed")
    except Exception:
        completed = 0
    
    try:
        failed = redis_manager.llen(f"{status_key}:failed")
    except Exception:
        failed = 0
    
    total = pending + completed + failed
    
    if total == 0:
        return {"status": "completed", "completed": 0, "total": 0, "failed": []}
    
    if pending > 0:
        status = "uploading"
    elif failed > 0:
        status = "failed"
    else:
        status = "completed"
    
    failed_list = redis_manager.lrange(f"{status_key}:failed", 0, -1)
    
    return {
        "status": status,
        "completed": completed,
        "total": total,
        "pending": pending,
        "failed": failed_list
    }


async def enqueue_image_upload(
    db: Session,
    repository,
    simulation_id: int,
    image_type: str,  # 'persona' or 'scene'
    image_id: int,
    temp_url: str
) -> bool:
    """Enqueue an image upload job to Redis queue. Checks S3 first to prevent duplicates."""
    # CRITICAL: Check if image already exists in S3 before enqueueing
    existing_s3_url = await check_image_exists_in_s3(simulation_id, image_type, image_id)
    if existing_s3_url:
        # Image already exists in S3 - update database and skip upload
        logger.info(f"[IMAGE_QUEUE] Image already exists in S3 for {image_type} {image_id}, skipping upload")
        
        # Update database with existing S3 URL
        if image_type == 'persona':
            persona = db.query(SimulationPersona).filter(
                SimulationPersona.id == image_id
            ).first()
            if persona:
                persona.image_url = existing_s3_url
                db.add(persona)
        else:
            scene = db.query(SimulationScene).filter(
                SimulationScene.id == image_id
            ).first()
            if scene:
                scene.image_url = existing_s3_url
                db.add(scene)
        
        db.commit()
        return False  # Not enqueued because already exists
    
    # ADDITIONAL CHECK: Use temp URL as deduplication key
    temp_url_key = f"upload:temp_url:{simulation_id}:{temp_url}"
    temp_url_value = redis_manager.get(temp_url_key)
    
    # Check if temp URL was already processed
    # Value can be: None (not processed), "enqueued" (in queue), or S3 URL (completed)
    if temp_url_value and temp_url_value != "enqueued" and is_s3_url(temp_url_value):
        # This temp URL was already uploaded - reuse the stored S3 URL
        logger.info(f"[IMAGE_QUEUE] Temp URL already uploaded, reusing S3 URL: {temp_url[:50]}...")
        
        # Update database with stored S3 URL
        if image_type == 'persona':
            persona = db.query(SimulationPersona).filter(
                SimulationPersona.id == image_id
            ).first()
            if persona:
                persona.image_url = temp_url_value
                db.add(persona)
                db.commit()
                logger.info(f"[IMAGE_QUEUE] Reused existing S3 URL for persona {image_id}: {temp_url_value}")
        else:
            scene = db.query(SimulationScene).filter(
                SimulationScene.id == image_id
            ).first()
            if scene:
                scene.image_url = temp_url_value
                db.add(scene)
                db.commit()
                logger.info(f"[IMAGE_QUEUE] Reused existing S3 URL for scene {image_id}: {temp_url_value}")
        return False
    
    elif temp_url_value == "enqueued":
        # Already enqueued, skip to prevent duplicate
        logger.info(f"[IMAGE_QUEUE] Temp URL already enqueued for this simulation, skipping: {temp_url[:50]}...")
        return False
    
    queue_key = "image_upload_queue"
    in_progress_key = f"upload:in_progress:{simulation_id}:{image_type}:{image_id}"
    
    # Check if already in progress
    if redis_manager.sismember("upload:in_progress_set", in_progress_key):
        logger.info(f"[IMAGE_QUEUE] Upload already in progress for {image_type} {image_id}")
        return False
    
    # Add to in-progress set
    redis_manager.sadd("upload:in_progress_set", in_progress_key)
    
    # Create job
    job = {
        "simulation_id": simulation_id,
        "image_type": image_type,
        "image_id": image_id,
        "temp_url": temp_url,
        "retry_count": 0,
        "created_at": datetime.utcnow().isoformat()
    }
    
    # Mark temp URL as enqueued (with TTL of 24 hours) - prevents duplicate enqueues
    redis_manager.set(temp_url_key, "enqueued", ttl=86400)
    
    # Enqueue
    redis_manager.lpush(queue_key, job)
    
    # Update status tracking (use lists consistently for all status keys)
    status_key = f"upload:status:{simulation_id}"
    pending_key = f"{status_key}:pending"
    
    # Ensure the key is a list (delete if it exists as wrong type from old code)
    if redis_manager.exists(pending_key):
        try:
            test_len = redis_manager.llen(pending_key)
            redis_manager.lpush(pending_key, in_progress_key)
        except Exception:
            logger.warning(f"[IMAGE_QUEUE] Deleting wrong-type key {pending_key} and recreating as list")
            redis_manager.delete(pending_key)
            redis_manager.lpush(pending_key, in_progress_key)
    else:
        redis_manager.lpush(pending_key, in_progress_key)
    
    logger.info(f"[IMAGE_QUEUE] Enqueued {image_type} {image_id} for simulation {simulation_id}")
    return True


async def handle_image_uploads(
    db: Session,
    repository,
    personas_to_upload: List[Dict[str, Any]],
    scenes_to_upload: List[Dict[str, Any]]
) -> Tuple[int, int]:
    """Handle image uploads to S3 - tries immediate upload first, then enqueues if needed."""
    logger.info(f"[IMAGE_STORAGE] Starting image uploads: {len(personas_to_upload)} personas, {len(scenes_to_upload)} scenes")
    
    # Filter out images that already exist in S3
    personas_to_upload_filtered = []
    for persona_info in personas_to_upload:
        temp_url = persona_info.get("temp_url")
        persona_id = persona_info.get("persona_id")
        scenario_id = persona_info.get("scenario_id")
        
        if temp_url and is_temporary_image_url(temp_url):
            # Check if already exists in S3
            file_exists = False
            for ext in ['jpg', 'png', 'webp']:
                s3_key = s3_service.get_persona_avatar_key(scenario_id, persona_id, ext)
                if await s3_service.file_exists(s3_key):
                    file_exists = True
                    # Update database with existing URL
                    persona = db.query(SimulationPersona).filter(
                        SimulationPersona.id == persona_id
                    ).first()
                    if persona:
                        persona.image_url = s3_service._build_public_url(s3_key)
                        db.add(persona)
                    break
            
            if not file_exists:
                personas_to_upload_filtered.append(persona_info)
    
    scenes_to_upload_filtered = []
    for scene_info in scenes_to_upload:
        temp_url = scene_info.get("temp_url")
        scene_id = scene_info.get("scene_id")
        scenario_id = scene_info.get("scenario_id")
        
        if temp_url and is_temporary_image_url(temp_url):
            # Check if already exists in S3
            file_exists = False
            for ext in ['jpg', 'png', 'webp']:
                s3_key = s3_service.get_scene_image_key(scenario_id, scene_id, ext)
                if await s3_service.file_exists(s3_key):
                    file_exists = True
                    # Update database with existing URL
                    scene = db.query(SimulationScene).filter(
                        SimulationScene.id == scene_id
                    ).first()
                    if scene:
                        scene.image_url = s3_service._build_public_url(s3_key)
                        db.add(scene)
                    break
            
            if not file_exists:
                scenes_to_upload_filtered.append(scene_info)
    
    # Commit any database updates from S3 checks
    if personas_to_upload_filtered or scenes_to_upload_filtered:
        db.commit()
    
    # Try uploading images immediately to prevent temporary URL expiration
    # BUT FIRST: Check if temp URLs were already processed (to avoid re-uploading when personas/scenes get new IDs)
    personas_uploaded_immediately = 0
    personas_to_enqueue = []
    
    for persona_info in personas_to_upload_filtered:
        temp_url = persona_info.get("temp_url")
        persona_id = persona_info.get("persona_id")
        scenario_id = persona_info.get("scenario_id")
        
        if temp_url and persona_id and scenario_id:
            # Check if this temp URL was already processed
            temp_url_key = f"upload:temp_url:{scenario_id}:{temp_url}"
            temp_url_status = redis_manager.get(temp_url_key)
            
            # Check if temp URL was already processed
            # Value can be: None (not processed), "enqueued" (in queue), or S3 URL (completed)
            if temp_url_status and temp_url_status != "enqueued" and is_s3_url(temp_url_status):
                # This temp URL was already uploaded - reuse the stored S3 URL
                logger.info(f"[IMAGE_STORAGE] Temp URL already processed for persona {persona_id}, reusing S3 URL")
                
                # Reuse stored S3 URL
                persona = db.query(SimulationPersona).filter(
                    SimulationPersona.id == persona_id
                ).first()
                if persona:
                    persona.image_url = temp_url_status
                    db.add(persona)
                    personas_uploaded_immediately += 1
                    logger.info(f"[IMAGE_STORAGE] Reused existing S3 URL for persona {persona_id}: {temp_url_status}")
                continue
            
            # Try immediate upload (either temp URL not processed, or couldn't find existing S3 URL)
            try:
                s3_url = await upload_persona_avatar_from_url(scenario_id, persona_id, temp_url)
                if s3_url:
                    persona = db.query(SimulationPersona).filter(
                        SimulationPersona.id == persona_id
                    ).first()
                    if persona:
                        persona.image_url = s3_url
                        db.add(persona)
                        personas_uploaded_immediately += 1
                        logger.info(f"[IMAGE_STORAGE] Immediately uploaded persona {persona_id} to S3: {s3_url}")
                        # Store S3 URL in Redis for future reuse
                        redis_manager.set(temp_url_key, s3_url, ttl=86400)
                    else:
                        personas_to_enqueue.append(persona_info)
                        logger.warning(f"[IMAGE_STORAGE] Persona {persona_id} not found in DB, enqueueing upload")
                else:
                    personas_to_enqueue.append(persona_info)
                    logger.warning(f"[IMAGE_STORAGE] Immediate upload failed for persona {persona_id}, enqueueing for retry")
            except Exception as e:
                personas_to_enqueue.append(persona_info)
                logger.error(f"[IMAGE_STORAGE] Error uploading persona {persona_id} immediately: {e}. Enqueueing for retry.")
    
    scenes_uploaded_immediately = 0
    scenes_to_enqueue = []
    
    for scene_info in scenes_to_upload_filtered:
        temp_url = scene_info.get("temp_url")
        scene_id = scene_info.get("scene_id")
        scenario_id = scene_info.get("scenario_id")
        
        if temp_url and scene_id and scenario_id:
            # Check if this temp URL was already processed
            temp_url_key = f"upload:temp_url:{scenario_id}:{temp_url}"
            temp_url_status = redis_manager.get(temp_url_key)
            
            # Check if temp URL was already processed
            # Value can be: None (not processed), "enqueued" (in queue), or S3 URL (completed)
            if temp_url_status and temp_url_status != "enqueued" and is_s3_url(temp_url_status):
                # This temp URL was already uploaded - reuse the stored S3 URL
                logger.info(f"[IMAGE_STORAGE] Temp URL already processed for scene {scene_id}, reusing S3 URL")
                
                # Reuse stored S3 URL
                scene = db.query(SimulationScene).filter(
                    SimulationScene.id == scene_id
                ).first()
                if scene:
                    scene.image_url = temp_url_status
                    db.add(scene)
                    scenes_uploaded_immediately += 1
                    logger.info(f"[IMAGE_STORAGE] Reused existing S3 URL for scene {scene_id}: {temp_url_status}")
                continue
            
            # Try immediate upload (either temp URL not processed, or couldn't find existing S3 URL)
            try:
                s3_url = await upload_scene_image_from_url(scenario_id, scene_id, temp_url)
                if s3_url:
                    scene = db.query(SimulationScene).filter(
                        SimulationScene.id == scene_id
                    ).first()
                    if scene:
                        scene.image_url = s3_url
                        db.add(scene)
                        scenes_uploaded_immediately += 1
                        logger.info(f"[IMAGE_STORAGE] Immediately uploaded scene {scene_id} to S3: {s3_url}")
                        # Store S3 URL in Redis for future reuse
                        redis_manager.set(temp_url_key, s3_url, ttl=86400)
                    else:
                        scenes_to_enqueue.append(scene_info)
                        logger.warning(f"[IMAGE_STORAGE] Scene {scene_id} not found in DB, enqueueing upload")
                else:
                    scenes_to_enqueue.append(scene_info)
                    logger.warning(f"[IMAGE_STORAGE] Immediate upload failed for scene {scene_id}, enqueueing for retry")
            except Exception as e:
                scenes_to_enqueue.append(scene_info)
                logger.error(f"[IMAGE_STORAGE] Error uploading scene {scene_id} immediately: {e}. Enqueueing for retry.")
    
    # Commit database updates from immediate uploads
    if personas_uploaded_immediately > 0 or scenes_uploaded_immediately > 0:
        db.commit()
        logger.info(f"[IMAGE_STORAGE] Immediately uploaded {personas_uploaded_immediately} personas and {scenes_uploaded_immediately} scenes to S3")
    
    # Enqueue remaining images that couldn't be uploaded immediately
    personas_enqueued = 0
    for persona_info in personas_to_enqueue:
        temp_url = persona_info.get("temp_url")
        persona_id = persona_info.get("persona_id")
        scenario_id = persona_info.get("scenario_id")
        if temp_url and persona_id and scenario_id:
            if await enqueue_image_upload(db, repository, scenario_id, "persona", persona_id, temp_url):
                personas_enqueued += 1
    
    scenes_enqueued = 0
    for scene_info in scenes_to_enqueue:
        temp_url = scene_info.get("temp_url")
        scene_id = scene_info.get("scene_id")
        scenario_id = scene_info.get("scenario_id")
        if temp_url and scene_id and scenario_id:
            if await enqueue_image_upload(db, repository, scenario_id, "scene", scene_id, temp_url):
                scenes_enqueued += 1
    
    if personas_enqueued > 0 or scenes_enqueued > 0:
        logger.info(f"[IMAGE_STORAGE] Enqueued {personas_enqueued} personas and {scenes_enqueued} scenes for background upload")
    
    return personas_uploaded_immediately + personas_enqueued, scenes_uploaded_immediately + scenes_enqueued


async def process_upload_job(job: Dict[str, Any], db: Session) -> bool:
    """
    Process a single image upload job.
    
    Args:
        job: Job dictionary with simulation_id, image_type, image_id, temp_url, retry_count
        db: Database session
        
    Returns:
        True if successful, False otherwise
    """
    simulation_id = job.get("simulation_id")
    image_type = job.get("image_type")  # 'persona' or 'scene'
    image_id = job.get("image_id")
    temp_url = job.get("temp_url")
    retry_count = job.get("retry_count", 0)
    
    in_progress_key = f"upload:in_progress:{simulation_id}:{image_type}:{image_id}"
    status_key = f"upload:status:{simulation_id}"
    
    try:
        logger.info(f"[IMAGE_WORKER] Processing {image_type} {image_id} for simulation {simulation_id} (attempt {retry_count + 1})")
        
        # Check if already exists in S3 (deduplication)
        existing_url = None
        for ext in ['jpg', 'png', 'webp']:
            if image_type == 'persona':
                s3_key = s3_service.get_persona_avatar_key(simulation_id, image_id, ext)
            else:
                s3_key = s3_service.get_scene_image_key(simulation_id, image_id, ext)
            
            if await s3_service.file_exists(s3_key):
                existing_url = s3_service._build_public_url(s3_key)
                logger.info(f"[IMAGE_WORKER] Image already exists in S3: {s3_key}")
                break
        
        if existing_url:
            # Update database with existing URL
            if image_type == 'persona':
                persona = db.query(SimulationPersona).filter(
                    SimulationPersona.id == image_id
                ).first()
                if persona:
                    persona.image_url = existing_url
                    db.add(persona)
            else:
                scene = db.query(SimulationScene).filter(
                    SimulationScene.id == image_id
                ).first()
                if scene:
                    scene.image_url = existing_url
                    db.add(scene)
            
            db.commit()
            
            # Mark as complete (image already existed in S3)
            redis_manager.srem("upload:in_progress_set", in_progress_key)
            redis_manager.lpush(f"{status_key}:completed", in_progress_key)
            # Remove from pending list using lrem (atomic operation)
            redis_manager.lrem(f"{status_key}:pending", 1, in_progress_key)
            
            # Mark temp URL as completed and store S3 URL for reuse
            temp_url_key = f"upload:temp_url:{simulation_id}:{temp_url}"
            redis_manager.set(temp_url_key, existing_url, ttl=86400)  # Store S3 URL instead of "completed"
            
            logger.info(f"[IMAGE_WORKER] Updated database with existing S3 URL for {image_type} {image_id}")
            return True
        
        # Upload from temp URL
        async with UPLOAD_SEMAPHORE:
            if image_type == 'persona':
                s3_url = await upload_persona_avatar_from_url(simulation_id, image_id, temp_url)
            else:
                s3_url = await upload_scene_image_from_url(simulation_id, image_id, temp_url)
        
        if s3_url:
            # Update database with S3 URL
            if image_type == 'persona':
                persona = db.query(SimulationPersona).filter(
                    SimulationPersona.id == image_id
                ).first()
                if persona:
                    persona.image_url = s3_url
                    db.add(persona)
            else:
                scene = db.query(SimulationScene).filter(
                    SimulationScene.id == image_id
                ).first()
                if scene:
                    scene.image_url = s3_url
                    db.add(scene)
            
            db.commit()
            
            # Mark as complete (successfully uploaded)
            redis_manager.srem("upload:in_progress_set", in_progress_key)
            redis_manager.lpush(f"{status_key}:completed", in_progress_key)
            # Remove from pending list using lrem (atomic operation)
            redis_manager.lrem(f"{status_key}:pending", 1, in_progress_key)
            
            # Mark temp URL as completed and store S3 URL for reuse
            temp_url_key = f"upload:temp_url:{simulation_id}:{temp_url}"
            redis_manager.set(temp_url_key, s3_url, ttl=86400)  # Store S3 URL instead of "completed"
            
            logger.info(f"[IMAGE_WORKER] Successfully uploaded {image_type} {image_id} to S3: {s3_url}")
            return True
        else:
            raise Exception("Upload returned None - upload failed")
            
    except Exception as e:
        logger.error(f"[IMAGE_WORKER] Error processing {image_type} {image_id}: {str(e)}")
        
        # Retry logic
        if retry_count < MAX_RETRIES - 1:
            # Exponential backoff: 2^retry_count seconds
            wait_time = 2 ** retry_count
            logger.info(f"[IMAGE_WORKER] Retrying {image_type} {image_id} in {wait_time}s (attempt {retry_count + 2}/{MAX_RETRIES})")
            
            # Re-enqueue with incremented retry count
            job["retry_count"] = retry_count + 1
            await asyncio.sleep(wait_time)
            redis_manager.lpush(QUEUE_KEY, job)
            return False
        else:
            # Max retries reached - mark as failed
            logger.error(f"[IMAGE_WORKER] Max retries reached for {image_type} {image_id}")
            redis_manager.srem("upload:in_progress_set", in_progress_key)
            redis_manager.lpush(f"{status_key}:failed", {
                "image_type": image_type,
                "image_id": image_id,
                "error": str(e),
                "failed_at": datetime.utcnow().isoformat()
            })
            # Remove from pending list using lrem (atomic operation)
            redis_manager.lrem(f"{status_key}:pending", 1, in_progress_key)
            return False


async def process_queue():
    """Continuously poll Redis queue and process upload jobs."""
    logger.info("[IMAGE_WORKER] Starting image upload worker...")
    
    try:
        while True:
            try:
                # Dequeue job from Redis
                job = redis_manager.rpop(QUEUE_KEY)
                
                if job:
                    # Create a fresh DB session for this job
                    db = SessionLocal()
                    try:
                        await process_upload_job(job, db)
                    finally:
                        # Always close the session after processing
                        db.close()
                else:
                    # No jobs available, wait a bit before checking again
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"[IMAGE_WORKER] Error in queue processing loop: {str(e)}")
                await asyncio.sleep(5)  # Wait before retrying
                
    except KeyboardInterrupt:
        logger.info("[IMAGE_WORKER] Worker stopped by user")


def run_worker():
    """Entry point for running the worker as a separate process."""
    asyncio.run(process_queue())


if __name__ == "__main__":
    run_worker()
