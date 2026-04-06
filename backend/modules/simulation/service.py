"""
Simulation Service.

Main orchestrator for simulation operations.
Delegates to specialized services for lifecycle, grading, and progress operations.
"""

from typing import Dict, Any, Optional, AsyncGenerator
import json
import logging
import secrets

from sqlalchemy.orm import Session

from modules.simulation.repository import SimulationRepository
from modules.simulation.core import OrchestratorManager, SceneProgressionHandler
from modules.simulation.handlers import ChatHandler
from modules.simulation.schemas.dto import (
    SimulationStartResponse, SimulationChatResponse,
    UserProgressResponse, SimulationSceneResponse
)
from modules.simulation.services import GradingService, ProgressService, LifecycleService
from common.exceptions import NotFoundError, ForbiddenError
from common.config import get_settings
from common.utils.concurrency import acquire_stream_slot, release_stream_slot

logger = logging.getLogger(__name__)

settings = get_settings()
_is_dev = settings.environment != "production"


class SimulationService:
    """Main service orchestrator for simulation operations."""
    
    def __init__(self, db: Session):
        self.db = db
        self.repository = SimulationRepository(db)
        self.chat_handler = ChatHandler(db, self.repository)
        self.scene_handler = SceneProgressionHandler(db, self.repository)
        self.orchestrator_manager = OrchestratorManager(db, self.repository)
        
        # Specialized services
        self.lifecycle_service = LifecycleService(db, self.repository)
        self.grading_service = GradingService(db, self.repository)
        self.progress_service = ProgressService(db, self.repository)
    
    def generate_scene_intro_message(
        self, 
        scene: dict, 
        db_scene = None
    ) -> str:
        """Generate the scene introduction message that appears at the start of each scene."""
        return self.lifecycle_service.generate_scene_intro_message(scene, db_scene)
    
    def validate_goal_with_function_calling(
        self,
        conversation_history: str,
        scene_goal: str,
        scene_description: str,
        current_attempts: int,
        max_attempts: int,
        user_progress_id: int = None,
        current_scene_id: int = None,
        perform_db_progression: bool = False
    ) -> dict:
        """
        Use OpenAI function calling to validate if user has achieved the scene goal.
        
        TODO: This method needs to be fully extracted from legacy code.
        Currently returns a placeholder structure.
        """
        # TODO: Extract full implementation from legacy simulation.py
        # This requires OpenAI client setup and function calling logic
        return {
            "goal_achieved": False,
            "confidence_score": 0.0,
            "reasoning": "Not implemented",
            "next_action": "continue",
            "hint_message": None
        }
    
    async def start_simulation(
        self,
        user_id: int,
        simulation_id: int
    ) -> SimulationStartResponse:
        """Start a new simulation or resume existing one."""
        return await self.lifecycle_service.start_simulation(user_id, simulation_id)
    
    async def process_chat_message(
        self,
        user_id: int,
        user_progress_id: int,
        message: str,
        scene_id: Optional[int] = None
    ) -> SimulationChatResponse:
        """
        Process a chat message (non-streaming).
        
        Used for SUBMIT_FOR_GRADING and other special messages.
        """
        user_progress = self.repository.get_user_progress_by_id(user_progress_id)
        if not user_progress:
            raise NotFoundError("User progress not found")
        
        if user_progress.user_id != user_id:
            raise ForbiddenError("Access denied")
        
        if not user_progress.orchestrator_data:
            raise NotFoundError("Simulation not properly initialized")
        
        # Check if this is SUBMIT_FOR_GRADING
        if message.strip() == "SUBMIT_FOR_GRADING":
            # Load orchestrator
            orchestrator = self.orchestrator_manager.load_orchestrator(user_progress, user_id)
            
            # Initialize LangChain session if needed
            await self.orchestrator_manager.initialize_langchain_session(orchestrator, user_progress.id)
            
            # Load saved state
            self.orchestrator_manager.load_orchestrator_state(orchestrator, user_progress)
            
            scene_id_to_use = scene_id if scene_id is not None else user_progress.current_scene_id
            
            # Progress to next scene using scene handler
            progression_result = self.scene_handler.progress_to_next_scene(
                orchestrator=orchestrator,
                user_progress=user_progress,
                current_scene_id=scene_id_to_use,
                generate_scene_intro_fn=lambda scene: self.lifecycle_service.generate_scene_intro_message(scene, self.repository.get_scene_by_id(scene.get('id')))
            )
            
            if progression_result.get('simulation_complete'):
                # Clean up sandbox if one was created
                if user_progress.sandbox_id:
                    try:
                        from common.services.sandbox_service import sandbox_service
                        deleted = await sandbox_service.delete_sandbox(user_progress.sandbox_id)
                        if deleted:
                            logger.info(f"[SERVICE] Cleaned up sandbox {user_progress.sandbox_id}")
                            user_progress.sandbox_id = None
                        else:
                            logger.error(f"[SERVICE] Sandbox {user_progress.sandbox_id} teardown returned False — ID retained for retry")
                    except Exception as e:
                        logger.error(f"[SERVICE] Sandbox cleanup failed: {e}")

                # Simulation complete
                self.db.commit()
                return SimulationChatResponse(
                    message="🎉 **Congratulations! You have completed the entire simulation.**",
                    scene_id=scene_id_to_use,
                    scene_completed=True,
                    next_scene_id=None,
                    persona_name="System",
                    persona_id=None,
                    turn_count=orchestrator.state.turn_count,
                    simulation_complete=True
                )
            
            # Save orchestrator state
            self.orchestrator_manager.save_orchestrator_state(orchestrator, user_progress)
            self.db.commit()

            # Upload data files for the next scene into sandbox (if applicable)
            next_scene = progression_result['next_scene']
            next_scene_id = progression_result['next_scene_id']
            if user_progress.sandbox_id and next_scene_id:
                db_next_scene = self.repository.get_scene_by_id(next_scene_id)
                if db_next_scene and getattr(db_next_scene, "scene_type", "conversation") == "code_challenge":
                    scene_data_files = getattr(db_next_scene, "data_files", None)
                    if scene_data_files:
                        try:
                            from common.services.sandbox_service import sandbox_service
                            count = await sandbox_service.upload_scene_data_files(
                                user_progress.sandbox_id, scene_data_files
                            )
                            logger.info(f"[SERVICE] Uploaded {count} data files for scene {next_scene_id}")
                        except Exception as e:
                            logger.error(f"[SERVICE] Data file upload failed for scene {next_scene_id}: {e}")

            # Build response
            scene_intro_message = progression_result.get('scene_intro_message')
            
            # Load personas for the next scene
            next_scene_personas = self.repository.get_personas_for_scene(next_scene_id)
            personas_data = [
                {
                    'id': p.id,
                    'simulation_id': p.simulation_id,
                    'name': p.name,
                    'role': p.role,
                    'background': getattr(p, 'background', None),
                    'correlation': getattr(p, 'correlation', None),
                    'primary_goals': (
                        [p.primary_goals] if isinstance(getattr(p, 'primary_goals', None), str) and getattr(p, 'primary_goals', None) else
                        getattr(p, 'primary_goals', []) if isinstance(getattr(p, 'primary_goals', None), list) else []
                    ),
                    'personality_traits': getattr(p, 'personality_traits', None) or {},
                    'image_url': getattr(p, 'image_url', None)
                }
                for p in next_scene_personas
            ]
            
            ai_response = f"🎉 **Scene Submitted!** Moving to next scene:\n\n**{next_scene.get('title', 'Next Scene')}**\n\n**Objective:** {next_scene.get('objectives', ['Continue the simulation'])[0]}"
            
            # Get DB scene for code challenge fields
            db_next_scene = self.repository.get_scene_by_id(next_scene_id) if next_scene_id else None
            next_scene_obj = {
                'id': next_scene.get('id'),
                'title': next_scene.get('title'),
                'description': next_scene.get('description'),
                'objectives': next_scene.get('objectives', []),
                'image_url': next_scene.get('image_url'),
                'scene_order': next_scene.get('scene_order') or (orchestrator.state.current_scene_index + 1),
                'user_goal': next_scene.get('objectives', ['Continue the simulation'])[0] if next_scene.get('objectives') else 'Continue the simulation',
                'timeout_turns': next_scene.get('timeout_turns') or next_scene.get('max_turns', 15),
                'personas': personas_data,
                'personas_involved': next_scene.get('personas_involved', []),
                'scene_type': getattr(db_next_scene, 'scene_type', None) or 'conversation' if db_next_scene else 'conversation',
                'starter_code': getattr(db_next_scene, 'starter_code', None) if db_next_scene else None,
                'data_files': getattr(db_next_scene, 'data_files', None) if db_next_scene else None,
                'reference_files': getattr(db_next_scene, 'reference_files', None) if db_next_scene else None,
            }
            
            return SimulationChatResponse(
                message=ai_response,
                scene_id=next_scene_id,
                scene_completed=True,
                next_scene_id=next_scene_id,
                next_scene=next_scene_obj,
                persona_name="System",
                persona_id=None,
                turn_count=0,
                scene_intro_message=scene_intro_message
            )
        
        # For other messages, return a basic response
        return SimulationChatResponse(
            message="This endpoint is for SUBMIT_FOR_GRADING. Use /linear-chat-stream for regular chat.",
            scene_id=scene_id,
            scene_completed=False,
            persona_name="System",
            persona_id=None,
            turn_count=0
        )
    
    async def stream_chat_message(
        self,
        user_id: int,
        user_progress_id: int,
        message: str,
        scene_id: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream a chat message (streaming).
        
        Used for real-time chat interactions with persona agents.
        Handles @mentions, @all, scene transitions, and timeouts.
        Applies global back-pressure when the process is at capacity.
        """
        acquired = await acquire_stream_slot()
        if not acquired:
            # Immediate back-pressure: inform client that capacity is reached.
            logger.warning(f"[CAPACITY] Stream slot unavailable for user {user_id}, user_progress_id {user_progress_id} - system at capacity")
            error_payload = {
                "error": "Simulation system is at capacity. Please wait a moment and try again.",
                "code": "SIMULATION_STREAMS_AT_CAPACITY",
                "message": "Too many users are using the simulation right now. Please wait a few seconds and try again."
            }
            yield f"data: {json.dumps(error_payload)}\n\n"
            return

        try:
            last_chunk_was_done = False
            async for chunk in self.chat_handler.handle_stream_message(
                user_id=user_id,
                user_progress_id=user_progress_id,
                message=message,
                orchestrator_manager=self.orchestrator_manager,
                scene_progression_handler=self.scene_handler,
                generate_scene_intro_fn=self.lifecycle_service.generate_scene_intro_message,
            ):
                yield chunk
                # Check if this is the final 'done' chunk and commit
                try:
                    if chunk.startswith("data: "):
                        data_str = chunk.replace("data: ", "").strip()
                        if data_str:
                            data = json.loads(data_str)
                            if data.get("done", False):
                                last_chunk_was_done = True
                except (json.JSONDecodeError, KeyError, json.JSONDecodeError):
                    # Ignore malformed payloads in the commit detection logic.
                    pass

            # Commit after streaming completes successfully
            # NOTE: turn_count and persona responses may have already been committed
            # by chat_handler or PersonaCallbackHandler, but we commit here to ensure 
            # any remaining changes (like orchestrator state updates) are persisted
            if last_chunk_was_done:
                # Refresh to see any changes from other commits (e.g., PersonaCallbackHandler)
                # This ensures persona responses and turn_count changes are visible
                self.db.expire_all()
                self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        finally:
            release_stream_slot()
    
    def get_user_progress(
        self,
        user_progress_id: int,
        user_id: int
    ) -> UserProgressResponse:
        """Get detailed user progress for a simulation."""
        return self.progress_service.get_user_progress(user_progress_id, user_id)
    
    def get_scene_by_id(self, scene_id: int, user_id: int) -> SimulationSceneResponse:
        """Get scene data by ID with ownership validation."""
        return self.progress_service.get_scene_by_id(scene_id, user_id)
    
    async def get_simulation_grading(
        self,
        user_progress_id: int,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Get simulation grading.
        
        Returns AI-generated grades and feedback for the simulation.
        """
        return await self.grading_service.get_simulation_grading(user_progress_id, user_id)
    
    def save_message(
        self,
        user_id: int,
        user_progress_id: int,
        scene_id: int,
        sender_name: str,
        message_content: str,
        message_type: str,
        session_id: str = None
    ) -> Dict[str, Any]:
        """Save a system message to conversation history."""
        user_progress = self.repository.get_user_progress_by_id(user_progress_id)
        if not user_progress:
            raise NotFoundError("User progress not found")

        if user_progress.user_id != user_id:
            raise ForbiddenError("Access denied: You can only save messages to your own simulation")

        scene = self.repository.get_scene_by_id(scene_id)
        if not scene:
            raise NotFoundError("Scene not found")
        if scene.simulation_id != user_progress.simulation_id:
            raise ForbiddenError("scene_id does not belong to this simulation")

        next_message_order = self.repository.get_next_message_order(user_progress_id)

        # Resolve session_id: caller-provided > active session from orchestrator_data > synthetic fallback
        effective_session_id = (
            session_id
            or (user_progress.orchestrator_data or {}).get('state', {}).get('session_id')
            or f"system_{user_progress_id}_{scene_id}_{secrets.token_urlsafe(8)}"
        )

        log = self.repository.create_conversation_log(
            user_progress_id=user_progress_id,
            scene_id=scene_id,
            message_type=message_type,
            sender_name=sender_name,
            message_content=message_content,
            message_order=next_message_order,
            session_id=effective_session_id
        )
        self.repository.db.commit()
        return {"id": log.id, "message_order": log.message_order, "status": "saved"}
