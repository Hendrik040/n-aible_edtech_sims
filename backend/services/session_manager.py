"""
Session Manager for AI Agent Education Platform
Handles session state, caching, and memory management with LangChain
"""

from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import json
import hashlib
import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from langchain_config import langchain_manager, settings
from database.connection import get_db, get_db_session
from database.models import UserProgress, ScenarioScene, ScenarioPersona
from database.models import (
    SessionMemory, ConversationSummaries, AgentSessions, CacheEntries, VectorEmbeddings
)
from utilities.redis_manager import redis_manager, cache_manager

# Logger for session manager operations
logger = logging.getLogger(__name__)

# Create aliases for easier usage
AgentSession = AgentSessions
CacheEntry = CacheEntries

class SessionManager:
    """Manages agent sessions, memory, and caching using Redis"""
    
    def __init__(self):
        self.session_timeout = settings.session_timeout
        self.cache_ttl = settings.cache_ttl
        self._cleanup_task: Optional[asyncio.Task] = None
        
    def generate_session_id(self, user_id: int, scenario_id: int, scene_id: int) -> str:
        """Generate unique, unguessable session ID"""
        return secrets.token_urlsafe(32)
    
    def get_cache_key(self, content_type: str, content_id: int, additional_data: str = "") -> str:
        """Generate cache key for content"""
        return cache_manager.generate_cache_key(f"session_{content_type}", content_id, additional=additional_data)
    
    async def create_agent_session(self, 
                                 user_progress_id: int,
                                 agent_type: str,
                                 agent_id: Optional[str] = None,
                                 session_config: Optional[Dict[str, Any]] = None) -> str:
        """Create new agent session"""
        
        session_id = self.generate_session_id(
            user_progress_id, 0, 0  # Simplified for agent sessions
        )
        
        # Store session data in Redis
        session_data = {
            "agent_type": agent_type,
            "agent_id": agent_id,
            "user_progress_id": user_progress_id,
            "created_at": datetime.utcnow().isoformat(),
            "last_activity": datetime.utcnow().isoformat(),
            "config": session_config or {},
            "session_state": {},
            "is_active": True
        }
        
        # Store in Redis with TTL
        redis_key = f"session:{session_id}"
        if not redis_manager.set(redis_key, session_data, self.session_timeout):
            raise RuntimeError("Failed to store session in Redis")
        
        # Also store in database for persistence (optional backup)
        try:
            with get_db_session() as db:
                agent_session = AgentSession(
                    session_id=session_id,
                    user_progress_id=user_progress_id,
                    agent_type=agent_type,
                    agent_id=agent_id,
                    session_config=session_config or {},
                    session_state={},
                    expires_at=datetime.utcnow() + timedelta(seconds=self.session_timeout),
                    is_active=True
                )
                
                db.add(agent_session)
                db.commit()
        except Exception as e:
            logger.error(f"Error creating agent session in database: {e}")
            # Don't fail if database write fails, Redis is primary
        
        return session_id
    
    async def get_agent_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get agent session by ID"""
        
        # Check memory first
        if session_id in self.active_sessions:
            session_data = self.active_sessions[session_id]
            
            # Check if session is expired
            if datetime.utcnow() - session_data["last_activity"] > timedelta(seconds=self.session_timeout):
                await self.expire_session(session_id)
                return None
            
            # Update last activity
            session_data["last_activity"] = datetime.utcnow()
            return session_data
        
        # Check database
        try:
            with get_db_session() as db:
                agent_session = db.query(AgentSession).filter(
                    and_(
                        AgentSession.session_id == session_id,
                        AgentSession.is_active == True,
                        AgentSession.expires_at > datetime.utcnow()
                    )
                ).first()
                
                if agent_session:
                    # Restore to memory
                    self.active_sessions[session_id] = {
                        "agent_type": agent_session.agent_type,
                        "agent_id": agent_session.agent_id,
                        "user_progress_id": agent_session.user_progress_id,
                        "created_at": agent_session.created_at,
                        "last_activity": agent_session.last_activity,
                        "config": agent_session.session_config or {}
                    }
                    
                    return self.active_sessions[session_id]
        except Exception as e:
            pass
        
        return None
    
    async def update_session_state(self, 
                                 session_id: str, 
                                 state_updates: Dict[str, Any]) -> bool:
        """Update session state"""
        
        # Update memory
        if session_id in self.active_sessions:
            self.active_sessions[session_id]["last_activity"] = datetime.utcnow()
        
        # Update database
        try:
            with get_db_session() as db:
                agent_session = db.query(AgentSession).filter(
                    AgentSession.session_id == session_id
                ).first()
                
                if agent_session:
                    current_state = agent_session.session_state or {}
                    current_state.update(state_updates)
                    agent_session.session_state = current_state
                    agent_session.last_activity = datetime.utcnow()
                    
                    db.commit()
                    return True
        except Exception as e:
            return False
        
        return False
    
    async def expire_session(self, session_id: str) -> bool:
        """Expire and clean up session"""
        
        # Remove from memory
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
        
        # Update database
        try:
            with get_db_session() as db:
                agent_session = db.query(AgentSession).filter(
                    AgentSession.session_id == session_id
                ).first()
                
                if agent_session:
                    agent_session.is_active = False
                    agent_session.expires_at = datetime.utcnow()
                    db.commit()
                    return True
        except Exception as e:
            return False
        
        return False
    
    async def store_memory(self, 
                         session_id: str,
                         memory_type: str,
                         memory_content: str,
                         user_progress_id: int,
                         scene_id: Optional[int] = None,
                         persona_id: Optional[int] = None,
                         importance_score: float = 0.5,
                         metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Store memory in session"""
        
        try:
            with get_db_session() as db:
                memory = SessionMemory(
                    session_id=session_id,
                    user_progress_id=user_progress_id,
                    scene_id=scene_id,
                    memory_type=memory_type,
                    memory_content=memory_content,
                    memory_metadata=metadata or {},
                    related_persona_id=persona_id,
                    importance_score=importance_score,
                    access_count=0
                )
                
                db.add(memory)
                db.commit()
                return True
        except Exception as e:
            return False
    
    async def retrieve_memories(self, 
                              session_id: str,
                              memory_type: Optional[str] = None,
                              limit: int = 10,
                              min_importance: float = 0.0) -> List[SessionMemory]:
        """Retrieve memories for session"""
        
        try:
            with get_db_session() as db:
                query = db.query(SessionMemory).filter(
                    and_(
                        SessionMemory.session_id == session_id,
                        SessionMemory.importance_score >= min_importance
                    )
                )
                
                if memory_type:
                    query = query.filter(SessionMemory.memory_type == memory_type)
                
                memories = query.order_by(
                    desc(SessionMemory.importance_score),
                    desc(SessionMemory.created_at)
                ).limit(limit).all()
                
                # Update access count
                if memories:
                    memory_ids = [m.id for m in memories]
                    db.query(SessionMemory).filter(
                        SessionMemory.id.in_(memory_ids)
                    ).update(
                        {
                            SessionMemory.access_count: SessionMemory.access_count + 1,
                            SessionMemory.last_accessed: datetime.utcnow()
                        },
                        synchronize_session=False
                    )
                    db.commit()
                return memories
        except Exception as e:
            return []
    
    async def store_conversation_summary(self, 
                                       user_progress_id: int,
                                       summary_type: str,
                                       summary_text: str,
                                       scene_id: Optional[int] = None,
                                       key_points: Optional[List[str]] = None,
                                       learning_moments: Optional[List[str]] = None,
                                       insights: Optional[List[str]] = None,
                                       recommendations: Optional[List[str]] = None,
                                       metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Store conversation summary"""
        
        try:
            with get_db_session() as db:
                summary = ConversationSummaries(
                    user_progress_id=user_progress_id,
                    scene_id=scene_id,
                    summary_type=summary_type,
                    summary_text=summary_text,
                    key_points=key_points or [],
                    learning_moments=learning_moments or [],
                    insights=insights or [],
                    recommendations=recommendations or [],
                    summary_metadata=metadata or {},
                    quality_score=0.5,
                    relevance_score=0.5
                )
                
                db.add(summary)
                db.commit()
                return True
        except Exception as e:
            return False
    
    async def get_conversation_summaries(self, 
                                       user_progress_id: int,
                                       summary_type: Optional[str] = None,
                                       scene_id: Optional[int] = None,
                                       limit: int = 10) -> List[ConversationSummaries]:
        """Get conversation summaries"""
        
        try:
            with get_db_session() as db:
                query = db.query(ConversationSummaries).filter(
                    ConversationSummaries.user_progress_id == user_progress_id
                )
                
                if summary_type:
                    query = query.filter(ConversationSummaries.summary_type == summary_type)
                
                if scene_id:
                    query = query.filter(ConversationSummaries.scene_id == scene_id)
                
                summaries = query.order_by(
                    desc(ConversationSummaries.created_at)
                ).limit(limit).all()
                
                return summaries
        except Exception as e:
            return []
    
    async def cache_data(self, 
                        cache_key: str,
                        cache_type: str,
                        data: Any,
                        ttl_seconds: Optional[int] = None) -> bool:
        """Cache data with TTL"""
        
        ttl = ttl_seconds or self.cache_ttl
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        
        try:
            with get_db_session() as db:
                # Check if entry exists
                existing_entry = db.query(CacheEntry).filter(
                    CacheEntry.cache_key == cache_key
                ).first()
                
                if existing_entry:
                    # Update existing entry
                    existing_entry.cache_data = data
                    existing_entry.expires_at = expires_at
                    existing_entry.is_expired = False
                    existing_entry.updated_at = datetime.utcnow()
                else:
                    # Create new entry
                    cache_entry = CacheEntry(
                        cache_key=cache_key,
                        cache_type=cache_type,
                        cache_data=data,
                        cache_size=len(str(data)),
                        expires_at=expires_at,
                        is_expired=False
                    )
                    db.add(cache_entry)
                
                db.commit()
                return True
        except Exception as e:
            return False
    
    async def get_cached_data(self, cache_key: str) -> Optional[Any]:
        """Get cached data"""
        
        try:
            with get_db_session() as db:
                cache_entry = db.query(CacheEntry).filter(
                    and_(
                        CacheEntry.cache_key == cache_key,
                        CacheEntry.is_expired == False,
                        CacheEntry.expires_at > datetime.utcnow()
                    )
                ).first()
                
                if cache_entry:
                    # Update access statistics
                    cache_entry.hit_count += 1
                    cache_entry.last_accessed = datetime.utcnow()
                    db.commit()
                    
                    return cache_entry.cache_data
                
                # Update miss count for non-existent entries
                cache_entry = db.query(CacheEntry).filter(
                    CacheEntry.cache_key == cache_key
                ).first()
                
                if cache_entry:
                    cache_entry.miss_count += 1
                    db.commit()
                
                return None
        except Exception as e:
            return None
    
    async def invalidate_cache(self, cache_key: str) -> bool:
        """Invalidate cache entry"""
        
        try:
            with get_db_session() as db:
                cache_entry = db.query(CacheEntry).filter(
                    CacheEntry.cache_key == cache_key
                ).first()
                
                if cache_entry:
                    cache_entry.is_expired = True
                    cache_entry.expires_at = datetime.utcnow()
                    db.commit()
                    return True
        except Exception as e:
            return False
        
        return False
    
    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions and cache entries"""
        
        try:
            with get_db_session() as db:
                # Clean up expired agent sessions
                expired_sessions = db.query(AgentSession).filter(
                    and_(
                        AgentSession.is_active == True,
                        AgentSession.expires_at < datetime.utcnow()
                    )
                ).all()
                
                for session in expired_sessions:
                    session.is_active = False
                
                # Clean up expired cache entries
                expired_cache = db.query(CacheEntry).filter(
                    and_(
                        CacheEntry.is_expired == False,
                        CacheEntry.expires_at < datetime.utcnow()
                    )
                ).all()
                
                for cache_entry in expired_cache:
                    cache_entry.is_expired = True
                
                db.commit()
                
                # Clean up memory
                expired_session_ids = [s.session_id for s in expired_sessions]
                for session_id in expired_session_ids:
                    if session_id in self.active_sessions:
                        del self.active_sessions[session_id]
                
                return len(expired_sessions) + len(expired_cache)
        except Exception as e:
            return 0
    
    async def get_session_statistics(self) -> Dict[str, Any]:
        """Get session and cache statistics"""
        
        try:
            with get_db_session() as db:
                # Active sessions count
                active_sessions = db.query(AgentSession).filter(
                    AgentSession.is_active == True
                ).count()
                
                # Cache statistics
                from sqlalchemy import func
                cache_stats = db.query(CacheEntry).with_entities(
                    CacheEntry.cache_type,
                    func.count(CacheEntry.id).label('count'),
                    func.sum(CacheEntry.hit_count).label('total_hits'),
                    func.sum(CacheEntry.miss_count).label('total_misses')
                ).group_by(CacheEntry.cache_type).all()
                
                # Memory statistics
                memory_stats = db.query(SessionMemory).with_entities(
                    SessionMemory.memory_type,
                    func.count(SessionMemory.id).label('count')
                ).group_by(SessionMemory.memory_type).all()
                
                return {
                    "active_sessions": active_sessions,
                    "memory_sessions": len(self.active_sessions),
                    "cache_statistics": [
                        {
                            "type": stat.cache_type,
                            "count": stat.count,
                            "total_hits": stat.total_hits or 0,
                            "total_misses": stat.total_misses or 0
                        }
                        for stat in cache_stats
                    ],
                    "memory_statistics": [
                        {
                            "type": stat.memory_type,
                            "count": stat.count
                        }
                        for stat in memory_stats
                    ]
                }
        except Exception as e:
            return {}
    

# Global session manager instance
session_manager = SessionManager()

# Background task for cleanup
async def cleanup_task():
    """Background task to clean up expired sessions"""
    while True:
        try:
            cleaned = await session_manager.cleanup_expired_sessions()
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} expired sessions and cache entries")
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")
        
        # Run cleanup every 5 minutes
        await asyncio.sleep(300)

# FastAPI lifespan manager for session cleanup
@asynccontextmanager
async def session_manager_lifespan(app):
    """FastAPI lifespan handler for session manager startup and shutdown"""
    global cleanup_task_handle
    # Startup
    cleanup_task_handle = asyncio.create_task(cleanup_task())
    logger.info("Started session cleanup task")
    yield
    # Shutdown
    if cleanup_task_handle:
        cleanup_task_handle.cancel()
        try:
            await cleanup_task_handle
        except asyncio.CancelledError:
            logger.info("Session cleanup task cancelled successfully")
        except Exception as e:
            logger.error(f"Error during cleanup task shutdown: {e}")

# Global variable to hold the cleanup task handle
cleanup_task_handle = None
