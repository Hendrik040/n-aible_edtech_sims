"""
Global async concurrency controls for heavy operations.

This module provides process-wide semaphores that cap:
- The number of active SSE simulation streams.
- The number of concurrent AI-heavy persona calls.

Limits are intentionally conservative by default and can be tuned via env vars:
- SIMULATION_MAX_STREAMS_PER_PROCESS (default: 50)
- SIMULATION_MAX_AI_CALLS_PER_PROCESS (default: 32)
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


_max_streams = _env_int("SIMULATION_MAX_STREAMS_PER_PROCESS", 50)
_max_ai_calls = _env_int("SIMULATION_MAX_AI_CALLS_PER_PROCESS", 32)

# Global semaphores
stream_semaphore = asyncio.Semaphore(_max_streams)
ai_semaphore = asyncio.Semaphore(_max_ai_calls)


async def _try_acquire(semaphore: asyncio.Semaphore, timeout: float) -> bool:
    """Try to acquire a semaphore within a timeout, returning False on timeout."""
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        return False


async def acquire_stream_slot(timeout: float = 0.1) -> bool:
    """Attempt to acquire a slot for a streaming simulation request."""
    return await _try_acquire(stream_semaphore, timeout=timeout)


def release_stream_slot() -> None:
    """Release a previously acquired stream slot."""
    stream_semaphore.release()


@asynccontextmanager
async def ai_concurrency_slot(timeout: float = 0.1) -> AsyncIterator[bool]:
    """
    Context manager that acquires/releases an AI concurrency slot.

    Yields:
        acquired (bool): True if a slot was acquired, False if timed out.
    """
    acquired = await _try_acquire(ai_semaphore, timeout=timeout)
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

