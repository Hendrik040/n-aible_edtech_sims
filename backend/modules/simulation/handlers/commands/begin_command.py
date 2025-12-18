"""Handle the 'begin' command for starting simulations."""

from typing import Dict, Any, AsyncGenerator
from sqlalchemy.orm import Session
import json
import asyncio

from modules.simulation.repository import SimulationRepository
from modules.simulation.core import ChatOrchestrator, OrchestratorManager
from common.db.models import UserProgress


async def handle_begin_command(
    db: Session,
    repository: SimulationRepository,
    orchestrator: ChatOrchestrator,
    user_progress: UserProgress,
    message: str,
    current_scene: Dict[str, Any],
    generate_scene_intro_fn: callable
) -> AsyncGenerator[str, None]:
    """
    Handle the "begin" command.
    
    Args:
        db: Database session
        repository: SimulationRepository instance
        orchestrator: ChatOrchestrator instance
        user_progress: UserProgress instance
        message: The "begin" message
        current_scene: Current scene data
        generate_scene_intro_fn: Function to generate scene intro message
        
    Yields:
        SSE event strings
    """
    # Check if simulation is already started
    if orchestrator.state.simulation_started:
        already_started_msg = "The simulation is already in progress. You can continue interacting with the personas."
        for char in already_started_msg:
            yield f"data: {json.dumps({'content': char, 'done': False})}\n\n"
            await asyncio.sleep(0.03)
        yield f"data: {json.dumps({'done': True, 'persona_name': 'ChatOrchestrator', 'persona_id': None, 'scene_completed': False, 'next_scene_id': None, 'turn_count': orchestrator.state.turn_count, 'full_content': already_started_msg})}\n\n"
        return
    
    # Don't save begin command - it's a command word, not a user response
    begin_order = repository.get_next_message_order(user_progress.id)
    
    orchestrator.state.simulation_started = True
    orchestrator.state.user_ready = True
    user_progress.simulation_status = "in_progress"
    
    # Save orchestrator state
    orchestrator_manager = OrchestratorManager(db, repository)
    orchestrator_manager.save_orchestrator_state(orchestrator, user_progress)
    # Note: Commit handled by service layer
    
    # Generate scene intro message
    scene_intro_message = generate_scene_intro_fn(current_scene)
    
    # Stream welcome message
    welcome_msg = "🎬 **Simulation Started!**\n\nThe simulation has begun. You can now interact with the personas in this scene."
    full_response = ""
    for char in welcome_msg:
        full_response += char
        yield f"data: {json.dumps({'content': char, 'done': False})}\n\n"
        await asyncio.sleep(0.03)
    
    # Save welcome message
    repository.create_conversation_log(
        user_progress_id=user_progress.id,
        scene_id=user_progress.current_scene_id,
        message_type="orchestrator",
        sender_name="ChatOrchestrator",
        message_content=welcome_msg,
        message_order=begin_order + 1
    )
    
    # Save scene intro message
    repository.create_conversation_log(
        user_progress_id=user_progress.id,
        scene_id=user_progress.current_scene_id,
        message_type="system",
        sender_name="System",
        message_content=scene_intro_message,
        message_order=begin_order + 2
    )
    # Note: Commit handled by service layer
    
    # Send metadata
    yield f"data: {json.dumps({'done': True, 'persona_name': 'ChatOrchestrator', 'persona_id': None, 'scene_completed': False, 'next_scene_id': None, 'turn_count': 0, 'scene_intro_message': scene_intro_message, 'full_content': full_response})}\n\n"
