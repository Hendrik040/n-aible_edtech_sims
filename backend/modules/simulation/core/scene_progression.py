"""
Scene Progression Handler.

Handles scene transitions, completion, and initialization.
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from modules.simulation.repository import SimulationRepository
from .orchestrator import ChatOrchestrator
from common.db.models import UserProgress, SceneProgress
from common.config import get_settings

settings = get_settings()
_is_dev = settings.environment != "production"


class SceneProgressionHandler:
    """Handles scene progression and transition logic."""
    
    def __init__(self, db: Session, repository: SimulationRepository):
        self.db = db
        self.repository = repository
    
    def mark_scene_complete(
        self,
        user_progress: UserProgress,
        scene_id: int
    ) -> None:
        """
        Mark a scene as completed in UserProgress and SceneProgress.
        
        Args:
            user_progress: UserProgress instance
            scene_id: ID of the scene to mark as complete
        """
        # Mark scene as completed in UserProgress
        completed_scenes = user_progress.scenes_completed or []
        if scene_id and scene_id not in completed_scenes:
            completed_scenes.append(scene_id)
            user_progress.scenes_completed = completed_scenes
        
        # Update SceneProgress for the completed scene
        scene_progress = self.repository.get_scene_progress(user_progress.id, scene_id)
        if scene_progress:
            scene_progress.status = "completed"
            scene_progress.completed_at = datetime.utcnow()
    
    def initialize_new_scene(
        self,
        user_progress: UserProgress,
        next_scene_id: int,
        orchestrator: ChatOrchestrator
    ) -> None:
        """
        Initialize a new scene (create SceneProgress, update UserProgress).
        
        Args:
            user_progress: UserProgress instance
            next_scene_id: ID of the next scene
            orchestrator: ChatOrchestrator instance (for cleanup)
        """
        # Update UserProgress current scene
        user_progress.current_scene_id = next_scene_id
        
        # Clear conversation history for scene transition
        if orchestrator.langchain_enabled and hasattr(orchestrator, 'persona_agents') and orchestrator.persona_agents:
            for agent_id, persona_agent in orchestrator.persona_agents.items():
                if hasattr(persona_agent, 'clear_conversation_history'):
                    persona_agent.clear_conversation_history(user_progress.id)
        
        # Create or reactivate SceneProgress for new scene
        new_scene_progress = self.repository.get_scene_progress(user_progress.id, next_scene_id)
        if not new_scene_progress:
            self.repository.create_scene_progress(
                user_progress_id=user_progress.id,
                scene_id=next_scene_id,
                status="in_progress"
            )
        else:
            new_scene_progress.status = "in_progress"
            new_scene_progress.started_at = datetime.utcnow()
    
    def progress_to_next_scene(
        self,
        orchestrator: ChatOrchestrator,
        user_progress: UserProgress,
        current_scene_id: int,
        generate_scene_intro_fn: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Progress to the next scene.
        
        Args:
            orchestrator: ChatOrchestrator instance
            user_progress: UserProgress instance
            current_scene_id: ID of the current scene being completed
            generate_scene_intro_fn: Optional function to generate scene intro message
            
        Returns:
            Dictionary with next_scene_id, next_scene data, and scene_intro_message
        """
        scenes = orchestrator.simulation.get('scenes', [])
        
        # Check if there's a next scene
        if orchestrator.state.current_scene_index + 1 < len(scenes):
            # Move to next scene
            next_scene_index = orchestrator.state.current_scene_index + 1
            next_scene = scenes[next_scene_index]
            next_scene_id = next_scene.get('id')
            
            if _is_dev:
                print(f"[DEBUG] Moving to next scene: index={next_scene_index}, id={next_scene_id}, title={next_scene.get('title')}")
            
            # Update orchestrator state
            orchestrator.state.current_scene_index = next_scene_index
            orchestrator.state.turn_count = 0
            orchestrator.state.scene_completed = False
            orchestrator.state.current_scene_id = next_scene_id
            
            # Mark current scene as complete
            self.mark_scene_complete(user_progress, current_scene_id)
            
            # Initialize new scene
            self.initialize_new_scene(user_progress, next_scene_id, orchestrator)
            
            # Generate scene intro message if function provided
            scene_intro_message = None
            if generate_scene_intro_fn:
                scene_intro_message = generate_scene_intro_fn(next_scene)
                
                # Save scene intro if it doesn't exist
                existing_intro = self.repository.check_scene_intro_exists(
                    user_progress.id,
                    next_scene_id
                )
                
                if not existing_intro:
                    last_msg = self.repository.get_last_conversation_log(user_progress.id)
                    next_order = (last_msg.message_order + 1) if last_msg else 1
                    self.repository.create_conversation_log(
                        user_progress_id=user_progress.id,
                        scene_id=next_scene_id,
                        message_type="system",
                        sender_name="System",
                        message_content=scene_intro_message,
                        message_order=next_order
                    )
            
            return {
                'next_scene_id': next_scene_id,
                'next_scene': next_scene,
                'scene_intro_message': scene_intro_message
            }
        else:
            # No more scenes - simulation complete
            user_progress.simulation_status = "completed"
            user_progress.completed_at = datetime.utcnow()
            return {
                'next_scene_id': None,
                'next_scene': None,
                'scene_intro_message': None,
                'simulation_complete': True
            }

