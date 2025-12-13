"""
Conversation Service for AI Agent Education Platform
Handles conversation summary storage and retrieval
"""
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging
from sqlalchemy import desc

from common.db.core import SessionLocal
from common.db.models import ConversationSummaries

logger = logging.getLogger(__name__)


class ConversationService:
    """Manages conversation summaries"""
    
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
            db = SessionLocal()
            try:
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
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error storing conversation summary: {e}")
            return False
    
    async def get_conversation_summaries(self, 
                                       user_progress_id: int,
                                       summary_type: Optional[str] = None,
                                       scene_id: Optional[int] = None,
                                       limit: int = 10) -> List[ConversationSummaries]:
        """Get conversation summaries"""
        
        try:
            db = SessionLocal()
            try:
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
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error getting conversation summaries: {e}")
            return []


# Global conversation service instance
conversation_service = ConversationService()

