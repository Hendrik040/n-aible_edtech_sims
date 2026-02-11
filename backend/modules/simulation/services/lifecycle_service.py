"""
Lifecycle Service.

Handles simulation initialization and lifecycle operations.
"""

import logging
import re
from sqlalchemy.orm import Session
from datetime import datetime

from modules.simulation.repository import SimulationRepository
from modules.simulation.schemas.dto import (
    SimulationStartResponse, SimulationPersonaResponse
)
from common.exceptions import NotFoundError
from common.db.models import User

logger = logging.getLogger(__name__)


class LifecycleService:
    """Service for simulation lifecycle operations."""
    
    def __init__(self, db: Session, repository: SimulationRepository):
        self.db = db
        self.repository = repository
    
    def generate_scene_intro_message(
        self, 
        scene: dict, 
        db_scene = None
    ) -> str:
        """Generate the scene introduction message that appears at the start of each scene."""
        if db_scene:
            title = db_scene.title
            description = db_scene.description
            user_goal = db_scene.user_goal
            timeout_turns = db_scene.timeout_turns if db_scene.timeout_turns is not None else 15
            scene_order = db_scene.scene_order
        else:
            title = scene.get('title', 'Scene')
            description = scene.get('description', '')
            user_goal = scene.get('objectives', ['Complete the scene'])[0] if scene.get('objectives') else scene.get('user_goal', 'Complete the scene')
            timeout_turns = scene.get('timeout_turns') or scene.get('max_turns', 15)
            scene_order = scene.get('scene_order', 1)
        
        # Get personas involved with their roles
        personas_involved = scene.get('personas_involved', [])
        
        # Build persona list with roles
        persona_text = ""
        if personas_involved and db_scene:
            scene_personas = self.repository.get_personas_for_scene(db_scene.id)
            
            if scene_personas:
                persona_text = "\n**Active Participants:**\n"
                for persona in scene_personas:
                    # Sanitize persona ID: remove parentheses, dots, and other special chars
                    persona_id = re.sub(r'[^a-z0-9_]', '', persona.name.lower().replace(' ', '_'))
                    persona_text += f"• @{persona_id}: {persona.name} ({persona.role})\n"
        elif personas_involved:
            persona_text = "\n**Active Participants:**\n"
            for persona_name in personas_involved:
                # Sanitize persona ID: remove parentheses, dots, and other special chars
                persona_id = re.sub(r'[^a-z0-9_]', '', persona_name.lower().replace(' ', '_'))
                persona_text += f"• @{persona_id}: {persona_name}\n"
        
        intro = f"""**Scene {scene_order} — {title}**

*{description}*

**Objective:** {user_goal}
{persona_text}
*You have {timeout_turns} turns to achieve the objective.*"""
        
        return intro
    
    async def start_simulation(
        self,
        user_id: int,
        simulation_id: int
    ) -> SimulationStartResponse:
        """
        Start a new simulation or resume existing one.
        
        Creates a new UserProgress, initializes ChatOrchestrator data,
        and sets up the first scene.
        """
        # Delete all previous progress and related logs for this user and simulation
        self.repository.delete_all_user_progress_for_simulation(user_id, simulation_id)
        self.db.commit()
        # Expunge any deleted objects from session to prevent ObjectDeletedError
        self.db.expunge_all()
        
        # Verify simulation exists
        simulation = self.repository.get_simulation_by_id(simulation_id)
        if not simulation:
            raise NotFoundError("Simulation not found")
        
        # Get first scene in order
        all_scenes = self.repository.get_scenes_by_simulation_id(simulation_id, eager_load_personas=True)
        if not all_scenes:
            raise NotFoundError("Simulation has no scenes")
        
        first_scene = all_scenes[0]
        
        # Get all personas for the simulation
        all_personas = self.repository.get_personas_by_simulation_id(simulation_id)
        
        # Build persona map from scene-persona associations using bulk loading to avoid N+1 queries
        scene_ids = [scene.id for scene in all_scenes]
        personas_by_scene = self.repository.get_personas_for_scenes(scene_ids) if scene_ids else {}
        scene_personas_map = {
            scene.id: [p.name for p in personas_by_scene.get(scene.id, [])]
            for scene in all_scenes
        }
        
        # Get user role once to determine if this is a professor test simulation
        # Store it in orchestrator_data to avoid repeated queries
        user = self.db.query(User).filter(User.id == user_id).first()
        is_professor_test = user and user.role in ['professor', 'admin'] if user else False
        
        # Build simulation data for ChatOrchestrator
        simulation_data = {
            "id": simulation.id,
            "title": simulation.title,
            "description": simulation.description,
            "challenge": simulation.challenge,
            "student_role": simulation.student_role,
            "is_professor_test": is_professor_test,  # Store flag to avoid repeated queries
            "scenes": [
                {
                    "id": scene.id,
                    "title": scene.title,
                    "description": scene.description,
                    "user_goal": scene.user_goal,
                    "objectives": [scene.user_goal] if scene.user_goal else ["Complete the scene interaction"],
                    "image_url": scene.image_url,
                    # Sanitize agent IDs: remove parentheses, dots, and other special chars
                    "agent_ids": [re.sub(r'[^a-z0-9_]', '', p.name.lower().replace(" ", "_")) for p in all_personas],
                    "personas_involved": scene_personas_map.get(scene.id, []),
                    "timeout_turns": scene.timeout_turns if scene.timeout_turns is not None else 15,
                    "max_turns": scene.timeout_turns if scene.timeout_turns is not None else 15,
                    "success_criteria": f"User achieves: {scene.user_goal or 'scene completion'}",
                    "scene_order": scene.scene_order
                }
                for scene in all_scenes
            ],
            "personas": [
                {
                    # Sanitize persona ID: remove parentheses, dots, and other special chars
                    "id": re.sub(r'[^a-z0-9_]', '', persona.name.lower().replace(" ", "_")),
                    "db_id": persona.id,
                    "identity": {
                        "name": persona.name,
                        "role": persona.role,
                        "bio": persona.background or "Professional team member"
                    },
                    "personality": {
                        "goals": persona.primary_goals or ["Support team objectives"],
                        "traits": persona.personality_traits or "Professional and collaborative"
                    },
                    "system_prompt": persona.system_prompt,
                    "image_url": persona.image_url
                }
                for persona in all_personas
            ]
        }
        
        # Create new UserProgress
        user_progress = self.repository.create_user_progress(
            user_id=user_id,
            simulation_id=simulation_id,
            current_scene_id=first_scene.id,
            orchestrator_data=simulation_data,
            simulation_status="waiting_for_begin"
        )
        user_progress.session_count = 1
        user_progress.scenes_completed = []
        user_progress.started_at = datetime.utcnow()
        user_progress.last_activity = datetime.utcnow()
        self.db.flush()
        # Refresh to ensure object is fully loaded and not stale
        self.db.refresh(user_progress)
        
        # Create scene progress for first scene
        self.repository.create_scene_progress(
            user_progress_id=user_progress.id,
            scene_id=first_scene.id,
            status="in_progress"
        )
        
        # Save initial welcome message to conversation history
        welcome_text = f"""🎯 **{simulation.title}**

{simulation.description or ''}

**Your Role:** {simulation.student_role or 'Team Member'}

**Current Scene:** {first_scene.title}

**Instructions:**
• Type **"begin"** to start the simulation
• Type **"help"** for available commands
• Use natural conversation to interact with personas"""
        
        # Generate session_id for initial system message
        # This is intentional - initial messages are created before user starts simulation
        # When user starts, orchestrator will create proper session_id via session_manager
        # This ensures initial messages have proper isolation
        import secrets
        initial_session_id = f"init_{user_progress.id}_{first_scene.id}_{secrets.token_urlsafe(16)}"
        
        self.repository.create_conversation_log(
            user_progress_id=user_progress.id,
            scene_id=first_scene.id,
            message_type="system",
            sender_name="System",
            message_content=welcome_text,
            message_order=1,
            session_id=initial_session_id
        )
        self.db.commit()

        # Create Daytona sandbox if simulation has code_challenge scenes
        has_code_scenes = any(
            getattr(scene, "scene_type", "conversation") == "code_challenge"
            for scene in all_scenes
        )
        if has_code_scenes:
            try:
                from common.services.sandbox_service import sandbox_service
                sandbox_id = await sandbox_service.create_sandbox(
                    session_label=f"user_{user_id}_sim_{simulation_id}"
                )
                self.db.refresh(user_progress)
                user_progress.sandbox_id = sandbox_id
                self.db.commit()
                logger.info(f"[LIFECYCLE] Sandbox {sandbox_id} created for user {user_id}")
                # Upload first scene's data files into the sandbox
                if sandbox_id and getattr(first_scene, "scene_type", "conversation") == "code_challenge":
                    scene_data_files = getattr(first_scene, "data_files", None)
                    if scene_data_files:
                        count = await sandbox_service.upload_scene_data_files(sandbox_id, scene_data_files)
                        logger.info(f"[LIFECYCLE] Uploaded {count} data files to sandbox for scene {first_scene.id}")
            except Exception as e:
                # Simulation starts anyway — frontend shows degraded "offline" code editor
                logger.error(f"[LIFECYCLE] Sandbox creation failed for user {user_id}: {e}")

        # Capture user_progress attributes before potential detachment (NullPool closes connections after commit)
        # Refresh the object to ensure it's still attached to the session
        self.db.refresh(user_progress)
        user_progress_id = user_progress.id
        simulation_status = user_progress.simulation_status
        captured_sandbox_id = user_progress.sandbox_id

        # Prepare response data
        learning_objectives = simulation.learning_objectives
        if isinstance(learning_objectives, str):
            learning_objectives = [learning_objectives]
        elif learning_objectives is None:
            learning_objectives = []
        
        case_study_url = getattr(simulation, 'case_study_url', None)
        
        # Build simulation response
        simulation_response = {
            "id": simulation.id,
            "title": simulation.title,
            "description": simulation.description,
            "challenge": simulation.challenge,
            "industry": getattr(simulation, 'industry', None),
            "learning_objectives": learning_objectives,
            "student_role": simulation.student_role,
            "total_scenes": len(all_scenes),
            "case_study_url": case_study_url
        }
        
        # Get personas involved in current scene
        involved_personas = self.repository.get_personas_for_scene(first_scene.id)
        
        def is_main_character(persona_name, student_role):
            if not student_role:
                return False
            student_name = student_role.split('(')[0].strip().lower()
            persona_name_clean = persona_name.strip().lower()
            return persona_name_clean == student_name
        
        personas_data = [
            SimulationPersonaResponse(
                id=persona.id,
                simulation_id=persona.simulation_id,
                name=persona.name,
                role=persona.role,
                background=persona.background,
                correlation=persona.correlation,
                primary_goals=(
                    [persona.primary_goals] if isinstance(persona.primary_goals, str) and persona.primary_goals else
                    persona.primary_goals if isinstance(persona.primary_goals, list) else []
                ),
                personality_traits=persona.personality_traits or {},
                image_url=persona.image_url,
                created_at=persona.created_at,
                updated_at=persona.updated_at
            ) for persona in involved_personas
            if not is_main_character(persona.name, simulation.student_role)
        ]
        
        # Build scene response
        scene_response = {
            "id": first_scene.id,
            "simulation_id": first_scene.simulation_id,
            "title": first_scene.title,
            "description": first_scene.description,
            "user_goal": first_scene.user_goal,
            "scene_order": first_scene.scene_order,
            "estimated_duration": getattr(first_scene, 'estimated_duration', None),
            "image_url": first_scene.image_url,
            "image_prompt": first_scene.image_prompt,
            "timeout_turns": first_scene.timeout_turns,
            "success_metric": first_scene.success_metric,
            "personas_involved": scene_personas_map.get(first_scene.id, []),
            "personas": [p.model_dump() for p in personas_data],
            "scene_type": getattr(first_scene, 'scene_type', None) or "conversation",
            "starter_code": getattr(first_scene, 'starter_code', None),
            "data_files": getattr(first_scene, 'data_files', None),
            "reference_files": getattr(first_scene, 'reference_files', None),
        }

        # Get conversation history - use captured ID to avoid ObjectDeletedError with NullPool
        conversation_logs = self.repository.get_conversation_logs(user_progress_id)
        
        # Format conversation logs for frontend
        messages_history = []
        # Build persona map for conversation logs
        persona_ids = [log.persona_id for log in conversation_logs if log.persona_id]
        persona_map = {}
        if persona_ids:
            personas = self.repository.get_personas_by_ids(persona_ids)
            persona_map = {p.id: p for p in personas}
        
        for log in conversation_logs:
            persona_name = None
            persona_role = None
            if log.persona_id and log.persona_id in persona_map:
                persona = persona_map[log.persona_id]
                persona_name = persona.name
                persona_role = persona.role
            
            messages_history.append({
                "id": log.id,
                "message_order": log.message_order,
                "message_type": log.message_type,
                "sender_name": log.sender_name,
                "message_content": log.message_content,
                "persona_name": persona_name,
                "persona_role": persona_role,
                "persona_id": log.persona_id,
                "scene_id": log.scene_id,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None
            })
        
        # Build all scenes response - bulk load personas to avoid N+1 queries
        scene_ids = [scene.id for scene in all_scenes]
        personas_by_scene = self.repository.get_personas_for_scenes(scene_ids) if scene_ids else {}
        
        all_scenes_response = []
        for scene in all_scenes:
            scene_personas_list = personas_by_scene.get(scene.id, [])
            scene_personas_data = [
                SimulationPersonaResponse(
                    id=p.id,
                    simulation_id=p.simulation_id,
                    name=p.name,
                    role=p.role,
                    background=p.background,
                    correlation=p.correlation,
                    primary_goals=(
                        [p.primary_goals] if isinstance(p.primary_goals, str) and p.primary_goals else
                        p.primary_goals if isinstance(p.primary_goals, list) else []
                    ),
                    personality_traits=p.personality_traits or {},
                    image_url=p.image_url,
                    created_at=p.created_at,
                    updated_at=p.updated_at
                ) for p in scene_personas_list
                if not is_main_character(p.name, simulation.student_role)
            ]
            all_scenes_response.append({
                "id": scene.id,
                "simulation_id": scene.simulation_id,
                "title": scene.title,
                "description": scene.description,
                "user_goal": scene.user_goal,
                "scene_order": scene.scene_order,
                "estimated_duration": getattr(scene, 'estimated_duration', None),
                "image_url": scene.image_url,
                "image_prompt": scene.image_prompt,
                "timeout_turns": scene.timeout_turns,
                "success_metric": scene.success_metric,
                "personas_involved": scene_personas_map.get(scene.id, []),
                "personas": [p.model_dump() for p in scene_personas_data],
                "scene_type": getattr(scene, 'scene_type', None) or "conversation",
                "starter_code": getattr(scene, 'starter_code', None),
                "data_files": getattr(scene, 'data_files', None),
                "reference_files": getattr(scene, 'reference_files', None),
            })

        return SimulationStartResponse(
            user_progress_id=user_progress_id,  # Use captured ID to avoid ObjectDeletedError
            simulation=simulation_response,
            current_scene=scene_response,
            simulation_status=simulation_status,  # Use captured value to avoid ObjectDeletedError
            conversation_history=messages_history,
            is_resuming=False,
            all_scenes=all_scenes_response,
            turn_count=0,  # New simulation starts at 0 turns
            completed_scene_ids=[],  # No scenes completed yet
            sandbox_id=captured_sandbox_id,
        )
    
    async def resume_simulation(
        self,
        user_id: int,
        user_progress_id: int,
        simulation_id: int
    ) -> SimulationStartResponse:
        """
        Resume an existing simulation from saved progress.
        
        Loads existing UserProgress and returns it in the same format as start_simulation.
        """
        # Get existing user progress
        user_progress = self.repository.get_user_progress_by_id(user_progress_id)
        if not user_progress:
            raise NotFoundError("User progress not found")
        
        if user_progress.user_id != user_id:
            raise NotFoundError("User progress not found")  # Don't reveal it exists for different user
        
        if user_progress.simulation_id != simulation_id:
            raise NotFoundError("Simulation mismatch")
        
        # Verify simulation exists
        simulation = self.repository.get_simulation_by_id(simulation_id)
        if not simulation:
            raise NotFoundError("Simulation not found")
        
        # Get all scenes
        all_scenes = self.repository.get_scenes_by_simulation_id(simulation_id, eager_load_personas=True)
        if not all_scenes:
            raise NotFoundError("Simulation has no scenes")
        
        # Get current scene
        current_scene_id = user_progress.current_scene_id
        if not current_scene_id:
            # Fallback to first scene if current_scene_id is None
            current_scene_id = all_scenes[0].id
        
        current_scene = self.repository.get_scene_by_id(current_scene_id)
        if not current_scene:
            raise NotFoundError("Current scene not found")
        
        # Ensure orchestrator_data has is_professor_test flag (for backward compatibility with old records)
        if user_progress.orchestrator_data:
            if 'is_professor_test' not in user_progress.orchestrator_data:
                # Query user role once and store it
                user = self.db.query(User).filter(User.id == user_id).first()
                is_professor_test = user and user.role in ['professor', 'admin'] if user else False
                user_progress.orchestrator_data['is_professor_test'] = is_professor_test
                self.db.flush()
        
        # Build persona map from scene-persona associations using bulk loading to avoid N+1 queries
        scene_ids = [scene.id for scene in all_scenes]
        personas_by_scene = self.repository.get_personas_for_scenes(scene_ids) if scene_ids else {}
        scene_personas_map = {
            scene.id: [p.name for p in personas_by_scene.get(scene.id, [])]
            for scene in all_scenes
        }
        
        # Prepare response data
        learning_objectives = simulation.learning_objectives
        if isinstance(learning_objectives, str):
            learning_objectives = [learning_objectives]
        elif learning_objectives is None:
            learning_objectives = []
        
        case_study_url = getattr(simulation, 'case_study_url', None)
        
        # Build simulation response
        simulation_response = {
            "id": simulation.id,
            "title": simulation.title,
            "description": simulation.description,
            "challenge": simulation.challenge,
            "industry": getattr(simulation, 'industry', None),
            "learning_objectives": learning_objectives,
            "student_role": simulation.student_role,
            "total_scenes": len(all_scenes),
            "case_study_url": case_study_url
        }
        
        # Get personas involved in current scene
        involved_personas = self.repository.get_personas_for_scene(current_scene.id)
        
        def is_main_character(persona_name, student_role):
            if not student_role:
                return False
            student_name = student_role.split('(')[0].strip().lower()
            persona_name_clean = persona_name.strip().lower()
            return persona_name_clean == student_name
        
        personas_data = [
            SimulationPersonaResponse(
                id=persona.id,
                simulation_id=persona.simulation_id,
                name=persona.name,
                role=persona.role,
                background=persona.background,
                correlation=persona.correlation,
                primary_goals=(
                    [persona.primary_goals] if isinstance(persona.primary_goals, str) and persona.primary_goals else
                    persona.primary_goals if isinstance(persona.primary_goals, list) else []
                ),
                personality_traits=persona.personality_traits or {},
                image_url=persona.image_url,
                created_at=persona.created_at,
                updated_at=persona.updated_at
            ) for persona in involved_personas
            if not is_main_character(persona.name, simulation.student_role)
        ]
        
        # Build current scene response
        scene_response = {
            "id": current_scene.id,
            "simulation_id": current_scene.simulation_id,
            "title": current_scene.title,
            "description": current_scene.description,
            "user_goal": current_scene.user_goal,
            "scene_order": current_scene.scene_order,
            "estimated_duration": getattr(current_scene, 'estimated_duration', None),
            "image_url": current_scene.image_url,
            "image_prompt": current_scene.image_prompt,
            "timeout_turns": current_scene.timeout_turns,
            "success_metric": current_scene.success_metric,
            "personas_involved": scene_personas_map.get(current_scene.id, []),
            "personas": [p.model_dump() for p in personas_data],
            "scene_type": getattr(current_scene, 'scene_type', None) or "conversation",
            "starter_code": getattr(current_scene, 'starter_code', None),
            "data_files": getattr(current_scene, 'data_files', None),
            "reference_files": getattr(current_scene, 'reference_files', None),
        }

        # Get conversation history
        conversation_logs = self.repository.get_conversation_logs(user_progress_id)
        
        # Format conversation logs for frontend
        messages_history = []
        persona_ids = [log.persona_id for log in conversation_logs if log.persona_id]
        persona_map = {}
        if persona_ids:
            personas = self.repository.get_personas_by_ids(persona_ids)
            persona_map = {p.id: p for p in personas}
        
        for log in conversation_logs:
            persona_name = None
            persona_role = None
            if log.persona_id and log.persona_id in persona_map:
                persona = persona_map[log.persona_id]
                persona_name = persona.name
                persona_role = persona.role
            
            messages_history.append({
                "id": log.id,
                "message_order": log.message_order,
                "message_type": log.message_type,
                "sender_name": log.sender_name,
                "message_content": log.message_content,
                "persona_name": persona_name,
                "persona_role": persona_role,
                "persona_id": log.persona_id,
                "scene_id": log.scene_id,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None
            })
        
        # Build all scenes response - bulk load personas to avoid N+1 queries
        scene_ids = [scene.id for scene in all_scenes]
        personas_by_scene = self.repository.get_personas_for_scenes(scene_ids) if scene_ids else {}
        
        all_scenes_response = []
        for scene in all_scenes:
            scene_personas_list = personas_by_scene.get(scene.id, [])
            scene_personas_data = [
                SimulationPersonaResponse(
                    id=p.id,
                    simulation_id=p.simulation_id,
                    name=p.name,
                    role=p.role,
                    background=p.background,
                    correlation=p.correlation,
                    primary_goals=(
                        [p.primary_goals] if isinstance(p.primary_goals, str) and p.primary_goals else
                        p.primary_goals if isinstance(p.primary_goals, list) else []
                    ),
                    personality_traits=p.personality_traits or {},
                    image_url=p.image_url,
                    created_at=p.created_at,
                    updated_at=p.updated_at
                ) for p in scene_personas_list
                if not is_main_character(p.name, simulation.student_role)
            ]
            all_scenes_response.append({
                "id": scene.id,
                "simulation_id": scene.simulation_id,
                "title": scene.title,
                "description": scene.description,
                "user_goal": scene.user_goal,
                "scene_order": scene.scene_order,
                "estimated_duration": getattr(scene, 'estimated_duration', None),
                "image_url": scene.image_url,
                "image_prompt": scene.image_prompt,
                "timeout_turns": scene.timeout_turns,
                "success_metric": scene.success_metric,
                "personas_involved": scene_personas_map.get(scene.id, []),
                "personas": [p.model_dump() for p in scene_personas_data],
                "scene_type": getattr(scene, 'scene_type', None) or "conversation",
                "starter_code": getattr(scene, 'starter_code', None),
                "data_files": getattr(scene, 'data_files', None),
                "reference_files": getattr(scene, 'reference_files', None),
            })

        # Extract turn_count from orchestrator_data state
        # CRITICAL: Refresh the session to ensure we see the latest committed changes
        self.db.refresh(user_progress)
        
        turn_count = 0
        if user_progress.orchestrator_data and 'state' in user_progress.orchestrator_data:
            saved_state = user_progress.orchestrator_data.get('state', {})
            turn_count = saved_state.get('turn_count', 0)
            import logging
            logger = logging.getLogger(__name__)
            logger.info(
                f"[RESUME_SIMULATION] Loaded turn_count={turn_count} from orchestrator_data for "
                f"user_progress_id={user_progress_id}, orchestrator_data exists: {user_progress.orchestrator_data is not None}, "
                f"state exists: {'state' in user_progress.orchestrator_data if user_progress.orchestrator_data else False}"
            )
        else:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"[RESUME_SIMULATION] No orchestrator_data or state found for user_progress_id={user_progress_id}, "
                f"using turn_count=0"
            )
        
        # Extract completed scene IDs from scenes_completed
        completed_scene_ids = user_progress.scenes_completed or []
        
        return SimulationStartResponse(
            user_progress_id=user_progress_id,
            simulation=simulation_response,
            current_scene=scene_response,
            simulation_status=user_progress.simulation_status,
            conversation_history=messages_history,
            is_resuming=True,
            all_scenes=all_scenes_response,
            turn_count=turn_count,
            completed_scene_ids=completed_scene_ids,
            sandbox_id=user_progress.sandbox_id,
        )

