"""Security helpers: rate limiting.

Provides a small fixed-window rate limiter backed by Redis, exposed as a
FastAPI dependency factory. Used to throttle abuse-prone auth endpoints
(login, password reset, email lookup, OAuth).

Design notes:
- Fixed-window counting via an atomic Redis INCR + EXPIRE (see
  ``RedisManager.increment``). Simple and good enough for abuse mitigation.
- Keyed by client IP + a caller-supplied scope, so different endpoints get
  independent budgets.
- Fail-open: if Redis is unavailable we allow the request (and log a warning)
  rather than locking every user out. Availability is preferred over a hard
  block, since the primary auth vulnerabilities are fixed independently.
"""

import logging
from typing import Callable

from fastapi import HTTPException, Request, status

from common.services.cache_service import redis_manager

logger = logging.getLogger(__name__)


def _client_ip(request: Request) -> str:
    """Best-effort client IP, honoring the first X-Forwarded-For hop.

    Railway terminates TLS at a proxy, so the real client IP arrives in
    X-Forwarded-For. We take the first entry (the original client).
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def rate_limit(max_requests: int, window_seconds: int, scope: str) -> Callable:
    """Build a FastAPI dependency that enforces a fixed-window rate limit.

    Args:
        max_requests: Allowed requests per window per client.
        window_seconds: Window length in seconds.
        scope: Logical name for the limited action (keeps budgets independent).
    """

    async def _dependency(request: Request) -> None:
        ip = _client_ip(request)
        key = f"ratelimit:{scope}:{ip}"

        count = redis_manager.increment(key, ttl=window_seconds)
        if count is None:
            # Redis unavailable - fail open but record it.
            logger.warning(
                "[RATELIMIT] Redis unavailable; allowing request for scope=%s ip=%s",
                scope, ip,
            )
            return

        if count > max_requests:
            logger.warning(
                "[RATELIMIT] Limit exceeded scope=%s ip=%s count=%s/%s",
                scope, ip, count, max_requests,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please wait a moment and try again.",
                headers={"Retry-After": str(window_seconds)},
            )

    return _dependency


__all__ = ["rate_limit"]
