"""
AI Response Caching Service
Caches expensive AI API calls to reduce costs and improve performance
"""

import hashlib
import json
import logging
from typing import Any, Dict, Optional, Union, List
from datetime import datetime, timedelta
from common.utils.redis_manager import redis_manager, cache_manager

# Logger for AI cache operations
logger = logging.getLogger(__name__)

class AICacheService:
    """Service for caching AI responses and managing cache invalidation"""
    
    def __init__(self):
        self.default_ttl = 3600  # 1 hour default TTL
        self.expensive_operations_ttl = 86400  # 24 hours for expensive operations
        self.cheap_operations_ttl = 1800  # 30 minutes for cheap operations
    
    def _generate_cache_key(self, 
                          operation: str, 
                          input_data: Union[str, Dict, List], 
                          model: Optional[str] = None,
                          temperature: Optional[float] = None,
                          additional_params: Optional[Dict] = None) -> str:
        """Generate a cache key for AI operations"""
        
        # Create a hash of the input data
        if isinstance(input_data, (dict, list)):
            input_str = json.dumps(input_data, sort_keys=True)
        else:
            input_str = str(input_data)
        
        # Include model and temperature in hash if provided
        hash_input = input_str
        if model:
            hash_input += f"|model:{model}"
        if temperature is not None:
            hash_input += f"|temp:{temperature}"
        if additional_params:
            hash_input += f"|params:{json.dumps(additional_params, sort_keys=True)}"
        
        # Generate hash
        input_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]
        
        return f"ai_cache:{operation}:{input_hash}"
    
    def cache_openai_response(self, 
                            operation: str,
                            input_data: Union[str, Dict, List],
                            response: Any,
                            model: str = "gpt-4",
                            temperature: Optional[float] = None,
                            ttl: Optional[int] = None) -> bool:
        """Cache OpenAI API response"""
        
        cache_key = self._generate_cache_key(operation, input_data, model, temperature)
        
        cache_data = {
            "response": response,
            "model": model,
            "temperature": temperature,
            "cached_at": datetime.utcnow().isoformat(),
            "operation": operation
        }
        
        if ttl is None:
            # Determine TTL based on operation type
            if operation in ["image_generation", "complex_analysis", "scenario_generation"]:
                ttl = self.expensive_operations_ttl
            elif operation in ["simple_chat", "text_completion", "embeddings"]:
                ttl = self.cheap_operations_ttl
            else:
                ttl = self.default_ttl
        
        success = redis_manager.set(cache_key, cache_data, ttl)
        if success:
            logger.debug(f"Cached OpenAI response for operation: {operation}")
        
        return success
    
    def get_cached_openai_response(self, 
                                 operation: str,
                                 input_data: Union[str, Dict, List],
                                 model: str = "gpt-4",
                                 temperature: Optional[float] = None) -> Optional[Any]:
        """Get cached OpenAI API response"""
        
        cache_key = self._generate_cache_key(operation, input_data, model, temperature)
        cached_data = redis_manager.get(cache_key)
        
        if cached_data:
            logger.debug(f"Cache hit for OpenAI operation: {operation}")
            return cached_data.get("response")
        
        logger.debug(f"Cache miss for OpenAI operation: {operation}")
        return None
    
    def cache_embedding(self, 
                       text: str, 
                       embedding: List[float],
                       model: str = "text-embedding-3-small") -> bool:
        """Cache text embeddings"""
        
        cache_key = self._generate_cache_key("embedding", text, model)
        
        cache_data = {
            "embedding": embedding,
            "text": text,
            "model": model,
            "cached_at": datetime.utcnow().isoformat()
        }
        
        # Embeddings are relatively stable, cache for 24 hours
        success = redis_manager.set(cache_key, cache_data, self.expensive_operations_ttl)
        if success:
            logger.debug(f"Cached embedding for text length: {len(text)}")
        
        return success
    
    def get_cached_embedding(self, text: str, model: str = "text-embedding-3-small") -> Optional[List[float]]:
        """Get cached text embedding"""
        
        cache_key = self._generate_cache_key("embedding", text, model)
        cached_data = redis_manager.get(cache_key)
        
        if cached_data:
            logger.debug(f"Cache hit for embedding, text length: {len(text)}")
            return cached_data.get("embedding")
        
        logger.debug(f"Cache miss for embedding, text length: {len(text)}")
        return None
    
    def cache_scenario_analysis(self, 
                              pdf_content: str, 
                              analysis_result: Dict[str, Any]) -> bool:
        """Cache PDF scenario analysis results"""
        
        cache_key = self._generate_cache_key("scenario_analysis", pdf_content)
        
        cache_data = {
            "analysis": analysis_result,
            "content_hash": hashlib.md5(pdf_content.encode()).hexdigest(),
            "cached_at": datetime.utcnow().isoformat()
        }
        
        # Scenario analysis is expensive, cache for 7 days
        success = redis_manager.set(cache_key, cache_data, 7 * 24 * 3600)
        if success:
            logger.debug("Cached scenario analysis result")
        
        return success
    
    def get_cached_scenario_analysis(self, pdf_content: str) -> Optional[Dict[str, Any]]:
        """Get cached scenario analysis result"""
        
        cache_key = self._generate_cache_key("scenario_analysis", pdf_content)
        cached_data = redis_manager.get(cache_key)
        
        if cached_data:
            logger.debug("Cache hit for scenario analysis")
            return cached_data.get("analysis")
        
        logger.debug("Cache miss for scenario analysis")
        return None
    
    def cache_simulation_response(self, 
                                simulation_id: int,
                                user_message: str,
                                response: Dict[str, Any],
                                ttl: int = 3600) -> bool:
        """Cache simulation chat responses"""
        
        cache_key = f"simulation:{simulation_id}:chat:{hashlib.md5(user_message.encode()).hexdigest()[:16]}"
        
        cache_data = {
            "response": response,
            "user_message": user_message,
            "simulation_id": simulation_id,
            "cached_at": datetime.utcnow().isoformat()
        }
        
        success = redis_manager.set(cache_key, cache_data, ttl)
        if success:
            logger.debug(f"Cached simulation response for simulation {simulation_id}")
        
        return success
    
    def get_cached_simulation_response(self, 
                                     simulation_id: int,
                                     user_message: str) -> Optional[Dict[str, Any]]:
        """Get cached simulation chat response"""
        
        cache_key = f"simulation:{simulation_id}:chat:{hashlib.md5(user_message.encode()).hexdigest()[:16]}"
        cached_data = redis_manager.get(cache_key)
        
        if cached_data:
            logger.debug(f"Cache hit for simulation {simulation_id}")
            return cached_data.get("response")
        
        logger.debug(f"Cache miss for simulation {simulation_id}")
        return None
    
    def invalidate_simulation_cache(self, simulation_id: int) -> int:
        """Invalidate all cache entries for a specific simulation"""
        
        pattern = f"simulation:{simulation_id}:*"
        keys = redis_manager.get_keys(pattern)
        
        deleted_count = 0
        for key in keys:
            if redis_manager.delete(key):
                deleted_count += 1
        
        logger.info(f"Invalidated {deleted_count} cache entries for simulation {simulation_id}")
        return deleted_count
    
    def invalidate_user_cache(self, user_id: int) -> int:
        """Invalidate all cache entries for a specific user"""
        
        patterns = [
            f"simulation:*:user:{user_id}",
            f"user:{user_id}:*",
            f"session:user:{user_id}:*"
        ]
        
        deleted_count = 0
        for pattern in patterns:
            keys = redis_manager.get_keys(pattern)
            for key in keys:
                if redis_manager.delete(key):
                    deleted_count += 1
        
        logger.info(f"Invalidated {deleted_count} cache entries for user {user_id}")
        return deleted_count
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        
        patterns = [
            "ai_cache:*",
            "simulation:*",
            "embedding:*",
            "session:*"
        ]
        
        stats = {}
        total_keys = 0
        
        for pattern in patterns:
            keys = redis_manager.get_keys(pattern)
            key_count = len(keys)
            stats[pattern] = key_count
            total_keys += key_count
        
        stats["total_cached_keys"] = total_keys
        stats["cache_timestamp"] = datetime.utcnow().isoformat()
        
        return stats
    
    def cleanup_expired_cache(self) -> int:
        """Clean up expired cache entries (Redis handles this automatically, but useful for monitoring)"""
        
        # Redis handles TTL expiration automatically
        # This method is kept for compatibility and monitoring
        stats = self.get_cache_stats()
        logger.info(f"Cache cleanup check completed. Total keys: {stats['total_cached_keys']}")
        
        return stats['total_cached_keys']


# Global AI cache service instance
ai_cache_service = AICacheService()

# Convenience functions
def get_ai_cache() -> AICacheService:
    """Get the global AI cache service instance"""
    return ai_cache_service

# Decorator for caching AI function results
def cache_ai_response(operation: str, ttl: Optional[int] = None):
    """Decorator to cache AI function results"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            cache_key = cache_manager.generate_cache_key(f"ai_{operation}", func.__name__, *args, **kwargs)
            
            # Try to get from cache
            cached_result = cache_manager.get_cached_result(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for AI function {func.__name__}")
                return cached_result
            
            # Execute function and cache result
            logger.debug(f"Cache miss for AI function {func.__name__}")
            result = func(*args, **kwargs)
            cache_manager.cache_result(cache_key, result, ttl or ai_cache_service.default_ttl)
            
            return result
        
        return wrapper
    return decorator
