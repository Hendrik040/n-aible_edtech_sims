"""Password hashing helpers.

Provides both synchronous and asynchronous password hashing/verification.
Use async versions in FastAPI endpoints to avoid blocking the event loop.
"""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Thread pool for CPU-bound bcrypt operations (shared across all calls)
# bcrypt is memory-intensive (~4KB per hash), so we limit parallel hashing
_max_workers = int(os.getenv("BCRYPT_THREAD_POOL_SIZE", "4"))
_executor = ThreadPoolExecutor(max_workers=_max_workers)


def hash_password(password: str) -> str:
    """Hash a plaintext password (synchronous).
    
    Use for migrations, scripts, or non-async contexts.
    For FastAPI endpoints, use hash_password_async() instead.
    """
    return _pwd_context.hash(password)


async def hash_password_async(password: str) -> str:
    """Hash a plaintext password asynchronously.
    
    Runs bcrypt in a thread pool to avoid blocking the async event loop.
    Use this in async endpoints (FastAPI routes).
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _pwd_context.hash, password)


def verify_password(password: str, password_hash: str) -> bool:
    """Check whether the password matches the stored hash (synchronous).
    
    Use for non-async contexts.
    For FastAPI endpoints, use verify_password_async() instead.
    """
    return _pwd_context.verify(password, password_hash)


async def verify_password_async(password: str, password_hash: str) -> bool:
    """Verify password asynchronously.
    
    Runs bcrypt verification in a thread pool to avoid blocking the event loop.
    Use this in async endpoints (FastAPI routes).
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _pwd_context.verify, password, password_hash)


__all__ = [
    "hash_password",
    "hash_password_async",
    "verify_password",
    "verify_password_async",
]
