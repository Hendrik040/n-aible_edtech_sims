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
        
        # Note: Instance progress update is handled in progress_to_next_scene to avoid transaction issues
    
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
            
            # Note: Instance progress updates are handled asynchronously via refresh endpoints
            # to avoid transaction conflicts during scene progression
            
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
                    next_order = self.repository.get_next_message_order(user_progress.id)
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
            
            # Update instance progress to 100%
            self._update_instance_progress(user_progress, is_complete=True)
            
            return {
                'next_scene_id': None,
                'next_scene': None,
                'scene_intro_message': None,
                'simulation_complete': True
            }
    
    def _update_instance_progress(self, user_progress: UserProgress, is_complete: bool = False):
        """Update StudentSimulationInstance completion_percentage and total_time_spent"""
        try:
            from common.db.models import StudentSimulationInstance, SimulationScene, SceneProgress
            
            # Find the instance linked to this user_progress
            instance = self.db.query(StudentSimulationInstance).filter(
                StudentSimulationInstance.user_progress_id == user_progress.id
            ).first()
            
            if not instance:
                # No instance found - this is normal for test simulations, skip update
                return
            
            # Calculate completion percentage
            if is_complete or user_progress.simulation_status in ["completed", "graded"]:
                instance.completion_percentage = 100.0
                # Update instance status to completed
                if instance.status != "completed":
                    instance.status = "completed"
                    instance.completed_at = datetime.utcnow()
            else:
                # Calculate based on completed scenes
                try:
                    total_scenes = self.db.query(SimulationScene).filter(
                        SimulationScene.simulation_id == user_progress.simulation_id,
                        SimulationScene.deleted_at.is_(None)
                    ).count()
                    
                    completed_scenes = self.db.query(SceneProgress).filter(
                        SceneProgress.user_progress_id == user_progress.id,
                        SceneProgress.status == "completed"
                    ).count()
                    
                    if total_scenes > 0:
                        instance.completion_percentage = (completed_scenes / total_scenes) * 100.0
                    else:
                        instance.completion_percentage = 0.0
                except Exception as calc_error:
                    if _is_dev:
                        print(f"[DEBUG] Error calculating completion percentage: {calc_error}")
                    # Don't update completion_percentage if calculation fails
                    pass
            
            # Calculate total_time_spent in seconds
            try:
                if instance.started_at:
                    end_time = instance.completed_at or datetime.utcnow()
                    time_delta = end_time - instance.started_at
                    instance.total_time_spent = int(time_delta.total_seconds())
                elif user_progress.created_at:
                    # Fallback to user_progress created_at if instance started_at is None
                    end_time = user_progress.completed_at or datetime.utcnow()
                    time_delta = end_time - user_progress.created_at
                    instance.total_time_spent = int(time_delta.total_seconds())
            except Exception as time_error:
                if _is_dev:
                    print(f"[DEBUG] Error calculating total_time_spent: {time_error}")
                # Don't update total_time_spent if calculation fails
                pass
            
            # Don't flush here - let the caller handle transaction commits
            # This avoids transaction conflicts
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Error updating instance progress: {e}", exc_info=True)
            # Don't fail the scene progression if instance update fails
            pass

