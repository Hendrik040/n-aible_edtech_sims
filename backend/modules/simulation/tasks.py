"""
Queue Decision Logic.

Determines when to use queue vs direct processing for simulation requests.
"""

import os
import logging
from typing import Final

from common.services.simulation_queue_service import (
    get_queue_length,
    get_in_progress_count,
)
from common.utils.concurrency import stream_semaphore

try:
    from modules.simulation.tasks import MAX_CONCURRENT_JOBS
except ImportError:
    MAX_CONCURRENT_JOBS = 5  # conservative fallback

logger = logging.getLogger(__name__)

# If available stream slots fall below this, queue
QUEUE_THRESHOLD_STREAMS: Final[int] = int(
    os.getenv("QUEUE_THRESHOLD_STREAMS", "8")
)

# If pending queue length exceeds this, queue
QUEUE_THRESHOLD_LENGTH: Final[int] = int(
    os.getenv("QUEUE_THRESHOLD_LENGTH", "10")
)

# Hard override to always queue (safe-mode / testing)
FORCE_QUEUE_MODE: Final[bool] = (
    os.getenv("FORCE_QUEUE_MODE", "false").lower() == "true"
)


def has_stream_capacity() -> bool:
    """
    Safely check whether this replica has stream capacity.

    We attempt a non-blocking acquire to avoid relying on
    private semaphore internals (_value), which are unsafe
    under concurrency.
    """
    acquired = stream_semaphore.acquire(blocking=False)
    if acquired:
        stream_semaphore.release()
    return acquired


def should_use_queue() -> bool:
    """
    Determine whether a simulation request should be queued
    or processed directly.

    Returns:
        True  -> enqueue the request
        False -> process directly
    """

    # Forced queue mode (debug / safety switch)
    if FORCE_QUEUE_MODE:
        logger.warning("[QUEUE_DECISION] Force queue mode enabled")
        return True

    try:
        queue_length = get_queue_length()
        if queue_length >= QUEUE_THRESHOLD_LENGTH:
            logger.info(
                "[QUEUE_DECISION] Using queue due to queue backlog "
                f"(length={queue_length}, threshold={QUEUE_THRESHOLD_LENGTH})"
            )
            return True
    except Exception:
        logger.exception("[QUEUE_DECISION] Failed to read queue length; defaulting to queue")
        return True

    try:
        in_progress = get_in_progress_count()
        if in_progress >= MAX_CONCURRENT_JOBS:
            logger.info(
                "[QUEUE_DECISION] Using queue due to worker saturation "
                f"(in_progress={in_progress}, max={MAX_CONCURRENT_JOBS})"
            )
            return True
    except Exception:
        logger.exception("[QUEUE_DECISION] Failed to read in-progress count; defaulting to queue")
        return True

    if not has_stream_capacity():
        logger.info(
            "[QUEUE_DECISION] Using queue due to local stream saturation"
        )
        return True

    return False
