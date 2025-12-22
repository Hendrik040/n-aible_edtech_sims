"""
Simulation Queue Service.

Handles enqueueing and managing simulation chat requests in Redis queue.
Similar pattern to image upload queue in modules/publishing/tasks.py
"""

import json
import uuid
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from common.services.cache_service import redis_manager

logger = logging.getLogger(__name__)

# Queue configuration
QUEUE_KEY = "simulation_queue"
JOB_DATA_PREFIX = "simulation:job:"
JOB_STATUS_PREFIX = "simulation:status:"
JOB_RESULT_PREFIX = "simulation:result:"
IN_PROGRESS_SET = "simulation:in_progress"

# Job statuses
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

# Result TTL: 1 hour
RESULT_TTL = 3600


def _json_serializer(obj):
    """JSON serializer for datetime and other objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def _safe_json_parse(data: Any, default: Any = None) -> Any:
    """
    Safely parse JSON data that may be a dict, str, bytes, or None.
    
    Args:
        data: Data to parse (may be dict, str, bytes, or None)
        default: Default value to return if parsing fails (default: {})
        
    Returns:
        Parsed dictionary or default value
    """
    if default is None:
        default = {}
    
    # Handle None
    if data is None:
        return default
    
    # If already a dict, return it directly
    if isinstance(data, dict):
        return data
    
    # If bytes, decode to string first
    if isinstance(data, bytes):
        try:
            data = data.decode('utf-8')
        except UnicodeDecodeError:
            logger.warning(f"[SIMULATION_QUEUE] Failed to decode bytes data")
            return default
    
    # If string, try to parse as JSON
    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            logger.warning(f"[SIMULATION_QUEUE] Failed to parse JSON string: {e}")
            return default
    
    # Unknown type
    logger.warning(f"[SIMULATION_QUEUE] Unexpected data type for JSON parsing: {type(data)}")
    return default


async def enqueue_simulation_request(
    user_id: int,
    user_progress_id: int,
    message: str,
    scene_id: Optional[int] = None
) -> str:
    """
    Enqueue a simulation chat request.
    
    Args:
        user_id: ID of the user making the request
        user_progress_id: ID of the user progress
        message: User's message
        scene_id: Optional scene ID
        
    Returns:
        job_id: Unique job identifier
    """
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    
    # Create job data
    job_data = {
        "job_id": job_id,
        "user_id": user_id,
        "user_progress_id": user_progress_id,
        "message": message,
        "scene_id": scene_id,
        "created_at": datetime.utcnow().isoformat(),
        "retry_count": 0,
    }
    
    # Store job data in Redis (TTL: 24 hours)
    job_data_key = f"{JOB_DATA_PREFIX}{job_id}"
    redis_manager.set(job_data_key, json.dumps(job_data, default=_json_serializer), ttl=86400)
    
    # Set initial status
    status_key = f"{JOB_STATUS_PREFIX}{job_id}"
    redis_manager.set(status_key, STATUS_PENDING, ttl=86400)
    
    # Add to queue
    redis_manager.lpush(QUEUE_KEY, job_id)
    
    logger.info(
        f"[SIMULATION_QUEUE] Enqueued simulation request: job_id={job_id}, "
        f"user_id={user_id}, user_progress_id={user_progress_id}"
    )
    
    return job_id


async def get_job_status(job_id: str) -> Dict[str, Any]:
    """
    Get the status of a simulation job.
    
    Args:
        job_id: Job identifier
        
    Returns:
        Dictionary with job status and metadata
    """
    status_key = f"{JOB_STATUS_PREFIX}{job_id}"
    status = redis_manager.get(status_key)
    
    if not status:
        return {
            "status": "not_found",
            "job_id": job_id,
            "error": "Job not found or expired"
        }
    
    # Get job data
    job_data_key = f"{JOB_DATA_PREFIX}{job_id}"
    job_data_str = redis_manager.get(job_data_key)
    job_data = _safe_json_parse(job_data_str, default={})
    
    # Get queue position (if pending)
    queue_position = None
    if status == STATUS_PENDING:
        queue_items = redis_manager.lrange(QUEUE_KEY, 0, -1)
        try:
            queue_position = queue_items.index(job_id) + 1
        except ValueError:
            queue_position = None
    
    result = {
        "job_id": job_id,
        "status": status,
        "created_at": job_data.get("created_at"),
        "queue_position": queue_position,
        "user_id": job_data.get("user_id"),  # Include user_id for ownership verification
    }
    
    # Add result if completed
    if status == STATUS_COMPLETED:
        result_key = f"{JOB_RESULT_PREFIX}{job_id}"
        result_data = redis_manager.get(result_key)
        if result_data:
            result["has_result"] = True
        else:
            result["has_result"] = False
    
    # Add error if failed
    if status == STATUS_FAILED:
        result_key = f"{JOB_RESULT_PREFIX}{job_id}"
        result_data = redis_manager.get(result_key)
        if result_data:
            try:
                error_data = json.loads(result_data)
                result["error"] = error_data.get("error", "Unknown error")
            except (json.JSONDecodeError, TypeError):
                result["error"] = "Processing failed"
    
    return result


async def get_job_result(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the result of a completed simulation job.
    
    Args:
        job_id: Job identifier
        
    Returns:
        Dictionary with job result data and user_id, or None if not found/completed
    """
    # Check status first
    status_key = f"{JOB_STATUS_PREFIX}{job_id}"
    status = redis_manager.get(status_key)
    
    if status != STATUS_COMPLETED:
        return None
    
    # Get job data for user_id
    job_data_key = f"{JOB_DATA_PREFIX}{job_id}"
    job_data_str = redis_manager.get(job_data_key)
    job_data = _safe_json_parse(job_data_str, default={})
    
    # Get result
    result_key = f"{JOB_RESULT_PREFIX}{job_id}"
    result_data = redis_manager.get(result_key)
    
    if not result_data:
        return None
    
    result = _safe_json_parse(result_data)
    if not isinstance(result, dict):
        logger.error(f"[SIMULATION_QUEUE] Result is not a dict for job {job_id}")
        return None
    
    # Include user_id for ownership verification
    result["user_id"] = job_data.get("user_id")
    return result


async def dequeue_job() -> Optional[Dict[str, Any]]:
    """
    Dequeue a job from the queue (used by worker).
    
    Returns:
        Job data dictionary, or None if queue is empty
    """
    # Pop from right side of queue (FIFO)
    job_id = redis_manager.rpop(QUEUE_KEY)
    
    if not job_id:
        return None
    
    # Get job data
    job_data_key = f"{JOB_DATA_PREFIX}{job_id}"
    job_data_str = redis_manager.get(job_data_key)
    
    if not job_data_str:
        logger.warning(
            f"[SIMULATION_QUEUE] Job data not found for job_id={job_id}, "
            f"re-queuing job to prevent permanent loss"
        )
        # Re-queue the job ID to prevent permanent loss
        try:
            redis_manager.lpush(QUEUE_KEY, job_id)
            logger.info(f"[SIMULATION_QUEUE] Re-queued job_id={job_id} after missing data")
        except Exception as e:
            logger.error(f"[SIMULATION_QUEUE] Failed to re-queue job {job_id}: {e}")
        return None
    
    job_data = _safe_json_parse(job_data_str, default=None)
    if job_data is None or not isinstance(job_data, dict):
        logger.error(
            f"[SIMULATION_QUEUE] Failed to parse job data for {job_id}, "
            f"re-queuing job to prevent permanent loss"
        )
        # Re-queue the job ID to prevent permanent loss
        try:
            redis_manager.lpush(QUEUE_KEY, job_id)
            logger.info(f"[SIMULATION_QUEUE] Re-queued job_id={job_id} after parse failure")
        except Exception as e:
            logger.error(f"[SIMULATION_QUEUE] Failed to re-queue job {job_id}: {e}")
        return None
    
    # Update status to processing
    status_key = f"{JOB_STATUS_PREFIX}{job_id}"
    redis_manager.set(status_key, STATUS_PROCESSING, ttl=86400)
    
    # Add to in-progress set (to track actively processing jobs)
    redis_manager.sadd(IN_PROGRESS_SET, job_id)
    
    return job_data


async def mark_job_completed(job_id: str, result: Dict[str, Any]) -> None:
    """
    Mark a job as completed and store the result.
    
    Args:
        job_id: Job identifier
        result: Result data to store
    """
    # Update status
    status_key = f"{JOB_STATUS_PREFIX}{job_id}"
    redis_manager.set(status_key, STATUS_COMPLETED, ttl=86400)
    
    # Store result
    result_key = f"{JOB_RESULT_PREFIX}{job_id}"
    redis_manager.set(
        result_key,
        json.dumps(result, default=_json_serializer),
        ttl=RESULT_TTL
    )
    
    # Remove from in-progress set
    redis_manager.srem(IN_PROGRESS_SET, job_id)
    
    logger.info(f"[SIMULATION_QUEUE] Job completed: job_id={job_id}")


async def mark_job_failed(job_id: str, error: str, retry: bool = False) -> None:
    """
    Mark a job as failed.
    
    Args:
        job_id: Job identifier
        error: Error message
        retry: Whether to retry the job
    """
    if retry:
        # Remove from in-progress set before re-enqueuing
        try:
            redis_manager.srem(IN_PROGRESS_SET, job_id)
        except Exception as e:
            logger.warning(f"[SIMULATION_QUEUE] Failed to remove job {job_id} from in-progress set: {e}")
        
        # Re-enqueue with incremented retry count
        job_data_key = f"{JOB_DATA_PREFIX}{job_id}"
        job_data_str = redis_manager.get(job_data_key)
        
        if job_data_str:
            job_data = _safe_json_parse(job_data_str, default=None)
            if job_data and isinstance(job_data, dict):
                job_data["retry_count"] = job_data.get("retry_count", 0) + 1
                
                # Max 3 retries
                if job_data["retry_count"] < 3:
                    redis_manager.set(
                        job_data_key,
                        json.dumps(job_data, default=_json_serializer),
                        ttl=86400
                    )
                    redis_manager.set(f"{JOB_STATUS_PREFIX}{job_id}", STATUS_PENDING, ttl=86400)
                    redis_manager.lpush(QUEUE_KEY, job_id)
                    logger.info(f"[SIMULATION_QUEUE] Retrying job: job_id={job_id}, retry_count={job_data['retry_count']}")
                    return
    
    # Mark as failed
    status_key = f"{JOB_STATUS_PREFIX}{job_id}"
    redis_manager.set(status_key, STATUS_FAILED, ttl=86400)
    
    # Store error in result
    result_key = f"{JOB_RESULT_PREFIX}{job_id}"
    redis_manager.set(
        result_key,
        json.dumps({"error": error}, default=_json_serializer),
        ttl=RESULT_TTL
    )
    
    # Remove from in-progress set
    redis_manager.srem(IN_PROGRESS_SET, job_id)
    
    logger.error(f"[SIMULATION_QUEUE] Job failed: job_id={job_id}, error={error}")


def get_queue_length() -> int:
    """Get the current queue length."""
    return redis_manager.llen(QUEUE_KEY)


def get_in_progress_count() -> int:
    """Get the number of jobs currently in progress."""
    return redis_manager.scard(IN_PROGRESS_SET)

