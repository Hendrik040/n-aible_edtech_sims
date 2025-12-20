"""
Orchestrator Manager.

Manages ChatOrchestrator lifecycle: loading, initialization, state persistence.
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from modules.simulation.repository import SimulationRepository
from .orchestrator import ChatOrchestrator
from common.db.models import UserProgress, User
from common.config import get_settings

settings = get_settings()
_is_dev = settings.environment != "production"


class OrchestratorManager:
    """Manages ChatOrchestrator lifecycle and state persistence."""
    
    def __init__(self, db: Session, repository: SimulationRepository):
        self.db = db
        self.repository = repository
    
    def load_orchestrator(
        self,
        user_progress: UserProgress,
        user_id: int
    ) -> ChatOrchestrator:
        """
        Load and initialize ChatOrchestrator from UserProgress.
        
        Args:
            user_progress: UserProgress instance with orchestrator_data
            user_id: ID of the user (to check role for professor test)
            
        Returns:
            Initialized ChatOrchestrator instance
        """
        if not user_progress.orchestrator_data:
            raise ValueError("UserProgress has no orchestrator_data")
        
        # Get is_professor_test flag from orchestrator_data (stored when UserProgress was created)
        # Fallback to querying user only for backward compatibility with old records
        is_professor_test = user_progress.orchestrator_data.get('is_professor_test', False)
        if 'is_professor_test' not in user_progress.orchestrator_data:
            # Backward compatibility: query user if flag not present (shouldn't happen for new records)
        user = self.db.query(User).filter(User.id == user_id).first()
        is_professor_test = user and user.role in ['professor', 'admin'] if user else False
            # Store it for future use
            user_progress.orchestrator_data['is_professor_test'] = is_professor_test
        
        orchestrator = ChatOrchestrator(
            user_progress.orchestrator_data,
            enable_langchain=True,
            is_professor_test=is_professor_test,
            db=self.db,
        )
        orchestrator.user_progress_id = user_progress.id
        
        # Initialize _last_scene_id if not set
        if not hasattr(orchestrator, '_last_scene_id'):
            orchestrator._last_scene_id = None
        
        # Initialize current_scene_id from user progress if not set
        if not hasattr(orchestrator.state, 'current_scene_id') or orchestrator.state.current_scene_id is None or orchestrator.state.current_scene_id == "":
            orchestrator.state.current_scene_id = user_progress.current_scene_id
        
        return orchestrator
    
    async def initialize_langchain_session(
        self,
        orchestrator: ChatOrchestrator,
        user_progress_id: int
    ) -> bool:
        """
        Initialize LangChain session for the orchestrator.
        
        Args:
            orchestrator: ChatOrchestrator instance
            user_progress_id: ID of the user progress
            
        Returns:
            True if initialization successful, False otherwise
        """
        if orchestrator.langchain_enabled and not orchestrator.state.scene_memory_initialized:
            return await orchestrator.initialize_langchain_session(user_progress_id)
        return True
    
    def load_orchestrator_state(self, orchestrator: ChatOrchestrator, user_progress: UserProgress) -> None:
        """
        Load saved orchestrator state from UserProgress.
        
        Args:
            orchestrator: ChatOrchestrator instance to update
            user_progress: UserProgress instance with state data
        """
        if user_progress.orchestrator_data and 'state' in user_progress.orchestrator_data:
            saved_state = user_progress.orchestrator_data['state']
            orchestrator.state.simulation_started = saved_state.get('simulation_started', False)
            orchestrator.state.user_ready = saved_state.get('user_ready', False)
            orchestrator.state.current_scene_index = saved_state.get('current_scene_index', 0)
            orchestrator.state.turn_count = saved_state.get('turn_count', 0)
            orchestrator.state.state_variables = saved_state.get('state_variables', {})
            # Load session_id if it exists (critical for conversation history persistence)
            if 'session_id' in saved_state:
                orchestrator.state.session_id = saved_state['session_id']
    
    def save_orchestrator_state(
        self,
        orchestrator: ChatOrchestrator,
        user_progress: UserProgress
    ) -> None:
        """
        Persist orchestrator state to UserProgress.
        
        Args:
            orchestrator: ChatOrchestrator instance
            user_progress: UserProgress instance to update
        """
        import logging
        logger = logging.getLogger(__name__)
        
        state_dict = {
            'current_scene_id': orchestrator.state.current_scene_id,
            'current_scene_index': orchestrator.state.current_scene_index,
            'turn_count': orchestrator.state.turn_count,
            'simulation_started': orchestrator.state.simulation_started,
            'user_ready': orchestrator.state.user_ready,
            'state_variables': orchestrator.state.state_variables,
            # Save session_id so it persists across requests (critical for conversation history)
            'session_id': getattr(orchestrator.state, 'session_id', '')
        }
        
        if not user_progress.orchestrator_data:
            user_progress.orchestrator_data = {}
        
        user_progress.orchestrator_data['state'] = state_dict
        
        # Log state save for debugging (especially turn_count updates)
        logger.debug(
            f"[STATE_SAVE] Saved orchestrator state: user_progress_id={user_progress.id}, "
            f"turn_count={orchestrator.state.turn_count}, scene_id={orchestrator.state.current_scene_id}"
        )
    
    def handle_scene_transition_cleanup(
        self,
        orchestrator: ChatOrchestrator,
        user_progress_id: int
    ) -> None:
        """
        Handle scene transition cleanup.
        
        Note: With stateless PersonaAgent, memory is created fresh per request,
        so we don't need to clear memory. This method now only tracks scene transitions
        for logging/debugging purposes. Vectorstore cleanup is optional and can be
        done via clear_conversation_history() if needed.
        
        Args:
            orchestrator: ChatOrchestrator instance
            user_progress_id: ID of the user progress
        """
        if orchestrator.langchain_enabled:
            current_scene_id_state = orchestrator.state.current_scene_id
            
            # Check if we're in a different scene than before
            if orchestrator._last_scene_id is not None and orchestrator._last_scene_id != current_scene_id_state:
                if _is_dev:
                    print(f"Scene transition detected: {orchestrator._last_scene_id} -> {current_scene_id_state}")
                
                # Note: No need to clear memory - PersonaAgent is stateless per request
                # Memory is created fresh for each chat() call, so no state persists between requests
                # Vectorstore cleanup is optional and can be done via clear_conversation_history() if needed
            
            orchestrator._last_scene_id = current_scene_id_state

