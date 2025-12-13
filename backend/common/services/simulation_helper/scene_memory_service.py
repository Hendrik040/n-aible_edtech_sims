"""
Scene Memory System for AI Agent Education Platform
Handles scene-level shared memory and context management
"""

from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import json
import asyncio
import threading
import logging
import os
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, or_

from .langchain_service import langchain_manager, settings
from common.db.core import SessionLocal
from common.db.models import UserProgress, ScenarioScene, ScenarioPersona, ConversationLog
from common.db.models import SessionMemory, VectorEmbeddings
from .memory_service import memory_service
from .conversation_service import conversation_service
from common.config import get_settings
config = get_settings()
def is_production():
    return config.environment == "production"

# Logger for scene memory operations
logger = logging.getLogger(__name__)

class SceneMemoryManager:
    """Manages scene-level shared memory and context"""
    
    def __init__(self):
        self.scene_contexts: Dict[str, Dict[str, Any]] = {}
        self.persona_memories: Dict[str, Dict[str, Any]] = {}
        self.shared_contexts: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        
    def get_scene_key(self, user_progress_id: int, scene_id: int) -> str:
        """Generate scene memory key"""
        return f"scene_{user_progress_id}_{scene_id}"
    
    def get_persona_key(self, user_progress_id: int, scene_id: int, persona_id: int) -> str:
        """Generate persona memory key"""
        return f"persona_{user_progress_id}_{scene_id}_{persona_id}"
    
    def get_shared_key(self, user_progress_id: int, scene_id: int) -> str:
        """Generate shared context key"""
        return f"shared_{user_progress_id}_{scene_id}"
    
    async def initialize_scene_memory(self, 
                                    user_progress_id: int,
                                    scene_id: int,
                                    scene_data: Dict[str, Any],
                                    personas: List[ScenarioPersona]) -> bool:
        """Initialize scene memory with context and personas"""
        
        scene_key = self.get_scene_key(user_progress_id, scene_id)
        shared_key = self.get_shared_key(user_progress_id, scene_id)
        
        try:
            with self._lock:
                # Check if memory already exists
                if scene_key in self.scene_contexts:
                    return True
                
                # Load existing memory from database first
                try:
                    await self._load_scene_memory(user_progress_id, scene_id)
                except Exception as e:
                    # Check if we're in production environment
                    if is_production():
                        # In production, log error and re-raise to ensure proper alerting
                        logger.error(f"Failed to load scene memory for user_progress_id={user_progress_id}, scene_id={scene_id}: {e}")
                        raise
                    else:
                        # In development, log at debug level and continue
                        logger.debug(f"Error loading scene memory for user_progress_id={user_progress_id}, scene_id={scene_id}: {e}")
                        # Continue with initialization of new memory structure
                        # This ensures the system doesn't fail completely if DB load fails
                
                # If still not in memory after loading, initialize new
                if scene_key not in self.scene_contexts:
                    self.scene_contexts[scene_key] = {
                        "scene_id": scene_id,
                        "user_progress_id": user_progress_id,
                        "scene_data": scene_data,
                        "personas": [{"id": p.id, "name": p.name, "role": p.role} for p in personas],
                        "conversation_history": [],
                        "shared_insights": [],
                        "learning_moments": [],
                        "created_at": datetime.utcnow(),
                        "last_updated": datetime.utcnow()
                    }
                
                # Initialize shared context if not exists
                if shared_key not in self.shared_contexts:
                    self.shared_contexts[shared_key] = {
                        "scene_id": scene_id,
                        "user_progress_id": user_progress_id,
                        "shared_knowledge": {},
                        "collective_insights": [],
                        "scene_progress": {},
                        "created_at": datetime.utcnow(),
                        "last_updated": datetime.utcnow()
                    }
                
                # Initialize persona memories if not exists
                for persona in personas:
                    persona_key = self.get_persona_key(user_progress_id, scene_id, persona.id)
                    if persona_key not in self.persona_memories:
                        self.persona_memories[persona_key] = {
                            "persona_id": persona.id,
                            "persona_name": persona.name,
                            "persona_role": persona.role,
                            "scene_id": scene_id,
                            "user_progress_id": user_progress_id,
                            "personal_memory": [],
                            "interactions": [],
                            "insights": [],
                            "created_at": datetime.utcnow(),
                            "last_updated": datetime.utcnow()
                        }
            
            # Store in database
            await self._persist_scene_memory(user_progress_id, scene_id, scene_data, personas)
            
            return True
            
        except Exception as e:
            return False
    
    async def add_conversation_to_scene(self, 
                                      user_progress_id: int,
                                      scene_id: int,
                                      conversation_log: ConversationLog) -> bool:
        """Add conversation to scene memory"""
        
        scene_key = self.get_scene_key(user_progress_id, scene_id)
        
        with self._lock:
            if scene_key not in self.scene_contexts:
                return False
        
        try:
            # Add to scene context
            conversation_entry = {
                "id": conversation_log.id,
                "message_type": conversation_log.message_type,
                "sender_name": conversation_log.sender_name,
                "persona_id": conversation_log.persona_id,
                "message_content": conversation_log.message_content,
                "timestamp": conversation_log.timestamp,
                "message_order": conversation_log.message_order
            }
            
            with self._lock:
                self.scene_contexts[scene_key]["conversation_history"].append(conversation_entry)
                self.scene_contexts[scene_key]["last_updated"] = datetime.utcnow()
                
                # Add to persona memory if applicable
                if conversation_log.persona_id:
                    persona_key = self.get_persona_key(user_progress_id, scene_id, conversation_log.persona_id)
                    if persona_key in self.persona_memories:
                        self.persona_memories[persona_key]["interactions"].append(conversation_entry)
                        self.persona_memories[persona_key]["last_updated"] = datetime.utcnow()
            
            # Store in database
            await self._store_conversation_memory(user_progress_id, scene_id, conversation_log)
            
            return True
            
        except Exception as e:
            return False
    
    async def get_scene_context(self, 
                              user_progress_id: int,
                              scene_id: int,
                              include_conversations: bool = True,
                              limit: int = 20) -> Dict[str, Any]:
        """Get comprehensive scene context"""
        
        scene_key = self.get_scene_key(user_progress_id, scene_id)
        shared_key = self.get_shared_key(user_progress_id, scene_id)
        
        # Get from memory first
        with self._lock:
            scene_context = self.scene_contexts.get(scene_key, {})
            shared_context = self.shared_contexts.get(shared_key, {})
        
        # If not in memory, load from database
        if not scene_context:
            scene_context = await self._load_scene_memory(user_progress_id, scene_id)
            if scene_context:
                with self._lock:
                    self.scene_contexts[scene_key] = scene_context
        
        if not shared_context:
            shared_context = await self._load_shared_memory(user_progress_id, scene_id)
            if shared_context:
                with self._lock:
                    self.shared_contexts[shared_key] = shared_context
        
        # Get recent conversations if requested
        conversations = []
        if include_conversations:
            conversations = await self._get_recent_conversations(user_progress_id, scene_id, limit)
        
        # Combine context
        combined_context = {
            "scene_context": scene_context,
            "shared_context": shared_context,
            "recent_conversations": conversations,
            "persona_memories": self._get_persona_memories_for_scene(user_progress_id, scene_id)
        }
        
        return combined_context
    
    async def get_persona_context(self, 
                                user_progress_id: int,
                                scene_id: int,
                                persona_id: int) -> Dict[str, Any]:
        """Get persona-specific context and memory"""
        
        persona_key = self.get_persona_key(user_progress_id, scene_id, persona_id)
        
        # Get from memory first
        with self._lock:
            persona_memory = self.persona_memories.get(persona_key, {})
        
        # If not in memory, load from database
        if not persona_memory:
            persona_memory = await self._load_persona_memory(user_progress_id, scene_id, persona_id)
            if persona_memory:
                with self._lock:
                    self.persona_memories[persona_key] = persona_memory
        
        # Get scene context
        scene_context = await self.get_scene_context(user_progress_id, scene_id, include_conversations=False)
        
        # Get persona-specific conversations
        persona_conversations = await self._get_persona_conversations(user_progress_id, scene_id, persona_id)
        
        return {
            "persona_memory": persona_memory,
            "scene_context": scene_context,
            "persona_conversations": persona_conversations
        }
    
    async def add_shared_insight(self, 
                               user_progress_id: int,
                               scene_id: int,
                               insight: str,
                               insight_type: str = "general",
                               importance: float = 0.5,
                               source_persona_id: Optional[int] = None) -> bool:
        """Add shared insight to scene memory"""
        
        scene_key = self.get_scene_key(user_progress_id, scene_id)
        shared_key = self.get_shared_key(user_progress_id, scene_id)
        
        try:
            insight_entry = {
                "insight": insight,
                "type": insight_type,
                "importance": importance,
                "source_persona_id": source_persona_id,
                "timestamp": datetime.utcnow()
            }
            
            # Add to scene context
            with self._lock:
                if scene_key in self.scene_contexts:
                    self.scene_contexts[scene_key]["shared_insights"].append(insight_entry)
                    self.scene_contexts[scene_key]["last_updated"] = datetime.utcnow()
                
                # Add to shared context
                if shared_key in self.shared_contexts:
                    self.shared_contexts[shared_key]["collective_insights"].append(insight_entry)
                    self.shared_contexts[shared_key]["last_updated"] = datetime.utcnow()
            
            # Store in database
            await memory_service.store_memory(
                session_id=shared_key,
                memory_type="shared_insight",
                memory_content=insight,
                user_progress_id=user_progress_id,
                scene_id=scene_id,
                persona_id=source_persona_id,
                importance_score=importance,
                metadata={"type": insight_type}
            )
            
            return True
            
        except Exception as e:
            return False
    
    async def add_learning_moment(self, 
                                user_progress_id: int,
                                scene_id: int,
                                learning_moment: str,
                                learning_type: str = "insight",
                                relevance_score: float = 0.7) -> bool:
        """Add learning moment to scene memory"""
        
        scene_key = self.get_scene_key(user_progress_id, scene_id)
        
        try:
            learning_entry = {
                "moment": learning_moment,
                "type": learning_type,
                "relevance_score": relevance_score,
                "timestamp": datetime.utcnow()
            }
            
            # Add to scene context
            with self._lock:
                if scene_key in self.scene_contexts:
                    self.scene_contexts[scene_key]["learning_moments"].append(learning_entry)
                    self.scene_contexts[scene_key]["last_updated"] = datetime.utcnow()
            
            # Store in database
            await memory_service.store_memory(
                session_id=scene_key,
                memory_type="learning_moment",
                memory_content=learning_moment,
                user_progress_id=user_progress_id,
                scene_id=scene_id,
                importance_score=relevance_score,
                metadata={"type": learning_type}
            )
            
            return True
            
        except Exception as e:
            return False
    
    async def update_scene_progress(self, 
                                  user_progress_id: int,
                                  scene_id: int,
                                  progress_data: Dict[str, Any]) -> bool:
        """Update scene progress in shared memory"""
        
        shared_key = self.get_shared_key(user_progress_id, scene_id)
        
        try:
            with self._lock:
                if shared_key in self.shared_contexts:
                    self.shared_contexts[shared_key]["scene_progress"].update(progress_data)
                    self.shared_contexts[shared_key]["last_updated"] = datetime.utcnow()
            
            # Store in database
            await memory_service.store_memory(
                session_id=shared_key,
                memory_type="scene_progress",
                memory_content=json.dumps(progress_data),
                user_progress_id=user_progress_id,
                scene_id=scene_id,
                importance_score=0.8,
                metadata={"progress_update": True}
            )
            
            return True
            
        except Exception as e:
            return False
    
    async def get_scene_summary(self, 
                              user_progress_id: int,
                              scene_id: int) -> Dict[str, Any]:
        """Get comprehensive scene summary"""
        
        # Get scene context
        scene_context = await self.get_scene_context(user_progress_id, scene_id)
        
        # Get conversation summaries
        summaries = await conversation_service.get_conversation_summaries(
            user_progress_id, 
            summary_type="scene", 
            scene_id=scene_id
        )
        
        # Get shared insights and learning moments
        shared_insights = scene_context.get("scene_context", {}).get("shared_insights", [])
        learning_moments = scene_context.get("scene_context", {}).get("learning_moments", [])
        
        return {
            "scene_id": scene_id,
            "user_progress_id": user_progress_id,
            "scene_data": scene_context.get("scene_context", {}).get("scene_data", {}),
            "conversation_count": len(scene_context.get("recent_conversations", [])),
            "shared_insights": shared_insights,
            "learning_moments": learning_moments,
            "summaries": [{"type": s.summary_type, "text": s.summary_text} for s in summaries],
            "persona_interactions": self._get_persona_interaction_summary(user_progress_id, scene_id),
            "last_updated": scene_context.get("scene_context", {}).get("last_updated")
        }
    
    async def transition_to_next_scene(self, 
                                     user_progress_id: int,
                                     current_scene_id: int,
                                     next_scene_id: int) -> bool:
        """Handle transition to next scene with memory transfer"""
        
        try:
            # Get current scene summary
            current_summary = await self.get_scene_summary(user_progress_id, current_scene_id)
            
            # Create transition summary
            transition_summary = {
                "from_scene_id": current_scene_id,
                "to_scene_id": next_scene_id,
                "transition_data": current_summary,
                "timestamp": datetime.utcnow()
            }
            
            # Store transition summary
            await conversation_service.store_conversation_summary(
                user_progress_id=user_progress_id,
                summary_type="scene_transition",
                summary_text=json.dumps(transition_summary),
                scene_id=current_scene_id,
                metadata={"transition": True, "next_scene_id": next_scene_id}
            )
            
            # Clear current scene memory (optional - you might want to keep it for reference)
            # await self._clear_scene_memory(user_progress_id, current_scene_id)
            
            return True
            
        except Exception as e:
            return False
    
    def _get_persona_memories_for_scene(self, user_progress_id: int, scene_id: int) -> Dict[str, Any]:
        """Get all persona memories for a scene"""
        persona_memories = {}
        
        with self._lock:
            for key, memory in self.persona_memories.items():
                if (memory.get("user_progress_id") == user_progress_id and 
                    memory.get("scene_id") == scene_id):
                    persona_memories[memory["persona_name"]] = memory
        
        return persona_memories
    
    def _get_persona_interaction_summary(self, user_progress_id: int, scene_id: int) -> Dict[str, int]:
        """Get summary of persona interactions"""
        interaction_counts = {}
        
        with self._lock:
            for key, memory in self.persona_memories.items():
                if (memory.get("user_progress_id") == user_progress_id and 
                    memory.get("scene_id") == scene_id):
                    persona_name = memory["persona_name"]
                    interaction_count = len(memory.get("interactions", []))
                    interaction_counts[persona_name] = interaction_count
        
        return interaction_counts
    
    async def _persist_scene_memory(self, 
                                  user_progress_id: int,
                                  scene_id: int,
                                  scene_data: Dict[str, Any],
                                  personas: List[ScenarioPersona]) -> bool:
        """Persist scene memory to database"""
        try:
            # Store scene initialization
            await memory_service.store_memory(
                session_id=self.get_scene_key(user_progress_id, scene_id),
                memory_type="scene_initialization",
                memory_content=json.dumps({
                    "scene_data": scene_data,
                    "personas": [{"id": p.id, "name": p.name, "role": p.role} for p in personas]
                }),
                user_progress_id=user_progress_id,
                scene_id=scene_id,
                importance_score=1.0,
                metadata={"initialization": True}
            )
            
            return True
            
        except Exception as e:
            return False
    
    async def _store_conversation_memory(self, 
                                       user_progress_id: int,
                                       scene_id: int,
                                       conversation_log: ConversationLog) -> bool:
        """Store conversation in memory system"""
        try:
            await memory_service.store_memory(
                session_id=self.get_scene_key(user_progress_id, scene_id),
                memory_type="conversation",
                memory_content=conversation_log.message_content,
                user_progress_id=user_progress_id,
                scene_id=scene_id,
                persona_id=conversation_log.persona_id,
                importance_score=0.6,
                metadata={
                    "message_type": conversation_log.message_type,
                    "sender_name": conversation_log.sender_name,
                    "message_order": conversation_log.message_order
                }
            )
            
            return True
            
        except Exception as e:
            return False
    
    async def _load_scene_memory(self, user_progress_id: int, scene_id: int) -> Optional[Dict[str, Any]]:
        """Load scene memory from database"""
        try:
            memories = await memory_service.retrieve_memories(
                session_id=self.get_scene_key(user_progress_id, scene_id),
                limit=100
            )
            
            if not memories:
                return None
            
            # Reconstruct scene context from memories
            scene_context = {
                "scene_id": scene_id,
                "user_progress_id": user_progress_id,
                "conversation_history": [],
                "shared_insights": [],
                "learning_moments": [],
                "last_updated": datetime.utcnow()
            }
            
            for memory in memories:
                if memory.memory_type == "conversation":
                    scene_context["conversation_history"].append({
                        "content": memory.memory_content,
                        "metadata": memory.memory_metadata,
                        "timestamp": memory.created_at
                    })
                elif memory.memory_type == "shared_insight":
                    scene_context["shared_insights"].append({
                        "insight": memory.memory_content,
                        "metadata": memory.memory_metadata,
                        "timestamp": memory.created_at
                    })
                elif memory.memory_type == "learning_moment":
                    scene_context["learning_moments"].append({
                        "moment": memory.memory_content,
                        "metadata": memory.memory_metadata,
                        "timestamp": memory.created_at
                    })
            
            return scene_context
            
        except Exception as e:
            return None
    
    async def _load_shared_memory(self, user_progress_id: int, scene_id: int) -> Optional[Dict[str, Any]]:
        """Load shared memory from database"""
        try:
            memories = await memory_service.retrieve_memories(
                session_id=self.get_shared_key(user_progress_id, scene_id),
                limit=50
            )
            
            if not memories:
                return None
            
            # Reconstruct shared context from memories
            shared_context = {
                "scene_id": scene_id,
                "user_progress_id": user_progress_id,
                "shared_knowledge": {},
                "collective_insights": [],
                "scene_progress": {},
                "last_updated": datetime.utcnow()
            }
            
            for memory in memories:
                if memory.memory_type == "shared_insight":
                    shared_context["collective_insights"].append({
                        "insight": memory.memory_content,
                        "metadata": memory.memory_metadata,
                        "timestamp": memory.created_at
                    })
                elif memory.memory_type == "scene_progress":
                    try:
                        progress_data = json.loads(memory.memory_content)
                        shared_context["scene_progress"].update(progress_data)
                    except (json.JSONDecodeError, ValueError) as e:
                        pass
            
            return shared_context
            
        except Exception as e:
            return None
    
    async def _load_persona_memory(self, 
                                 user_progress_id: int,
                                 scene_id: int,
                                 persona_id: int) -> Optional[Dict[str, Any]]:
        """Load persona memory from database"""
        try:
            memories = await memory_service.retrieve_memories(
                session_id=self.get_persona_key(user_progress_id, scene_id, persona_id),
                limit=50
            )
            
            if not memories:
                return None
            
            # Reconstruct persona memory from memories
            persona_memory = {
                "persona_id": persona_id,
                "scene_id": scene_id,
                "user_progress_id": user_progress_id,
                "personal_memory": [],
                "interactions": [],
                "insights": [],
                "last_updated": datetime.utcnow()
            }
            
            for memory in memories:
                if memory.memory_type == "conversation":
                    persona_memory["interactions"].append({
                        "content": memory.memory_content,
                        "metadata": memory.memory_metadata,
                        "timestamp": memory.created_at
                    })
                elif memory.memory_type == "personal_insight":
                    persona_memory["insights"].append({
                        "insight": memory.memory_content,
                        "metadata": memory.memory_metadata,
                        "timestamp": memory.created_at
                    })
            
            return persona_memory
            
        except Exception as e:
            return None
    
    async def _get_recent_conversations(self, 
                                      user_progress_id: int,
                                      scene_id: int,
                                      limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent conversations for scene"""
        try:
            db = SessionLocal()
            try:
                conversations = db.query(ConversationLog).filter(
                    and_(
                        ConversationLog.user_progress_id == user_progress_id,
                        ConversationLog.scene_id == scene_id
                    )
                ).order_by(desc(ConversationLog.timestamp)).limit(limit).all()
                
                return [
                    {
                        "id": conv.id,
                        "message_type": conv.message_type,
                        "sender_name": conv.sender_name,
                        "persona_id": conv.persona_id,
                        "message_content": conv.message_content,
                        "timestamp": conv.timestamp,
                        "message_order": conv.message_order
                    }
                    for conv in conversations
                ]
            finally:
                db.close()
        except Exception as e:
            return []
    
    async def _get_persona_conversations(self, 
                                       user_progress_id: int,
                                       scene_id: int,
                                       persona_id: int,
                                       limit: int = 10) -> List[Dict[str, Any]]:
        """Get persona-specific conversations"""
        try:
            db = SessionLocal()
            try:
                conversations = db.query(ConversationLog).filter(
                    and_(
                        ConversationLog.user_progress_id == user_progress_id,
                        ConversationLog.scene_id == scene_id,
                        ConversationLog.persona_id == persona_id
                    )
                ).order_by(desc(ConversationLog.timestamp)).limit(limit).all()
                
                return [
                    {
                        "id": conv.id,
                        "message_type": conv.message_type,
                        "sender_name": conv.sender_name,
                        "message_content": conv.message_content,
                        "timestamp": conv.timestamp,
                        "message_order": conv.message_order
                    }
                    for conv in conversations
                ]
            finally:
                db.close()
        except Exception as e:
            return []

# Global scene memory manager instance
scene_memory_manager = SceneMemoryManager()