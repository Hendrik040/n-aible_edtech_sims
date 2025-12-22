"""
Queue Decision Logic.

Determines when to use queue vs direct processing for simulation requests.
"""

import os
import logging
from common.services.simulation_queue_service import get_queue_length, get_in_progress_count
from common.utils.concurrency import stream_semaphore

logger = logging.getLogger(__name__)

# Configuration via environment variables
QUEUE_THRESHOLD_STREAMS = int(os.getenv("QUEUE_THRESHOLD_STREAMS", "8"))  # Use queue if <8 slots available (20% of 40)
QUEUE_THRESHOLD_LENGTH = int(os.getenv("QUEUE_THRESHOLD_LENGTH", "10"))  # Use queue if >10 pending jobs
FORCE_QUEUE_MODE = os.getenv("FORCE_QUEUE_MODE", "false").lower() == "true"  # Force queue mode (for testing)

# Import MAX_CONCURRENT_JOBS from worker (with fallback)
try:
    from workers.simulation_worker import MAX_CONCURRENT_JOBS
except ImportError:
    MAX_CONCURRENT_JOBS = 5  # Default fallback


def should_use_queue() -> bool:
    """
    Determine if a simulation request should be queued or processed directly.
    
    Returns:
        True if request should be queued, False for direct processing
    """
    # Force queue mode (for testing/debugging)
    if FORCE_QUEUE_MODE:
        logger.debug("[QUEUE_DECISION] Force queue mode enabled")
        return True
    
    # Check available stream slots
    available_slots = stream_semaphore._value
    if available_slots < QUEUE_THRESHOLD_STREAMS:
        logger.info(
            f"[QUEUE_DECISION] Using queue: low stream capacity "
            f"(available={available_slots}, threshold={QUEUE_THRESHOLD_STREAMS})"
        )
        return True
    
    # Check queue length
    queue_length = get_queue_length()
    if queue_length > QUEUE_THRESHOLD_LENGTH:
        logger.info(
            f"[QUEUE_DECISION] Using queue: high queue length "
            f"(length={queue_length}, threshold={QUEUE_THRESHOLD_LENGTH})"
        )
        return True
    
    # Check in-progress jobs
    in_progress = get_in_progress_count()
    if in_progress > MAX_CONCURRENT_JOBS * 2:  # If more than 2x worker capacity
        logger.info(
            f"[QUEUE_DECISION] Using queue: high in-progress count "
            f"(in_progress={in_progress})"
        )
        return True
    
    # Default: process directly
    return False

