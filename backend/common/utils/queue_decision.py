"""
Queue Decision Logic.

Determines when to use queue vs direct processing for simulation requests.
"""

import os
import logging
from common.services.simulation_queue_service import get_queue_length, get_worker_in_progress_count
from common.utils.concurrency import stream_semaphore

logger = logging.getLogger(__name__)

# Configuration via environment variables
QUEUE_THRESHOLD_STREAMS = int(os.getenv("QUEUE_THRESHOLD_STREAMS", "8"))  # Use queue if <8 slots available (20% of 40)
QUEUE_THRESHOLD_LENGTH = int(os.getenv("QUEUE_THRESHOLD_LENGTH", "10"))  # Use queue if >10 pending jobs
FORCE_QUEUE_MODE = os.getenv("FORCE_QUEUE_MODE", "false").lower() == "true"  # Force queue mode (for testing)

# Max concurrent jobs per worker (must match modules.simulation.tasks.MAX_CONCURRENT_JOBS)
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "5"))


async def should_use_queue() -> bool:
    """
    Determine if a simulation request should be queued or processed directly.
    
    Returns:
        True if request should be queued, False for direct processing
    """
    # Force queue mode (for testing/debugging)
    if FORCE_QUEUE_MODE:
        logger.warning("[QUEUE_DECISION] Force queue mode enabled - ALL requests will be queued")
        return True
    
    # Check queue length (with error handling)
    try:
        queue_length = get_queue_length()
        if queue_length >= QUEUE_THRESHOLD_LENGTH:
            logger.info(
                "[QUEUE_DECISION] Using queue due to queue backlog "
                f"(length={queue_length}, threshold={QUEUE_THRESHOLD_LENGTH})"
            )
            return True
    except Exception as e:
        # On error, log but default to direct processing (safer for high concurrency)
        logger.warning(
            f"[QUEUE_DECISION] Failed to read queue length: {e}; "
            "defaulting to direct processing (safer than queuing everything)"
        )
        # Continue to next check instead of returning True
    
    # Check in-progress jobs for THIS worker only (no KEYS command needed)
    try:
        in_progress = get_worker_in_progress_count()
        if in_progress >= MAX_CONCURRENT_JOBS:
            logger.info(
                "[QUEUE_DECISION] Using queue due to worker saturation "
                f"(this_worker_in_progress={in_progress}, max={MAX_CONCURRENT_JOBS})"
            )
            return True
    except Exception as e:
        # On error, log but default to direct processing (safer for high concurrency)
        logger.warning(
            f"[QUEUE_DECISION] Failed to read in-progress count: {e}; "
            "defaulting to direct processing (safer than queuing everything)"
        )
        # Continue to next check instead of returning True
    
    # Check available stream slots (using thread-safe API)
    try:
        available_slots = await stream_semaphore.available()
        if available_slots < QUEUE_THRESHOLD_STREAMS:
            logger.info(
                f"[QUEUE_DECISION] Using queue: low stream capacity "
                f"(available={available_slots}, threshold={QUEUE_THRESHOLD_STREAMS})"
            )
            return True
    except Exception as e:
        # On error, log but default to direct processing (safer for high concurrency)
        logger.warning(
            f"[QUEUE_DECISION] Failed to check stream capacity: {e}; "
            "defaulting to direct processing (safer than queuing everything)"
        )
        # Continue instead of returning True
    
    # Default: process directly (prefer direct processing for better responsiveness)
    logger.debug(
        f"[QUEUE_DECISION] Processing directly "
        f"(queue_threshold={QUEUE_THRESHOLD_LENGTH}, "
        f"stream_threshold={QUEUE_THRESHOLD_STREAMS}, "
        f"max_jobs={MAX_CONCURRENT_JOBS})"
    )
    return False

