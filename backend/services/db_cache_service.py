"""
Database Query Caching Service
Caches expensive database queries to improve performance
"""

import hashlib
import json
import logging
from typing import Any, Dict, Optional, Union, List, Callable
from datetime import datetime, timedelta
from functools import wraps
from sqlalchemy.orm import Session
from common.utilities.redis_manager import redis_manager, cache_manager

# Logger for database cache operations
logger = logging.getLogger(__name__)

class DatabaseCacheService:
    """Service for caching database query results"""
    
    def __init__(self):
        self.default_ttl = 1800  # 30 minutes default TTL
        self.user_data_ttl = 300  # 5 minutes for user-specific data
        self.static_data_ttl = 3600  # 1 hour for relatively static data
        self.dynamic_data_ttl = 600  # 10 minutes for frequently changing data
    
    def _generate_query_cache_key(self, 
                                query_name: str, 
                                params: Optional[Dict] = None,
                                user_id: Optional[int] = None) -> str:
        """Generate a cache key for database queries"""
        
        key_parts = [f"db_query:{query_name}"]
        
        if user_id:
            key_parts.append(f"user:{user_id}")
        
        if params:
            # Sort params for consistent key generation
            sorted_params = sorted(params.items()) if isinstance(params, dict) else params
            params_str = json.dumps(sorted_params, sort_keys=True)
            params_hash = hashlib.md5(params_str.encode()).hexdigest()[:16]
            key_parts.append(f"params:{params_hash}")
        
        return ":".join(key_parts)
    
    def cache_query_result(self, 
                         query_name: str,
                         result: Any,
                         ttl: Optional[int] = None,
                         user_id: Optional[int] = None,
                         params: Optional[Dict] = None) -> bool:
        """Cache a database query result"""
        
        cache_key = self._generate_query_cache_key(query_name, params, user_id)
        
        cache_data = {
            "result": result,
            "query_name": query_name,
            "user_id": user_id,
            "params": params,
            "cached_at": datetime.utcnow().isoformat()
        }
        
        if ttl is None:
            # Determine TTL based on query type
            if user_id:
                ttl = self.user_data_ttl
            elif query_name in ["scenario_list", "user_list", "published_scenarios"]:
                ttl = self.dynamic_data_ttl
            elif query_name in ["scenario_details", "user_profile", "persona_details"]:
                ttl = self.static_data_ttl
            else:
                ttl = self.default_ttl
        
        success = redis_manager.set(cache_key, cache_data, ttl)
        if success:
            logger.debug(f"Cached database query result: {query_name}")
        
        return success
    
    def get_cached_query_result(self, 
                              query_name: str,
                              user_id: Optional[int] = None,
                              params: Optional[Dict] = None) -> Optional[Any]:
        """Get cached database query result"""
        
        cache_key = self._generate_query_cache_key(query_name, params, user_id)
        cached_data = redis_manager.get(cache_key)
        
        if cached_data:
            logger.debug(f"Cache hit for database query: {query_name}")
            return cached_data.get("result")
        
        logger.debug(f"Cache miss for database query: {query_name}")
        return None
    
    def invalidate_query_cache(self, 
                             query_name: Optional[str] = None,
                             user_id: Optional[int] = None,
                             pattern: Optional[str] = None) -> int:
        """Invalidate database query cache entries"""
        
        if pattern:
            keys = redis_manager.get_keys(pattern)
        elif query_name and user_id:
            pattern = f"db_query:{query_name}:user:{user_id}:*"
            keys = redis_manager.get_keys(pattern)
        elif query_name:
            pattern = f"db_query:{query_name}:*"
            keys = redis_manager.get_keys(pattern)
        elif user_id:
            pattern = f"db_query:*:user:{user_id}:*"
            keys = redis_manager.get_keys(pattern)
        else:
            # Invalidate all database query caches
            keys = redis_manager.get_keys("db_query:*")
        
        deleted_count = 0
        for key in keys:
            if redis_manager.delete(key):
                deleted_count += 1
        
        logger.info(f"Invalidated {deleted_count} database query cache entries")
        return deleted_count
    
    def invalidate_user_related_cache(self, user_id: int) -> int:
        """Invalidate all cache entries related to a specific user"""
        
        patterns = [
            f"db_query:*:user:{user_id}:*",
            f"user:{user_id}:*",
            f"session:user:{user_id}:*"
        ]
        
        deleted_count = 0
        for pattern in patterns:
            keys = redis_manager.get_keys(pattern)
            for key in keys:
                if redis_manager.delete(key):
                    deleted_count += 1
        
        logger.info(f"Invalidated {deleted_count} user-related cache entries for user {user_id}")
        return deleted_count
    
    def invalidate_scenario_cache(self, scenario_id: int) -> int:
        """Invalidate all cache entries related to a specific scenario"""
        
        patterns = [
            f"db_query:*scenario*:*",
            f"scenario:{scenario_id}:*",
            f"ai_cache:scenario_*:*"
        ]
        
        deleted_count = 0
        for pattern in patterns:
            keys = redis_manager.get_keys(pattern)
            for key in keys:
                if redis_manager.delete(key):
                    deleted_count += 1
        
        logger.info(f"Invalidated {deleted_count} scenario-related cache entries for scenario {scenario_id}")
        return deleted_count


# Global database cache service instance
db_cache_service = DatabaseCacheService()

# Convenience functions
def get_db_cache() -> DatabaseCacheService:
    """Get the global database cache service instance"""
    return db_cache_service

# Decorator for caching database query results
def cache_db_query(query_name: str, ttl: Optional[int] = None, user_specific: bool = False):
    """Decorator to cache database query results"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extract user_id if user_specific is True
            user_id = None
            if user_specific:
                # Try to find user_id in kwargs or args
                user_id = kwargs.get('user_id') or kwargs.get('current_user_id')
                if not user_id and args:
                    # Check if first argument is a user object or has an id
                    first_arg = args[0]
                    if hasattr(first_arg, 'id'):
                        user_id = first_arg.id
            
            # Generate cache key
            cache_key = cache_manager.generate_cache_key(
                f"db_query_{query_name}", 
                *args, 
                user_id=user_id,
                **kwargs
            )
            
            # Try to get from cache
            cached_result = cache_manager.get_cached_result(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for database query: {query_name}")
                return cached_result
            
            # Execute function and cache result
            logger.debug(f"Cache miss for database query: {query_name}")
            result = func(*args, **kwargs)
            
            # Cache the result
            cache_ttl = ttl
            if cache_ttl is None:
                if user_specific:
                    cache_ttl = db_cache_service.user_data_ttl
                else:
                    cache_ttl = db_cache_service.default_ttl
            
            cache_manager.cache_result(cache_key, result, cache_ttl)
            
            return result
        
        return wrapper
    return decorator

# Specific caching decorators for common query types
def cache_user_query(ttl: Optional[int] = None):
    """Decorator for user-specific database queries"""
    return cache_db_query("user_specific", ttl, user_specific=True)

def cache_static_query(query_name: str, ttl: Optional[int] = None):
    """Decorator for relatively static database queries"""
    return cache_db_query(query_name, ttl or db_cache_service.static_data_ttl)

def cache_dynamic_query(query_name: str, ttl: Optional[int] = None):
    """Decorator for frequently changing database queries"""
    return cache_db_query(query_name, ttl or db_cache_service.dynamic_data_ttl)
