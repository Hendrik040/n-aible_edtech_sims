"""Single-use, time-limited password-reset tokens backed by Redis.

A reset token is an opaque high-entropy string mapped to a user id in Redis
with a short TTL. Tokens are single-use: consuming one deletes it atomically,
so a token cannot be replayed.

Storing tokens server-side (rather than, say, a self-validating JWT) is what
makes true single-use and instant revocation possible, and means the token is
never derivable from the (public) source code.
"""

import logging
import secrets
from typing import Optional

from common.services.cache_service import redis_manager

logger = logging.getLogger(__name__)

# Reset links are valid for 30 minutes.
RESET_TOKEN_TTL_SECONDS = 30 * 60
_KEY_PREFIX = "pwreset:"


def create_reset_token(user_id: int) -> Optional[str]:
    """Create and store a single-use reset token for ``user_id``.

    Returns the token string, or None if it could not be persisted (e.g. Redis
    is unavailable) so callers can fail closed.
    """
    token = secrets.token_urlsafe(32)
    stored = redis_manager.set(f"{_KEY_PREFIX}{token}", str(user_id), ttl=RESET_TOKEN_TTL_SECONDS)
    if not stored:
        logger.error("[PWRESET] Failed to store reset token (Redis unavailable?)")
        return None
    return token


def consume_reset_token(token: str) -> Optional[int]:
    """Validate and atomically invalidate a reset token.

    Returns the associated user id if the token was valid, else None. The token
    is deleted on success so it cannot be reused.
    """
    if not token:
        return None

    key = f"{_KEY_PREFIX}{token}"
    user_id = redis_manager.get(key)
    if user_id is None:
        return None

    # Single-use: delete before returning. If the delete fails we treat the
    # token as invalid rather than risk a replayable token.
    if not redis_manager.delete(key):
        logger.error("[PWRESET] Failed to invalidate reset token after use")
        return None

    try:
        return int(user_id)
    except (ValueError, TypeError):
        return None


__all__ = ["create_reset_token", "consume_reset_token", "RESET_TOKEN_TTL_SECONDS"]
