"""
Redis Manager for AI Agent Education Platform
Centralized Redis client with fallback mechanisms and caching utilities
"""

import json
import hashlib
import time
import logging
from typing import Any, Dict, Optional, Union, List
from datetime import datetime, timedelta
import os
from contextlib import asynccontextmanager

# Logger for Redis operations
logger = logging.getLogger(__name__)

class RedisManager:
    """Centralized Redis client - Redis only, no fallbacks"""
    
    def __init__(self):
        self.redis_client = None
        self._init_redis()
    
    def _init_redis(self):
        """Initialize Redis client - required for operation"""
        try:
            import redis
            redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
            if not redis_url or redis_url == 'REPLACE_WITH_YOUR_REDIS_URL':
                logger.error("REDIS_URL environment variable is required. Please set it in your .env file.")
                raise ValueError("REDIS_URL is required but not properly configured")
            
            self.redis_client = redis.from_url(
                redis_url, 
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            # Test connection
            self.redis_client.ping()
            logger.info("Redis client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Redis client: {e}")
            logger.error("Please ensure Redis is running and REDIS_URL is correctly configured in your .env file")
            raise RuntimeError(f"Redis initialization failed: {e}. Please check your Redis configuration.")
    
    def is_available(self) -> bool:
        """Check if Redis is available"""
        if not self.redis_client:
            return False
        try:
            self.redis_client.ping()
            return True
        except Exception:
            return False
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set a key-value pair with optional TTL"""
        try:
            # Serialize value
            if isinstance(value, (dict, list)):
                serialized_value = json.dumps(value)
            else:
                serialized_value = str(value)
            
            if ttl:
                self.redis_client.setex(key, ttl, serialized_value)
            else:
                self.redis_client.set(key, serialized_value)
            return True
        except Exception as e:
            logger.error(f"Failed to set Redis key {key}: {e}")
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value by key"""
        try:
            value = self.redis_client.get(key)
            if value is None:
                return None
            
            # Try to deserialize as JSON first, fallback to string
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
                
        except Exception as e:
            logger.error(f"Failed to get Redis key {key}: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """Delete a key"""
        try:
            self.redis_client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Failed to delete Redis key {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists"""
        try:
            return bool(self.redis_client.exists(key))
        except Exception as e:
            logger.error(f"Failed to check Redis key existence {key}: {e}")
            return False
    
    def expire(self, key: str, ttl: int) -> bool:
        """Set expiration for a key"""
        try:
            return bool(self.redis_client.expire(key, ttl))
        except Exception as e:
            logger.error(f"Failed to set expiration for Redis key {key}: {e}")
            return False
    
    def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment a numeric value"""
        try:
            return self.redis_client.incrby(key, amount)
        except Exception as e:
            logger.error(f"Failed to increment Redis key {key}: {e}")
            return None
    
    def get_keys(self, pattern: str = "*") -> List[str]:
        """Get keys matching pattern"""
        try:
            return self.redis_client.keys(pattern)
        except Exception as e:
            logger.error(f"Failed to get Redis keys with pattern {pattern}: {e}")
            return []
    
    def cleanup_expired(self):
        """Redis handles expiration automatically, no manual cleanup needed"""
        # Redis handles TTL expiration automatically
        # This method is kept for compatibility but does nothing
        pass


class CacheManager:
    """High-level caching utilities built on RedisManager"""
    
    def __init__(self, redis_manager: RedisManager):
        self.redis = redis_manager
    
    def generate_cache_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate a cache key from prefix and arguments"""
        key_parts = [prefix]
        
        # Add positional arguments
        for arg in args:
            key_parts.append(str(arg))
        
        # Add keyword arguments (sorted for consistency)
        for key, value in sorted(kwargs.items()):
            key_parts.append(f"{key}:{value}")
        
        # Create hash for long keys
        key_string = "_".join(key_parts)
        if len(key_string) > 200:
            key_hash = hashlib.md5(key_string.encode()).hexdigest()
            return f"{prefix}_hash_{key_hash}"
        
        return key_string
    
    def cache_result(self, cache_key: str, result: Any, ttl: int = 3600) -> bool:
        """Cache a result with TTL"""
        return self.redis.set(cache_key, result, ttl)
    
    def get_cached_result(self, cache_key: str) -> Optional[Any]:
        """Get a cached result"""
        return self.redis.get(cache_key)
    
    def invalidate_cache(self, pattern: str) -> int:
        """Invalidate cache entries matching pattern"""
        keys = self.redis.get_keys(pattern)
        deleted_count = 0
        
        for key in keys:
            if self.redis.delete(key):
                deleted_count += 1
        
        return deleted_count
    
    def cache_function_result(self, ttl: int = 3600, prefix: str = "func"):
        """Decorator to cache function results"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                # Generate cache key
                cache_key = self.generate_cache_key(
                    f"{prefix}_{func.__name__}", 
                    *args, 
                    **kwargs
                )
                
                # Try to get from cache
                cached_result = self.get_cached_result(cache_key)
                if cached_result is not None:
                    logger.debug(f"Cache hit for {func.__name__}: {cache_key}")
                    return cached_result
                
                # Execute function and cache result
                logger.debug(f"Cache miss for {func.__name__}: {cache_key}")
                result = func(*args, **kwargs)
                self.cache_result(cache_key, result, ttl)
                
                return result
            
            return wrapper
        return decorator


# Global Redis manager instance
redis_manager = RedisManager()
cache_manager = CacheManager(redis_manager)

# Convenience functions
def get_redis() -> RedisManager:
    """Get the global Redis manager instance"""
    return redis_manager

def get_cache() -> CacheManager:
    """Get the global cache manager instance"""
    return cache_manager

# Background cleanup task
async def redis_cleanup_task():
    """Background task to clean up expired cache entries"""
    while True:
        try:
            redis_manager.cleanup_expired()
            await asyncio.sleep(300)  # Run every 5 minutes
        except Exception as e:
            logger.error(f"Error in Redis cleanup task: {e}")
            await asyncio.sleep(300)

# Import asyncio for the cleanup task
import asyncio
