"""
Memory Service for AI Agent Education Platform
Handles memory storage and retrieval with PGVector semantic search
"""
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging
from sqlalchemy import desc

from common.db.core import SessionLocal
from common.db.models import SessionMemory
from .langchain_service import langchain_manager

logger = logging.getLogger(__name__)


class MemoryService:
    """Manages agent memory storage and retrieval with PGVector semantic search"""
    
    def __init__(self):
        self.vectorstore = langchain_manager.vectorstore
        self.embeddings = langchain_manager.embeddings
    
    async def store_memory(self, 
                         session_id: str,
                         memory_type: str,
                         memory_content: str,
                         user_progress_id: int,
                         scene_id: Optional[int] = None,
                         persona_id: Optional[int] = None,
                         importance_score: float = 0.5,
                         metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Store memory in both SessionMemory table AND PGVector with embedding
        """
        try:
            db = SessionLocal()
            try:
                # Store in SessionMemory table
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
                db.flush()  # Flush to get the ID
                
                # Store in PGVector for semantic search
                if self.vectorstore:
                    try:
                        # Create embedding for the memory content
                        embedding_vector = await self._get_embedding(memory_content)
                        
                        # Add to vectorstore with metadata
                        self.vectorstore.add_texts(
                            texts=[memory_content],
                            metadatas=[{
                                "session_id": session_id,
                                "memory_type": memory_type,
                                "user_progress_id": str(user_progress_id),
                                "scene_id": str(scene_id) if scene_id else None,
                                "persona_id": str(persona_id) if persona_id else None,
                                "importance_score": str(importance_score),
                                "memory_id": str(memory.id),
                                "created_at": datetime.utcnow().isoformat()
                            }]
                        )
                    except Exception as e:
                        logger.warning(f"Failed to store memory in PGVector: {e}")
                        # Continue even if vectorstore fails
                
                db.commit()
                return True
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error storing memory: {e}")
            return False
    
    async def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for text"""
        try:
            import asyncio
            # Use embeddings model to create embedding (sync method in executor for async)
            embedding = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.embeddings.embed_query(text)
            )
            return embedding
        except Exception as e:
            logger.error(f"Error creating embedding: {e}")
            return []
    
    async def retrieve_memories_by_similarity(self,
                                            session_id: str,
                                            query_text: str,
                                            memory_type: Optional[str] = None,
                                            limit: int = 10) -> List[SessionMemory]:
        """Retrieve memories using PGVector similarity search only"""
        if not self.vectorstore:
            logger.warning("PGVector not available, falling back to SQL retrieval")
            return await self._retrieve_memories_sql(session_id, memory_type, limit)
        
        try:
            # Use similarity search with metadata filter
            filter_dict = {"session_id": session_id}
            if memory_type:
                filter_dict["memory_type"] = memory_type
            
            # Get more results for filtering
            docs_with_scores = self.vectorstore.similarity_search_with_score(
                query_text,
                k=limit * 2,  # Get more for filtering
                filter=filter_dict
            )
            
            # Extract memory IDs from metadata
            memory_ids = []
            for doc, _ in docs_with_scores:
                memory_id = doc.metadata.get("memory_id")
                if memory_id:
                    memory_ids.append(int(memory_id))
            
            # Retrieve full memory objects from database
            if memory_ids:
                db = SessionLocal()
                try:
                    memories = db.query(SessionMemory).filter(
                        SessionMemory.id.in_(memory_ids)
                    ).limit(limit).all()
                    return memories
                finally:
                    db.close()
            
            return []
        except Exception as e:
            logger.error(f"Error retrieving memories by similarity: {e}")
            return await self._retrieve_memories_sql(session_id, memory_type, limit)
    
    async def retrieve_memories_hybrid(self,
                                      session_id: str,
                                      query_text: str,
                                      memory_type: Optional[str] = None,
                                      limit: int = 10,
                                      min_importance: float = 0.0) -> List[SessionMemory]:
        """
        Retrieve memories using hybrid ranking: combines vector similarity + importance_score
        Hybrid score: (similarity * 0.7) + (importance_score * 0.3)
        """
        if not self.vectorstore:
            logger.warning("PGVector not available, falling back to SQL retrieval")
            return await self._retrieve_memories_sql(session_id, memory_type, limit, min_importance)
        
        try:
            # Use similarity search with metadata filter
            filter_dict = {"session_id": session_id}
            if memory_type:
                filter_dict["memory_type"] = memory_type
            
            # Get more results for hybrid ranking
            docs_with_scores = self.vectorstore.similarity_search_with_score(
                query_text,
                k=limit * 3,  # Get more for hybrid ranking
                filter=filter_dict
            )
            
            # Combine similarity score with importance_score
            ranked_results = []
            for doc, similarity_score in docs_with_scores:
                try:
                    importance = float(doc.metadata.get("importance_score", 0.5))
                    if importance < min_importance:
                        continue
                    
                    # Normalize similarity score (vector similarity is distance, invert for score)
                    # Similarity scores are typically between 0 and 1, where 1 is most similar
                    # If using distance, lower is better, so we might need to invert
                    similarity_normalized = 1.0 - similarity_score if similarity_score > 1.0 else similarity_score
                    
                    # Hybrid score: 70% similarity, 30% importance
                    hybrid_score = (similarity_normalized * 0.7) + (importance * 0.3)
                    ranked_results.append({
                        "memory_id": int(doc.metadata.get("memory_id", 0)),
                        "hybrid_score": hybrid_score,
                        "similarity": similarity_normalized,
                        "importance": importance
                    })
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error processing memory metadata: {e}")
                    continue
            
            # Sort by hybrid score and take top limit
            ranked_results.sort(key=lambda x: x["hybrid_score"], reverse=True)
            top_memory_ids = [r["memory_id"] for r in ranked_results[:limit]]
            
            # Retrieve full memory objects from database
            if top_memory_ids:
                db = SessionLocal()
                try:
                    # Preserve order by using a CASE statement or sorting in Python
                    memories = db.query(SessionMemory).filter(
                        SessionMemory.id.in_(top_memory_ids)
                    ).all()
                    
                    # Sort to preserve hybrid ranking order
                    memory_dict = {m.id: m for m in memories}
                    sorted_memories = [memory_dict[mid] for mid in top_memory_ids if mid in memory_dict]
                    
                    # Update access count
                    memory_ids_list = [m.id for m in sorted_memories]
                    db.query(SessionMemory).filter(
                        SessionMemory.id.in_(memory_ids_list)
                    ).update({
                        SessionMemory.access_count: SessionMemory.access_count + 1,
                        SessionMemory.last_accessed: datetime.utcnow()
                    }, synchronize_session=False)
                    db.commit()
                    
                    return sorted_memories
                finally:
                    db.close()
            
            return []
        except Exception as e:
            logger.error(f"Error retrieving memories with hybrid ranking: {e}")
            return await self._retrieve_memories_sql(session_id, memory_type, limit, min_importance)
    
    async def retrieve_memories(self, 
                              session_id: str,
                              memory_type: Optional[str] = None,
                              limit: int = 10,
                              min_importance: float = 0.0,
                              query_text: Optional[str] = None) -> List[SessionMemory]:
        """
        Retrieve memories - backward compatible
        Uses hybrid approach if query_text is provided, otherwise uses SQL
        """
        if query_text:
            return await self.retrieve_memories_hybrid(
                session_id=session_id,
                query_text=query_text,
                memory_type=memory_type,
                limit=limit,
                min_importance=min_importance
            )
        else:
            return await self._retrieve_memories_sql(
                session_id=session_id,
                memory_type=memory_type,
                limit=limit,
                min_importance=min_importance
            )
    
    async def _retrieve_memories_sql(self,
                                    session_id: str,
                                    memory_type: Optional[str] = None,
                                    limit: int = 10,
                                    min_importance: float = 0.0) -> List[SessionMemory]:
        """Retrieve memories using SQL (fallback when PGVector not available)"""
        try:
            db = SessionLocal()
            try:
                from sqlalchemy import and_
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
                    ).update({
                        SessionMemory.access_count: SessionMemory.access_count + 1,
                        SessionMemory.last_accessed: datetime.utcnow()
                    }, synchronize_session=False)
                    db.commit()
                
                return memories
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error retrieving memories from SQL: {e}")
            return []


# Global memory service instance
memory_service = MemoryService()

