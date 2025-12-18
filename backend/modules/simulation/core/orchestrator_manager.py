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
        
        # Check if this is a professor test simulation
        user = self.db.query(User).filter(User.id == user_id).first()
        is_professor_test = user and user.role in ['professor', 'admin'] if user else False
        
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
        state_dict = {
            'current_scene_id': orchestrator.state.current_scene_id,
            'current_scene_index': orchestrator.state.current_scene_index,
            'turn_count': orchestrator.state.turn_count,
            'simulation_started': orchestrator.state.simulation_started,
            'user_ready': orchestrator.state.user_ready,
            'state_variables': orchestrator.state.state_variables
        }
        
        if not user_progress.orchestrator_data:
            user_progress.orchestrator_data = {}
        
        user_progress.orchestrator_data['state'] = state_dict
    
    def handle_scene_transition_cleanup(
        self,
        orchestrator: ChatOrchestrator,
        user_progress_id: int
    ) -> None:
        """
        Clean up persona agents on scene transitions.
        
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
                
                # Clear conversation history for all existing persona agents
                if hasattr(orchestrator, 'persona_agents') and orchestrator.persona_agents:
                    for persona_id, agent in orchestrator.persona_agents.items():
                        if hasattr(agent, 'clear_conversation_history'):
                            agent.clear_conversation_history(user_progress_id)
            
            orchestrator._last_scene_id = current_scene_id_state

