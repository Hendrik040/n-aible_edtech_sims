"""
Unified caching interface (Redis + in-memory fallback)
"""
import json
import logging
from typing import Optional, Any, List
import redis
from redis.exceptions import ConnectionError, RedisError

from common.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class RedisManager:
    """
    Redis client wrapper with connection management and queue operations.
    """
    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        self._connect()
    
    def _connect(self) -> None:
        """Initialize Redis connection."""
        try:
            redis_url = settings.redis_url or "redis://localhost:6379"
            self.redis = redis.from_url(redis_url, decode_responses=True)
            # Test connection
            self.redis.ping()
            logger.info(f"[REDIS] Connected to Redis at {redis_url}")
        except (ConnectionError, RedisError) as e:
            logger.error(f"[REDIS] Failed to connect to Redis: {e}")
            self.redis = None
    
    def _ensure_connected(self) -> bool:
        """Ensure Redis connection is active."""
        if self.redis is None:
            self._connect()
        if self.redis is None:
            return False
        try:
            self.redis.ping()
            return True
        except (ConnectionError, RedisError):
            logger.warning("[REDIS] Connection lost, attempting reconnect...")
            self._connect()
            return self.redis is not None

    def set(self, key: str, value: Any, ttl: int = 600) -> bool:
        """Set a key-value pair with optional TTL."""
        if not self._ensure_connected():
            return False
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            return self.redis.setex(key, ttl, value)
        except RedisError as e:
            logger.error(f"[REDIS] Error setting key {key}: {e}")
            return False

    def get(self, key: str) -> Optional[Any]:
        """Get value by key."""
        if not self._ensure_connected():
            return None
        try:
            value = self.redis.get(key)
            if value is None:
                return None
            # Try to parse as JSON, fallback to string
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        except RedisError as e:
            logger.error(f"[REDIS] Error getting key {key}: {e}")
        return None
    
    def delete(self, key: str) -> bool:
        """Delete a key."""
        if not self._ensure_connected():
            return False
        try:
            return bool(self.redis.delete(key))
        except RedisError as e:
            logger.error(f"[REDIS] Error deleting key {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists."""
        if not self._ensure_connected():
            return False
        try:
            return bool(self.redis.exists(key))
        except RedisError as e:
            logger.error(f"[REDIS] Error checking key {key}: {e}")
            return False
    
    # List operations for job queue
    def lpush(self, key: str, *values: Any) -> int:
        """Push values to left of list (queue)."""
        if not self._ensure_connected():
            return 0
        try:
            serialized = [json.dumps(v) if isinstance(v, (dict, list)) else str(v) for v in values]
            return self.redis.lpush(key, *serialized)
        except RedisError as e:
            # If WRONGTYPE error, key exists as different type - delete and retry
            if "WRONGTYPE" in str(e):
                logger.warning(f"[REDIS] Key {key} is wrong type, deleting and recreating as list")
                try:
                    self.redis.delete(key)
                    return self.redis.lpush(key, *serialized)
                except Exception as retry_error:
                    logger.error(f"[REDIS] Error recreating key {key}: {retry_error}")
                    return 0
            logger.error(f"[REDIS] Error lpush to {key}: {e}")
            return 0
    
    def rpop(self, key: str) -> Optional[Any]:
        """Pop value from right of list (queue)."""
        if not self._ensure_connected():
            return None
        try:
            value = self.redis.rpop(key)
            if value is None:
                return None
            # Try to parse as JSON, fallback to string
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        except RedisError as e:
            logger.error(f"[REDIS] Error rpop from {key}: {e}")
            return None
    
    def llen(self, key: str) -> int:
        """Get length of list."""
        if not self._ensure_connected():
            return 0
        try:
            return self.redis.llen(key)
        except RedisError as e:
            # If WRONGTYPE error, key exists as different type - return 0 (treat as empty)
            if "WRONGTYPE" in str(e):
                logger.warning(f"[REDIS] Key {key} is wrong type (expected list), treating as empty")
                return 0
            logger.error(f"[REDIS] Error llen for {key}: {e}")
            return 0
    
    def lrange(self, key: str, start: int = 0, end: int = -1) -> List[Any]:
        """Get range of list values."""
        if not self._ensure_connected():
            return []
        try:
            values = self.redis.lrange(key, start, end)
            result = []
            for v in values:
                try:
                    result.append(json.loads(v))
                except (json.JSONDecodeError, TypeError):
                    result.append(v)
            return result
        except RedisError as e:
            logger.error(f"[REDIS] Error lrange for {key}: {e}")
            return []
    
    def lrem(self, key: str, count: int, value: Any) -> int:
        """Remove elements from list. Returns number of elements removed."""
        if not self._ensure_connected():
            return 0
        try:
            # Serialize value to match how it was stored
            serialized = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
            return self.redis.lrem(key, count, serialized)
        except RedisError as e:
            # If WRONGTYPE error, key exists as different type - delete and return 0
            if "WRONGTYPE" in str(e):
                logger.warning(f"[REDIS] Key {key} is wrong type (expected list), deleting it")
                try:
                    self.redis.delete(key)
                    return 0
                except Exception as delete_error:
                    logger.error(f"[REDIS] Error deleting wrong-type key {key}: {delete_error}")
                    return 0
            logger.error(f"[REDIS] Error lrem from {key}: {e}")
            return 0
    
    # Set operations for deduplication
    def sadd(self, key: str, *values: Any) -> int:
        """Add values to set."""
        if not self._ensure_connected():
            return 0
        try:
            serialized = [json.dumps(v) if isinstance(v, (dict, list)) else str(v) for v in values]
            return self.redis.sadd(key, *serialized)
        except RedisError as e:
            logger.error(f"[REDIS] Error sadd to {key}: {e}")
            return 0
    
    def sismember(self, key: str, value: Any) -> bool:
        """Check if value is member of set."""
        if not self._ensure_connected():
            return False
        try:
            serialized = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
            return bool(self.redis.sismember(key, serialized))
        except RedisError as e:
            logger.error(f"[REDIS] Error sismember for {key}: {e}")
            return False
    
    def srem(self, key: str, *values: Any) -> int:
        """Remove values from set."""
        if not self._ensure_connected():
            return 0
        try:
            serialized = [json.dumps(v) if isinstance(v, (dict, list)) else str(v) for v in values]
            return self.redis.srem(key, *serialized)
        except RedisError as e:
            logger.error(f"[REDIS] Error srem from {key}: {e}")
            return 0

# Singleton instance
redis_manager = RedisManager()
