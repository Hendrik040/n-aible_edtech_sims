"""Handle timeout detection and scene progression."""

from typing import Dict, Any, Optional
import json

from modules.simulation.core import ChatOrchestrator, OrchestratorManager, SceneProgressionHandler
from common.db.models import UserProgress


async def handle_timeout(
    orchestrator: ChatOrchestrator,
    user_progress: UserProgress,
    current_scene: Dict[str, Any],
    current_scene_id: int,
    full_response: str,
    persona_name: str,
    persona_id: Optional[int],
    scene_progression_handler: SceneProgressionHandler,
    orchestrator_manager: OrchestratorManager,
    generate_scene_intro_fn: Optional[callable] = None
) -> Optional[str]:
    """
    Handle timeout detection and scene progression.
    
    Args:
        orchestrator: ChatOrchestrator instance
        user_progress: UserProgress instance
        current_scene: Current scene data
        current_scene_id: Current scene ID
        full_response: Full response text so far
        persona_name: Persona name for response
        persona_id: Persona ID for response
        scene_progression_handler: SceneProgressionHandler instance
        orchestrator_manager: OrchestratorManager instance
        generate_scene_intro_fn: Optional function to generate scene intro
        
    Returns:
        SSE event string if timeout handled (scene progressed), None otherwise
    """
    timeout_turns = current_scene.get('timeout_turns') or current_scene.get('max_turns', 15)
    
    if orchestrator.state.turn_count >= timeout_turns:
        # Handle timeout - progress to next scene
        progression_result = scene_progression_handler.progress_to_next_scene(
            orchestrator=orchestrator,
            user_progress=user_progress,
            current_scene_id=current_scene_id,
            generate_scene_intro_fn=generate_scene_intro_fn
        )
        
        # Save orchestrator state
        orchestrator_manager.save_orchestrator_state(orchestrator, user_progress)
        # Note: Commit handled by service layer
        
        if progression_result.get('simulation_complete'):
            # Simulation complete
            return json.dumps({'done': True, 'persona_name': persona_name, 'persona_id': str(persona_id) if persona_id else None, 'scene_completed': True, 'next_scene_id': None, 'turn_count': orchestrator.state.turn_count, 'simulation_complete': True, 'full_content': full_response})
        
        # Scene progressed
        next_scene_id = progression_result['next_scene_id']
        return json.dumps({'done': True, 'persona_name': persona_name, 'persona_id': str(persona_id) if persona_id else None, 'scene_completed': True, 'next_scene_id': next_scene_id, 'turn_count': 0, 'full_content': full_response})
    
    return None
