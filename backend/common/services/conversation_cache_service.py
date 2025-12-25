"""
Conversation Cache Service.

Caches conversation history in Redis to reduce DB queries during chat.
Uses write-through caching with batched persistence to DB.

Key format: conv_history:{user_progress_id}:{scene_id}
TTL: 30 minutes (matches inactivity timeout)
"""

import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from common.services.cache_service import redis_manager

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_TTL_SECONDS = 30 * 60  # 30 minutes
CACHE_KEY_PREFIX = "conv_history"
MAX_CACHED_MESSAGES = 50  # Keep last 50 messages in cache


@dataclass
class CachedMessage:
    """Lightweight message object matching ConversationLog attributes.
    
    Used to provide consistent interface whether data comes from cache or DB.
    """
    id: Optional[int]
    user_progress_id: int
    scene_id: int
    session_id: Optional[str]
    message_type: str
    sender_name: str
    message_content: str
    message_order: int
    persona_id: Optional[int]
    created_at: Optional[str]


def _get_cache_key(user_progress_id: int, scene_id: int) -> str:
    """Generate Redis cache key for conversation history."""
    return f"{CACHE_KEY_PREFIX}:{user_progress_id}:{scene_id}"


def _serialize_conversation_log(log) -> Dict[str, Any]:
    """Serialize a ConversationLog ORM object to dict for Redis storage."""
    return {
        "id": log.id,
        "user_progress_id": log.user_progress_id,
        "scene_id": log.scene_id,
        "session_id": log.session_id,
        "message_type": log.message_type,
        "sender_name": log.sender_name,
        "message_content": log.message_content,
        "message_order": log.message_order,
        "persona_id": log.persona_id,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def _dict_to_cached_message(data: Dict[str, Any]) -> CachedMessage:
    """Convert a dict from Redis to CachedMessage object."""
    return CachedMessage(
        id=data.get("id"),
        user_progress_id=data.get("user_progress_id"),
        scene_id=data.get("scene_id"),
        session_id=data.get("session_id"),
        message_type=data.get("message_type"),
        sender_name=data.get("sender_name"),
        message_content=data.get("message_content"),
        message_order=data.get("message_order"),
        persona_id=data.get("persona_id"),
        created_at=data.get("created_at"),
    )


class ConversationCacheService:
    """Service for caching conversation history in Redis."""
    
    @staticmethod
    def get_cached_history(
        user_progress_id: int,
        scene_id: int,
        session_id_filter: Optional[str] = None
    ) -> Optional[List[CachedMessage]]:
        """
        Get conversation history from Redis cache.
        
        Args:
            user_progress_id: User progress ID
            scene_id: Scene ID
            session_id_filter: Optional session_id prefix to filter by
            
        Returns:
            List of CachedMessage objects if cache hit, None if cache miss
        """
        cache_key = _get_cache_key(user_progress_id, scene_id)
        
        try:
            cached_data = redis_manager.get(cache_key)
            if cached_data is None:
                logger.info(f"[CONV_CACHE] Cache MISS for {cache_key}")
                return None
            
            # Parse cached JSON
            if isinstance(cached_data, str):
                messages = json.loads(cached_data)
            else:
                messages = cached_data
            
            # Filter by session_id if provided
            if session_id_filter:
                base_session_id = session_id_filter
                if "_persona_" in session_id_filter:
                    base_session_id = session_id_filter.rsplit("_persona_", 1)[0]
                
                messages = [
                    msg for msg in messages
                    if (msg.get("session_id") == base_session_id or
                        msg.get("session_id") == session_id_filter or
                        (msg.get("session_id") or "").startswith(f"{base_session_id}_"))
                ]
            
            # Convert to CachedMessage objects
            cached_messages = [_dict_to_cached_message(msg) for msg in messages]
            
            logger.info(
                f"[CONV_CACHE] Cache HIT for {cache_key}: {len(cached_messages)} messages"
            )
            return cached_messages
            
        except Exception as e:
            logger.warning(f"[CONV_CACHE] Error reading cache: {e}")
            return None
    
    @staticmethod
    def set_cached_history(
        user_progress_id: int,
        scene_id: int,
        messages: List
    ) -> bool:
        """
        Store conversation history in Redis cache.
        
        Args:
            user_progress_id: User progress ID
            scene_id: Scene ID
            messages: List of ConversationLog ORM objects to cache
            
        Returns:
            True if successful, False otherwise
        """
        cache_key = _get_cache_key(user_progress_id, scene_id)
        
        try:
            # Serialize messages (handles ORM objects)
            serialized = [_serialize_conversation_log(msg) for msg in messages]
            
            # Keep only last N messages
            if len(serialized) > MAX_CACHED_MESSAGES:
                serialized = serialized[-MAX_CACHED_MESSAGES:]
            
            # Store in Redis with TTL
            redis_manager.set(
                cache_key,
                json.dumps(serialized),
                ttl=CACHE_TTL_SECONDS
            )
            
            logger.info(
                f"[CONV_CACHE] Cached {len(serialized)} messages for {cache_key}"
            )
            return True
            
        except Exception as e:
            logger.warning(f"[CONV_CACHE] Error writing cache: {e}")
            return False
    
    @staticmethod
    def append_message(
        user_progress_id: int,
        scene_id: int,
        message_data: Dict[str, Any]
    ) -> bool:
        """
        Append a new message to the cached history.
        
        Args:
            user_progress_id: User progress ID
            scene_id: Scene ID
            message_data: Message dict to append (must include all required fields)
            
        Returns:
            True if successful, False otherwise
        """
        cache_key = _get_cache_key(user_progress_id, scene_id)
        
        try:
            # Get existing cache
            cached_data = redis_manager.get(cache_key)
            
            if cached_data is None:
                # No cache exists - just store the single message
                messages = [message_data]
            else:
                # Parse and append
                if isinstance(cached_data, str):
                    messages = json.loads(cached_data)
                else:
                    messages = cached_data
                messages.append(message_data)
                
                # Trim to max size
                if len(messages) > MAX_CACHED_MESSAGES:
                    messages = messages[-MAX_CACHED_MESSAGES:]
            
            # Store back with fresh TTL
            redis_manager.set(
                cache_key,
                json.dumps(messages),
                ttl=CACHE_TTL_SECONDS
            )
            
            logger.info(
                f"[CONV_CACHE] Appended message to {cache_key}, "
                f"total: {len(messages)} messages"
            )
            return True
            
        except Exception as e:
            logger.warning(f"[CONV_CACHE] Error appending to cache: {e}")
            return False
    
    @staticmethod
    def invalidate_cache(user_progress_id: int, scene_id: int) -> bool:
        """
        Invalidate (delete) cached conversation history.
        
        Call this when:
        - Scene changes
        - Simulation resets
        - User logs out
        
        Args:
            user_progress_id: User progress ID
            scene_id: Scene ID
            
        Returns:
            True if successful, False otherwise
        """
        cache_key = _get_cache_key(user_progress_id, scene_id)
        
        try:
            redis_manager.delete(cache_key)
            logger.info(f"[CONV_CACHE] Invalidated cache for {cache_key}")
            return True
        except Exception as e:
            logger.warning(f"[CONV_CACHE] Error invalidating cache: {e}")
            return False


# Singleton instance for easy importing
conversation_cache = ConversationCacheService()

