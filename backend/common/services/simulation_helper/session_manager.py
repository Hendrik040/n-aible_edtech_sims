"""
Session Manager for AI Agent Education Platform
Handles agent session state management
"""
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import secrets
import logging

from common.db.core import SessionLocal
from common.db.models import AgentSessions
from .langchain_service import settings

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages agent sessions"""
    
    def __init__(self):
        self.session_timeout = settings.session_timeout
        self.active_sessions: Dict[str, Dict[str, Any]] = {}  # In-memory cache
    
    def generate_session_id(self, user_id: int, scenario_id: int, scene_id: int) -> str:
        """Generate unique, unguessable session ID"""
        return secrets.token_urlsafe(32)
    
    async def create_agent_session(self, 
                                 user_progress_id: int,
                                 agent_type: str,
                                 agent_id: Optional[str] = None,
                                 session_config: Optional[Dict[str, Any]] = None) -> str:
        """Create new agent session"""
        
        session_id = self.generate_session_id(
            user_progress_id, 0, 0  # Simplified for agent sessions
        )
        
        # Store session data in memory
        session_data = {
            "agent_type": agent_type,
            "agent_id": agent_id,
            "user_progress_id": user_progress_id,
            "created_at": datetime.utcnow(),
            "last_activity": datetime.utcnow(),
            "config": session_config or {},
            "session_state": {},
            "is_active": True
        }
        
        self.active_sessions[session_id] = session_data
        
        # Also store in database for persistence
        try:
            db = SessionLocal()
            try:
                agent_session = AgentSessions(
                    session_id=session_id,
                    user_progress_id=user_progress_id,
                    persona_id=None,  # Can be set separately if needed
                    agent_type=agent_type,
                    agent_id=agent_id,
                    session_type=None,
                    session_config=session_config or {},
                    session_state={},
                    is_active=True,
                    expires_at=datetime.utcnow() + timedelta(seconds=self.session_timeout)
                )
                
                db.add(agent_session)
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error creating agent session in database: {e}")
            # Don't fail if database write fails, memory is primary
        
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
            db = SessionLocal()
            try:
                agent_session = db.query(AgentSessions).filter(
                    AgentSessions.session_id == session_id,
                    AgentSessions.is_active == True,
                    AgentSessions.expires_at > datetime.utcnow()
                ).first()
                
                if agent_session:
                    # Restore to memory
                    self.active_sessions[session_id] = {
                        "agent_type": agent_session.agent_type,
                        "agent_id": agent_session.agent_id,
                        "user_progress_id": agent_session.user_progress_id,
                        "created_at": agent_session.created_at,
                        "last_activity": agent_session.last_activity or datetime.utcnow(),
                        "config": agent_session.session_config or {}
                    }
                    
                    return self.active_sessions[session_id]
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error getting agent session: {e}")
        
        return None
    
    async def update_session_state(self, 
                                 session_id: str, 
                                 state_updates: Dict[str, Any]) -> bool:
        """Update session state"""
        
        # Update memory
        if session_id in self.active_sessions:
            current_state = self.active_sessions[session_id].get("session_state", {})
            current_state.update(state_updates)
            self.active_sessions[session_id]["session_state"] = current_state
            self.active_sessions[session_id]["last_activity"] = datetime.utcnow()
        
        # Update database
        try:
            db = SessionLocal()
            try:
                agent_session = db.query(AgentSessions).filter(
                    AgentSessions.session_id == session_id
                ).first()
                
                if agent_session:
                    current_state = agent_session.session_state or {}
                    current_state.update(state_updates)
                    agent_session.session_state = current_state
                    agent_session.last_activity = datetime.utcnow()
                    agent_session.last_accessed_at = datetime.utcnow()
                    
                    db.commit()
                    return True
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error updating session state: {e}")
            return False
        
        return False
    
    async def expire_session(self, session_id: str) -> bool:
        """Expire and clean up session"""
        
        # Remove from memory
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
        
        # Update database
        try:
            db = SessionLocal()
            try:
                agent_session = db.query(AgentSessions).filter(
                    AgentSessions.session_id == session_id
                ).first()
                
                if agent_session:
                    agent_session.is_active = False
                    agent_session.expires_at = datetime.utcnow()
                    db.commit()
                    return True
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error expiring session: {e}")
            return False
        
        return False


# Global session manager instance
session_manager = SessionManager()

