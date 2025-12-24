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
        session_id: str,
        db: Optional[Session] = None,
    ):
        self.persona_id = persona_id
        self.user_progress_id = user_progress_id
        self.scene_id = scene_id
        self.session_id = session_id
        self.start_time = None
        self.tokens_used = 0
        self.agent_steps = 0  # Track number of agent steps (tool calls + LLM calls)
        # Prefer using the request-scoped session if provided; fall back to SessionLocal.
        self._db: Optional[Session] = db
        # Track if response was saved (for fallback mechanism)
        self._response_saved = False

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs) -> None:
        """Called when LLM starts."""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[PERSONA_CALLBACK] on_llm_start called for persona_id={self.persona_id}, user_progress_id={self.user_progress_id}")
        self.start_time = datetime.utcnow()
        self.agent_steps += 1  # Count LLM call as a step

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        """Called when LLM ends."""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[PERSONA_CALLBACK] on_llm_end called for persona_id={self.persona_id}, user_progress_id={self.user_progress_id}")
        
        if self.start_time:
            processing_time = (datetime.utcnow() - self.start_time).total_seconds()
            # Log the interaction
            try:
                response_text = response.generations[0][0].text
                logger.info(f"[PERSONA_CALLBACK] Extracted response text: {len(response_text)} chars")
                self._log_conversation(response_text, processing_time)
            except (IndexError, AttributeError, KeyError) as e:
                logger.error(
                    f"[PERSONA_CALLBACK] Error extracting response from LLMResult: {e}, "
                    f"response type: {type(response)}, response keys: {dir(response) if hasattr(response, '__dict__') else 'N/A'}",
                    exc_info=True
                )
                # Try to get response text from alternative locations
                if hasattr(response, 'generations') and response.generations:
                    if isinstance(response.generations[0], list) and len(response.generations[0]) > 0:
                        if hasattr(response.generations[0][0], 'text'):
                            response_text = response.generations[0][0].text
                            self._log_conversation(response_text, processing_time)
                        else:
                            logger.error(f"[PERSONA_CALLBACK] Response object structure: {response.generations[0][0]}")
        else:
            logger.warning(f"[PERSONA_CALLBACK] on_llm_end called but start_time is None for persona_id={self.persona_id}")
    
    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs) -> None:
        """Called when a tool starts."""
        self.agent_steps += 1  # Count tool call as a step
    
    def on_agent_finish(self, finish: Dict[str, Any], **kwargs) -> None:
        """Called when agent finishes - log step count."""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            f"[AGENT_STEPS] Persona {self.persona_id} completed with {self.agent_steps} steps "
            f"(user_progress_id={self.user_progress_id}, scene_id={self.scene_id})"
        )

    def _log_conversation(self, response_text: str, processing_time: float):
        """Log conversation to database using a shared session when available."""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            f"[PERSONA_CALLBACK] _log_conversation called: persona_id={self.persona_id}, "
            f"user_progress_id={self.user_progress_id}, response_length={len(response_text)}, "
            f"has_db_session={self._db is not None}"
        )
        
        db: Optional[Session] = None
        own_session = False
        try:
            if self._db is not None:
                db = self._db
                logger.info(f"[PERSONA_CALLBACK] Using provided database session")
            else:
                db = SessionLocal()
                own_session = True
                logger.info(f"[PERSONA_CALLBACK] Created new database session")

            conversation_log = ConversationLog(
                user_progress_id=self.user_progress_id,
                scene_id=self.scene_id,
                session_id=self.session_id,  # CRITICAL: Must match session_id used when loading history
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
            
            # Mark as saved for fallback mechanism
            self._response_saved = True
            
            # Log successful save for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.info(
                f"[PERSONA_CALLBACK] Saved persona response: persona_id={self.persona_id}, "
                f"user_progress_id={self.user_progress_id}, scene_id={self.scene_id}, "
                f"message_length={len(response_text)}, order={conversation_log.message_order}"
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(
                f"[PERSONA_CALLBACK] Error logging conversation: persona_id={self.persona_id}, "
                f"user_progress_id={self.user_progress_id}, error={e}",
                exc_info=True
            )
            debug_log(f"Error logging conversation: {e}")
            raise
        finally:
            if own_session and db is not None:
                db.close()

    def _next_message_order(self, db: Session) -> int:
        """Get the next message order (optimized - only queries max message_order, not full object)."""
        from sqlalchemy import func
        max_order = db.query(func.max(ConversationLog.message_order)).filter(
            ConversationLog.user_progress_id == self.user_progress_id
        ).scalar()
        return (max_order + 1) if max_order is not None else 1


__all__ = ["PersonaCallbackHandler"]

