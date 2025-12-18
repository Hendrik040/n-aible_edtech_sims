"""
Callback handlers for persona agents.

Used by persona_agent.py
"""

from datetime import datetime
from typing import Dict, List, Any, Optional

import logging
from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema.output import LLMResult
from sqlalchemy.orm import Session

from common.config import get_settings
from common.db.core import SessionLocal
from common.db.models import ConversationLog


settings = get_settings()
debug_log = logging.getLogger(__name__).debug


class PersonaCallbackHandler(BaseCallbackHandler):
    """Callback handler for persona interactions."""

    def __init__(
        self,
        persona_id: int,
        user_progress_id: int,
        scene_id: int,
        db: Optional[Session] = None,
    ):
        self.persona_id = persona_id
        self.user_progress_id = user_progress_id
        self.scene_id = scene_id
        self.start_time = None
        self.tokens_used = 0
        # Prefer using the request-scoped session if provided; fall back to SessionLocal.
        self._db: Optional[Session] = db

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs) -> None:
        """Called when LLM starts."""
        self.start_time = datetime.utcnow()

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        """Called when LLM ends."""
        if self.start_time:
            processing_time = (datetime.utcnow() - self.start_time).total_seconds()
            # Log the interaction
            self._log_conversation(response.generations[0][0].text, processing_time)

    def _log_conversation(self, response_text: str, processing_time: float):
        """Log conversation to database using a shared session when available."""
        db: Optional[Session] = None
        own_session = False
        try:
            if self._db is not None:
                db = self._db
            else:
                db = SessionLocal()
                own_session = True

            conversation_log = ConversationLog(
                user_progress_id=self.user_progress_id,
                scene_id=self.scene_id,
                message_type="ai_persona",
                sender_name="Persona",
                persona_id=self.persona_id,
                message_content=response_text,
                message_order=self._next_message_order(db),
                ai_model_version=settings.openai_model,
                processing_time=processing_time,
                timestamp=datetime.utcnow(),
            )
            db.add(conversation_log)
            db.commit()
        except Exception as e:
            debug_log(f"Error logging conversation: {e}")
            raise
        finally:
            if own_session and db is not None:
                db.close()

    def _next_message_order(self, db: Session) -> int:
        last = (
            db.query(ConversationLog.message_order)
            .filter(
                ConversationLog.user_progress_id == self.user_progress_id,
                ConversationLog.scene_id == self.scene_id,
            )
            .order_by(ConversationLog.message_order.desc())
            .first()
        )
        return (last[0] if last else 0) + 1


__all__ = ["PersonaCallbackHandler"]

