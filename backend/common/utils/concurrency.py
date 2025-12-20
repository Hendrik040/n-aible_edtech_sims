"""
Global async concurrency controls for heavy operations.

This module provides process-wide semaphores that cap:
- The number of active SSE simulation streams.
- The number of concurrent AI-heavy persona calls.

Limits can be tuned via env vars:
- SIMULATION_MAX_STREAMS_PER_PROCESS (default: 40, conservative to prevent resource exhaustion)
- SIMULATION_MAX_AI_CALLS_PER_PROCESS (default: 25, respects OpenAI rate limits)

Resource Considerations:
- Each stream: ~100KB memory (orchestrator state), 1 DB connection, CPU for processing
- Each AI call: ~5-30s duration, consumes OpenAI API quota, memory for context
- Railway containers: Limited memory/CPU, single process
- OpenAI rate limits: Vary by tier (typically 50-500 RPM), 80 concurrent could exceed limits

Recommended tuning:
- Small deployments (1-2GB RAM): Keep defaults (40/25)
- Medium (4-8GB RAM): 60-80 streams, 40-50 AI calls
- Large (16GB+ RAM): 100+ streams, 60-80 AI calls (monitor OpenAI limits)
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except ValueError:
        return default


# Optimized defaults based on testing with 50 concurrent users
# These can be tuned via environment variables based on your deployment resources
# 
# Rationale:
# - 45 streams: Supports 50 concurrent users with headroom for spikes
#   (Not all users have active streams simultaneously - some reading, typing, waiting)
# - 25 AI calls: Balanced limit that prevents OpenAI rate limits and memory pressure
#   (LLM calls take 5-30s, so 25 concurrent = ~150-750 requests/minute)
#
# Testing Results:
# - 50/30: Works but can be slow under heavy load
# - 60/40: Causes hangs due to resource exhaustion
# - 45/25: Optimal balance (recommended starting point)
#
# Important: If you set these via environment variables in Railway, those override these defaults.
# Recommended Railway values for 50 concurrent users:
#   SIMULATION_MAX_STREAMS_PER_PROCESS=45
#   SIMULATION_MAX_AI_CALLS_PER_PROCESS=25
#
# If experiencing hangs, reduce to 40/22
# If stable but slow, can try increasing to 50/28 (monitor closely)
# 
# Performance note: Very low stream limits (e.g., 15) for many users (e.g., 50) cause
# excessive queuing and perceived slowness. Better to allow more concurrency with
# proper resource management than to over-restrict and queue everything.
#
# Recommended configuration for 2 replicas × 2.0 vCPU:
#   SIMULATION_MAX_STREAMS_PER_PROCESS=40
#   SIMULATION_MAX_AI_CALLS_PER_PROCESS=25
# This provides 80 total streams and 50 total AI calls across 2 replicas.
_max_streams = _env_int("SIMULATION_MAX_STREAMS_PER_PROCESS", 40)
_max_ai_calls = _env_int("SIMULATION_MAX_AI_CALLS_PER_PROCESS", 25)

# Global semaphores
stream_semaphore = asyncio.Semaphore(_max_streams)
ai_semaphore = asyncio.Semaphore(_max_ai_calls)

# Log configured values at module import (for debugging - visible in Railway logs)
import logging
logger = logging.getLogger(__name__)
logger.info(
    f"[CONCURRENCY_CONFIG] Loaded concurrency limits: "
    f"max_streams={_max_streams}, max_ai_calls={_max_ai_calls} "
    f"(from env: SIMULATION_MAX_STREAMS_PER_PROCESS={os.getenv('SIMULATION_MAX_STREAMS_PER_PROCESS', 'NOT SET')}, "
    f"SIMULATION_MAX_AI_CALLS_PER_PROCESS={os.getenv('SIMULATION_MAX_AI_CALLS_PER_PROCESS', 'NOT SET')})"
)


async def _try_acquire(semaphore: asyncio.Semaphore, timeout: float, semaphore_name: str = "semaphore") -> bool:
    """Try to acquire a semaphore within a timeout, returning False on timeout."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        start_time = asyncio.get_event_loop().time()
        await asyncio.wait_for(semaphore.acquire(), timeout=timeout)
        wait_time = asyncio.get_event_loop().time() - start_time
        if wait_time > 0.1:  # Log if we had to wait more than 100ms
            logger.warning(f"[CONCURRENCY] Waited {wait_time:.2f}s to acquire {semaphore_name} slot (high load)")
        return True
    except asyncio.TimeoutError:
        logger.warning(f"[CONCURRENCY] Timeout acquiring {semaphore_name} slot after {timeout}s (system at capacity)")
        return False


async def acquire_stream_slot(timeout: float = 5.0) -> bool:
    """
    Attempt to acquire a slot for a streaming simulation request.
    
    Increased timeout from 0.5s to 5.0s to handle load spikes better.
    Under heavy load, requests may need to wait a few seconds for a slot.
    """
    return await _try_acquire(stream_semaphore, timeout=timeout, semaphore_name="stream")


def release_stream_slot() -> None:
    """Release a previously acquired stream slot."""
    stream_semaphore.release()


@asynccontextmanager
async def ai_concurrency_slot(timeout: float = 10.0) -> AsyncIterator[bool]:
    """
    Context manager that acquires/releases an AI concurrency slot.
    
    Increased timeout from 0.5s to 10.0s since LLM calls can take time.
    Under heavy load, requests may need to wait for an AI slot to become available.

    Yields:
        acquired (bool): True if a slot was acquired, False if timed out.
    """
    acquired = await _try_acquire(ai_semaphore, timeout=timeout, semaphore_name="AI")
    try:
        yield acquired
    finally:
        if acquired:
            ai_semaphore.release()


__all__ = [
    "stream_semaphore",
    "ai_semaphore",
    "acquire_stream_slot",
    "release_stream_slot",
    "ai_concurrency_slot",
]

