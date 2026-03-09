"""
Chat Handler.

Handles chat streaming, message processing, @mentions, @all, and persona interactions.
"""

from typing import Dict, Any, Optional, AsyncGenerator
from sqlalchemy.orm import Session
from datetime import datetime
import json
import asyncio
import re
import logging
import time

from modules.simulation.repository import SimulationRepository
from modules.simulation.core import ChatOrchestrator, OrchestratorManager, SceneProgressionHandler
from modules.simulation.handlers.commands import (
    handle_begin_command,
    handle_mention,
    handle_all_mention,
    handle_timeout
)
from common.db.models import UserProgress
from common.config import get_settings
from common.utils.concurrency import ai_concurrency_slot
from common.services.conversation_cache_service import conversation_cache

settings = get_settings()
_is_dev = settings.environment != "production"
logger = logging.getLogger(__name__)


class ChatHandler:
    """Handles chat streaming and message processing."""
    
    def __init__(self, db: Session, repository: SimulationRepository):
        self.db = db
        self.repository = repository
    
    async def handle_stream_message(
        self,
        user_id: int,
        user_progress_id: int,
        message: str,
        orchestrator_manager: OrchestratorManager,
        scene_progression_handler: SceneProgressionHandler,
        generate_scene_intro_fn: callable
    ) -> AsyncGenerator[str, None]:
        """
        Handle streaming chat message.
        
        Args:
            user_id: ID of the user
            user_progress_id: ID of the user progress
            message: User message
            orchestrator_manager: OrchestratorManager instance
            scene_progression_handler: SceneProgressionHandler instance
            generate_scene_intro_fn: Function to generate scene intro messages
            
        Yields:
            SSE event strings
        """
        scene_completed = False
        next_scene_id = None
        full_response = ""
        
        try:
            # Validate user progress
            if not user_progress_id:
                yield f"data: {json.dumps({'error': 'user_progress_id is required'})}\n\n"
                return
            
            user_progress = self.repository.get_user_progress_by_id(user_progress_id)
            
            if not user_progress:
                yield f"data: {json.dumps({'error': 'User progress not found'})}\n\n"
                return
            
            if user_progress.user_id != user_id:
                yield f"data: {json.dumps({'error': 'Access denied'})}\n\n"
                return
            
            if not user_progress.orchestrator_data:
                yield f"data: {json.dumps({'error': 'Simulation not properly initialized'})}\n\n"
                return
            
            # Load orchestrator
            orchestrator = orchestrator_manager.load_orchestrator(user_progress, user_id)
            
            # Initialize LangChain session if needed
            # CRITICAL: Check return value - if False, session_id won't be set and conversation logs will fail
            langchain_initialized = await orchestrator_manager.initialize_langchain_session(orchestrator, user_progress.id)
            if not langchain_initialized:
                logger.warning(
                    f"LangChain session initialization failed for user_progress_id={user_progress.id}. "
                    f"Conversation history may not work correctly."
                )
            
            # Load saved state (this may restore session_id from previous request)
            orchestrator_manager.load_orchestrator_state(orchestrator, user_progress)
            
            # Verify session_id is set after initialization and state loading
            if orchestrator.langchain_enabled and (not hasattr(orchestrator.state, 'session_id') or not orchestrator.state.session_id):
                error_msg = (
                    f"session_id not set after LangChain initialization. "
                    f"user_progress_id={user_progress.id}, langchain_initialized={langchain_initialized}. "
                    f"This will cause conversation log creation to fail."
                )
                logger.error(error_msg)
                # Don't fail the request, but log the error clearly
            
            # Handle scene transition cleanup
            orchestrator_manager.handle_scene_transition_cleanup(orchestrator, user_progress.id)
            
            current_scene = orchestrator.simulation.get('scenes', [{}])[orchestrator.state.current_scene_index]
            correct_scene_id = current_scene.get('id')
            
            # Validate command words are one-word only
            trimmed_message = message.lower().strip()
            is_command = trimmed_message in ["begin", "help"]
            
            # If it's a command with multiple words, treat it as a regular message
            if is_command and len(message.split()) > 1:
                is_command = False
            
            # Handle "begin" command
            if trimmed_message == "begin" and is_command:
                async for chunk in handle_begin_command(
                    self.db, self.repository, orchestrator, user_progress, message, current_scene, generate_scene_intro_fn
                ):
                    yield chunk
                return
            
            # Handle "help" command (don't save, just return help message)
            if trimmed_message == "help" and is_command:
                help_message = """**Available Commands:**
• **begin** - Start the simulation
• **help** - Show this help message

**How to Interact:**
• Use @mentions to talk to specific personas: @persona_name your message
• Use @all to message all personas at once: @all your message
• Type normally to get guidance from the orchestrator"""
                
                for char in help_message:
                    yield f"data: {json.dumps({'content': char, 'done': False})}\n\n"
                    await asyncio.sleep(0.03)
                
                yield f"data: {json.dumps({'done': True, 'persona_name': 'ChatOrchestrator', 'persona_id': None})}\n\n"
                return
            
            # Initialize variables
            is_all_message_global = False
            scene_personas_count = 0
            ai_response = ""
            persona_name = "ChatOrchestrator"
            persona_id = None
            
            # Check if this is an @all message
            # Updated regex to capture special chars in persona names (dots, parentheses, hyphens, ampersands, etc.)
            mention_match_precheck = re.search(r'@([\w().\-&]+)', message.lower())
            if mention_match_precheck and mention_match_precheck.group(1).lower() == 'all':
                is_all_message_global = True
            
            # Determine session_id for user message based on @mention target
            # Default to orchestrator session_id, will be updated if @mention targets specific persona
            user_message_session_id = orchestrator.state.session_id if hasattr(orchestrator.state, 'session_id') else None
            
            # Handle @mention(s)
            # Updated regex to capture special chars in persona names (dots, parentheses, hyphens, ampersands, etc.)
            mention_matches = re.findall(r'@([\w().\-&]+)', message.lower())
            if mention_matches:
                persona_id_str = mention_matches[0]
                
                if persona_id_str.lower() == 'all':
                    # Handle @all
                    # Save user message first (if not a command)
                    if not is_command:
                        next_order = self.repository.get_next_message_order(user_progress_id)
                        self.repository.create_conversation_log(
                            user_progress_id=user_progress.id,
                            scene_id=correct_scene_id,
                            message_type="user",
                            sender_name="User",
                            message_content=message,
                            message_order=next_order,
                            session_id=user_message_session_id
                        )
                        self.db.commit()
                        
                        # Append to conversation cache
                        conversation_cache.append_message(
                            user_progress_id=user_progress.id,
                            scene_id=correct_scene_id,
                            message_data={
                                "id": None,
                                "user_progress_id": user_progress.id,
                                "scene_id": correct_scene_id,
                                "message_type": "user",
                                "sender_name": "User",
                                "message_content": message,
                                "message_order": next_order,
                                "session_id": user_message_session_id,
                                "persona_id": None,
                                "created_at": None,
                            }
                        )
                        
                        # NOTE: For @all messages, turn_count is incremented per persona response
                        # We don't increment here because each persona response counts as a separate turn
                        logger.debug(
                            f"[TURN_COUNT] @all message saved - turn_count will be incremented per persona response, "
                            f"current turn_count={orchestrator.state.turn_count}"
                        )
                    
                    # TRUE STREAMING for @all: Start all persona streams in parallel
                    # This kicks off all LLM calls immediately, so subsequent personas are ready faster
                    personas_involved = current_scene.get('personas_involved', [])
                    scene_personas = []
                    for persona in orchestrator.simulation.get('personas', []):
                        if persona['identity']['name'] in personas_involved:
                            scene_personas.append(persona)

                    # Build nested scene_context matching the single @mention path
                    scene_context_for_all = {
                        'current_scene': {
                            'title': current_scene.get('title'),
                            'description': current_scene.get('description'),
                            'objectives': current_scene.get('objectives', []),
                        },
                        'simulation': {
                            'title': orchestrator.simulation.get('title'),
                            'description': orchestrator.simulation.get('description'),
                            'challenge': orchestrator.simulation.get('challenge'),
                            'student_role': orchestrator.simulation.get('student_role'),
                        },
                    }

                    if not scene_personas:
                        # No personas in scene - yield error message
                        yield f"data: {json.dumps({'content': 'There are no personas available in this scene.', 'done': True, 'persona_name': 'ChatOrchestrator', 'persona_id': None})}\n\n"
                        return
                    
                    logger.info(f"[ALL_STREAM] Starting TRUE STREAMING for @all with {len(scene_personas)} personas, user_progress_id={user_progress_id}")
                    
                    # Create streaming generators for all personas (starts LLM calls immediately)
                    stream_generators = []
                    for persona in scene_personas:
                        persona_simulation_id = persona.get('id')
                        persona_db_id = persona.get('db_id')
                        persona_name_val = persona['identity']['name']
                        
                        if str(persona_simulation_id) in orchestrator.persona_agents:
                            agent = orchestrator.persona_agents[str(persona_simulation_id)]
                            stream_gen = agent.chat_stream(
                                message=message,
                                # Build the full nested structure that _get_system_prompt() expects.
                                # Passing current_scene directly (flat dict) left both simulation_block
                                # and scene_block empty — agents had no case study or scene context.
                                scene_context={
                                    'current_scene': {
                                        'title': current_scene.get('title'),
                                        'description': current_scene.get('description'),
                                        'objectives': current_scene.get('objectives', []),
                                    },
                                    'simulation': {
                                        'title': orchestrator.simulation.get('title'),
                                        'description': orchestrator.simulation.get('description'),
                                        'challenge': orchestrator.simulation.get('challenge'),
                                        'student_role': orchestrator.simulation.get('student_role'),
                                    },
                                },
                                user_progress_id=user_progress.id,
                                scene_id=correct_scene_id,
                                db=self.db
                            )
                            stream_generators.append({
                                'generator': stream_gen,
                                'persona_name': persona_name_val,
                                'persona_id': persona_db_id,
                            })
                    
                    is_all_message_global = bool(stream_generators)
                    
                    # Stream each persona's response (LLM calls already started in parallel)
                    if stream_generators:
                        if 'next_order' not in locals():
                            next_order = self.repository.get_next_message_order(user_progress_id)
                        current_order = next_order + 1
                        
                        all_stream_start = time.time()
                        first_token_received = False
                        
                        for gen_data in stream_generators:
                            persona_name_resp = gen_data['persona_name']
                            persona_id_resp = gen_data['persona_id']
                            stream_gen = gen_data['generator']
                            
                            orchestrator.state.turn_count += 1
                            current_turn_count = orchestrator.state.turn_count
                            
                            # Stream tokens as they arrive from OpenAI
                            full_response = ""
                            token_count = 0
                            persona_first_token = False
                            async for token in stream_gen:
                                if not first_token_received:
                                    ttfb_ms = int((time.time() - all_stream_start) * 1000)
                                    logger.info(f"[ALL_STREAM_TTFB] ⚡ First token received in {ttfb_ms}ms for @all (persona: {persona_name_resp})")
                                    first_token_received = True
                                    persona_first_token = True
                                elif not persona_first_token:
                                    # Log TTFB for subsequent personas too
                                    ttfb_ms = int((time.time() - all_stream_start) * 1000)
                                    logger.info(f"[ALL_STREAM] Persona {persona_name_resp} first token at {ttfb_ms}ms")
                                    persona_first_token = True
                                full_response += token
                                token_count += 1
                                yield f"data: {json.dumps({'content': token, 'done': False, 'persona_name': persona_name_resp, 'persona_id': str(persona_id_resp) if persona_id_resp else None})}\n\n"
                            
                            logger.info(f"[ALL_STREAM] Persona {persona_name_resp} streamed {token_count} tokens, {len(full_response)} chars")
                            
                            # Yield done for this persona
                            yield f"data: {json.dumps({'done': True, 'persona_name': persona_name_resp, 'persona_id': str(persona_id_resp) if persona_id_resp else None, 'scene_completed': False, 'next_scene_id': None, 'turn_count': current_turn_count, 'full_content': full_response})}\n\n"
                            
                            # Save persona response (note: chat_stream already saves via callback,
                            # but we save again here for consistency with message_order tracking)
                            # Actually, chat_stream already saves, so we just need cache + state
                            
                            # CRITICAL: Save orchestrator state after each persona response for @all
                            orchestrator_manager.save_orchestrator_state(orchestrator, user_progress)
                            self.db.commit()
                            
                            # Append persona response to conversation cache
                            conversation_cache.append_message(
                                user_progress_id=user_progress.id,
                                scene_id=correct_scene_id,
                                message_data={
                                    "id": None,
                                    "user_progress_id": user_progress.id,
                                    "scene_id": correct_scene_id,
                                    "message_type": "ai_persona",
                                    "sender_name": persona_name_resp,
                                    "message_content": full_response,
                                    "message_order": current_order,
                                    "session_id": orchestrator.state.session_id if hasattr(orchestrator.state, 'session_id') else None,
                                    "persona_id": persona_id_resp,
                                    "created_at": None,
                                }
                            )
                            
                            current_order += 1
                        
                        ai_response = ""  # Already streamed
                elif len([m for m in mention_matches if m.lower() != 'all']) > 1:
                    # ========================================
                    # MULTI-MENTION HANDLER
                    # Process multiple mentioned personas sequentially
                    # so each persona sees the previous persona's response.
                    # ========================================
                    non_all_mentions = [m for m in mention_matches if m.lower() != 'all']

                    # Resolve all mentioned persona names to persona objects
                    personas = orchestrator.simulation.get('personas', [])

                    # Build name mapping (same logic as single-mention handler)
                    name_mapping: Dict[str, Any] = {}
                    persona_by_sim_id: Dict[str, Any] = {}
                    for persona in personas:
                        persona_handle = str(persona.get('id', '')).lower()
                        name = persona['identity']['name'].lower()
                        sim_id = persona['id']
                        persona_by_sim_id[str(sim_id)] = persona

                        if persona_handle:
                            name_mapping[persona_handle] = sim_id
                        name_mapping[name] = sim_id
                        name_mapping[name.replace("'", "").replace(" ", "_")] = sim_id
                        name_mapping[name.replace("'", "").replace(" ", "")] = sim_id
                        sanitized_name = re.sub(r'[^a-z0-9_]', '', name.replace(' ', '_'))
                        name_mapping[sanitized_name] = sim_id
                        first_name = name.split()[0]
                        name_mapping[first_name] = sim_id
                        name_mapping[first_name.replace("'", "")] = sim_id
                        sanitized_first = re.sub(r'[^a-z0-9_]', '', first_name)
                        name_mapping[sanitized_first] = sim_id

                    # Resolve each mention to a persona object (preserving mention order, deduplicated)
                    resolved_personas = []
                    seen_sim_ids = set()
                    for mention_str in non_all_mentions:
                        search_name = mention_str.lower()
                        persona_simulation_id = None
                        matched_persona = None

                        # Direct ID match
                        matched_persona = next(
                            (p for p in personas if str(p.get('id', '')).lower() == search_name),
                            None,
                        )
                        if matched_persona:
                            persona_simulation_id = matched_persona.get('id')

                        # Name mapping match
                        if persona_simulation_id is None and search_name in name_mapping:
                            persona_simulation_id = name_mapping[search_name]
                            matched_persona = persona_by_sim_id.get(str(persona_simulation_id))

                        # Fuzzy match
                        if persona_simulation_id is None:
                            for name_key, pid in name_mapping.items():
                                if (search_name in name_key or name_key in search_name or
                                    search_name.replace("'", "").replace("_", "") in name_key.replace("'", "").replace("_", "")):
                                    persona_simulation_id = pid
                                    matched_persona = persona_by_sim_id.get(str(persona_simulation_id))
                                    break

                        # Deduplicate (same persona mentioned twice)
                        if matched_persona and str(persona_simulation_id) not in seen_sim_ids:
                            seen_sim_ids.add(str(persona_simulation_id))
                            resolved_personas.append({
                                'persona': matched_persona,
                                'persona_simulation_id': persona_simulation_id,
                                'persona_name': matched_persona['identity']['name'],
                                'persona_db_id': matched_persona.get('db_id'),
                            })

                    if not resolved_personas:
                        err_msg = "I don't recognize those personas. Please use @mentions to talk to specific team members."
                        for char in err_msg:
                            full_response += char
                            yield f"data: {json.dumps({'content': char, 'done': False, 'persona_name': 'ChatOrchestrator', 'persona_id': None})}\n\n"
                            await asyncio.sleep(0.03)
                    else:
                        # Save user message ONCE with base session_id (same as @all pattern)
                        if not is_command:
                            next_order = self.repository.get_next_message_order(user_progress_id)
                            self.repository.create_conversation_log(
                                user_progress_id=user_progress.id,
                                scene_id=correct_scene_id,
                                message_type="user",
                                sender_name="User",
                                message_content=message,
                                message_order=next_order,
                                session_id=user_message_session_id
                            )
                            self.db.commit()

                            conversation_cache.append_message(
                                user_progress_id=user_progress.id,
                                scene_id=correct_scene_id,
                                message_data={
                                    "id": None,
                                    "user_progress_id": user_progress.id,
                                    "scene_id": correct_scene_id,
                                    "message_type": "user",
                                    "sender_name": "User",
                                    "message_content": message,
                                    "message_order": next_order,
                                    "session_id": user_message_session_id,
                                    "persona_id": None,
                                    "created_at": None,
                                }
                            )

                            logger.debug(
                                f"[TURN_COUNT] Multi-mention message saved - turn_count will be incremented per persona response, "
                                f"current turn_count={orchestrator.state.turn_count}"
                            )

                        # Process each persona SEQUENTIALLY so each sees the previous one's response
                        if 'next_order' not in locals():
                            next_order = self.repository.get_next_message_order(user_progress_id)
                        current_order = next_order + 1

                        is_all_message_global = True  # Skip orchestrator response at end

                        logger.info(f"[MULTI_MENTION] Processing {len(resolved_personas)} personas sequentially, user_progress_id={user_progress_id}")

                        for rp in resolved_personas:
                            p_name = rp['persona_name']
                            p_db_id = rp['persona_db_id']
                            p_sim_id = rp['persona_simulation_id']

                            if str(p_sim_id) not in orchestrator.persona_agents:
                                logger.warning(f"[MULTI_MENTION] Persona agent not found for {p_name} (sim_id={p_sim_id})")
                                continue

                            persona_agent = orchestrator.persona_agents[str(p_sim_id)]

                            # Increment turn_count per persona response (matching @all behavior)
                            orchestrator.state.turn_count += 1
                            current_turn_count = orchestrator.state.turn_count

                            # Stream persona response sequentially
                            # Each chat_stream call loads history from DB, which now includes
                            # the previous persona's response (saved by PersonaCallbackHandler)
                            full_response_multi = ""
                            token_count = 0
                            try:
                                async for token in persona_agent.chat_stream(
                                    message=message,
                                    scene_context={
                                        'current_scene': {
                                            'title': current_scene.get('title'),
                                            'description': current_scene.get('description'),
                                            'objectives': current_scene.get('objectives', []),
                                        },
                                        'simulation': {
                                            'title': orchestrator.simulation.get('title'),
                                            'description': orchestrator.simulation.get('description'),
                                            'challenge': orchestrator.simulation.get('challenge'),
                                            'student_role': orchestrator.simulation.get('student_role'),
                                        },
                                    },
                                    user_progress_id=user_progress.id,
                                    scene_id=correct_scene_id,
                                    db=self.db,
                                ):
                                    full_response_multi += token
                                    token_count += 1
                                    yield f"data: {json.dumps({'content': token, 'done': False, 'persona_name': p_name, 'persona_id': str(p_db_id) if p_db_id else None})}\n\n"

                                logger.info(f"[MULTI_MENTION] Persona {p_name} streamed {token_count} tokens, {len(full_response_multi)} chars")

                            except Exception as e:
                                logger.error(f"[MULTI_MENTION] Error streaming persona {p_name}: {e}", exc_info=True)
                                error_msg = "I'm sorry, I'm having trouble processing that right now."
                                for char in error_msg:
                                    full_response_multi += char
                                    yield f"data: {json.dumps({'content': char, 'done': False, 'persona_name': p_name, 'persona_id': str(p_db_id) if p_db_id else None})}\n\n"

                            # Yield done for this persona (matching @all pattern)
                            yield f"data: {json.dumps({'done': True, 'persona_name': p_name, 'persona_id': str(p_db_id) if p_db_id else None, 'scene_completed': False, 'next_scene_id': None, 'turn_count': current_turn_count, 'full_content': full_response_multi})}\n\n"

                            # Save orchestrator state after each persona (matching @all pattern)
                            orchestrator_manager.save_orchestrator_state(orchestrator, user_progress)
                            self.db.commit()

                            # Append persona response to conversation cache
                            conversation_cache.append_message(
                                user_progress_id=user_progress.id,
                                scene_id=correct_scene_id,
                                message_data={
                                    "id": None,
                                    "user_progress_id": user_progress.id,
                                    "scene_id": correct_scene_id,
                                    "message_type": "ai_persona",
                                    "sender_name": p_name,
                                    "message_content": full_response_multi,
                                    "message_order": current_order,
                                    "session_id": orchestrator.state.session_id if hasattr(orchestrator.state, 'session_id') else None,
                                    "persona_id": p_db_id,
                                    "created_at": None,
                                }
                            )

                            current_order += 1

                        ai_response = ""  # Already streamed
                else:
                    # Handle single @mention - stream directly from agent
                    target_persona = None
                    # First try a direct handle match against persona IDs, since the
                    # frontend passes handles like "nick_elliott" that map to persona["id"].
                    personas = orchestrator.simulation.get('personas', [])
                    search_name = persona_id_str.lower()
                    target_persona = next(
                        (p for p in personas if str(p.get('id', '')).lower() == search_name),
                        None,
                    )
                    # Track the simulation-level persona ID we resolved so we can look
                    # up the correct PersonaAgent in orchestrator.persona_agents.
                    persona_simulation_id = None
                    if target_persona is not None:
                        persona_simulation_id = target_persona.get("id")

                    if target_persona is None:
                        # Build name mapping for more flexible lookup (display name variants).
                        name_mapping: Dict[str, Any] = {}
                        for persona in personas:
                            persona_handle = str(persona.get('id', '')).lower()
                            name = persona['identity']['name'].lower()
                            # Allow lookup by handle (e.g. @nick_elliott) and by various
                            # normalized forms of the display name.
                            if persona_handle:
                                name_mapping[persona_handle] = persona['id']
                            name_mapping[name] = persona['id']
                            name_mapping[name.replace("'", "").replace(" ", "_")] = persona['id']
                            name_mapping[name.replace("'", "").replace(" ", "")] = persona['id']
                            # Sanitized version: remove all special chars (parentheses, dots, etc.)
                            sanitized_name = re.sub(r'[^a-z0-9_]', '', name.replace(' ', '_'))
                            name_mapping[sanitized_name] = persona['id']
                            first_name = name.split()[0]
                            name_mapping[first_name] = persona['id']
                            name_mapping[first_name.replace("'", "")] = persona['id']
                            # Sanitized first name
                            sanitized_first = re.sub(r'[^a-z0-9_]', '', first_name)
                            name_mapping[sanitized_first] = persona['id']

                        if search_name in name_mapping:
                            persona_simulation_id = name_mapping[search_name]
                            target_persona = next((p for p in personas if p['id'] == persona_simulation_id), None)
                        else:
                            # Try fuzzy matching on the normalized keys
                            for name, pid in name_mapping.items():
                                if (
                                    search_name in name
                                    or name in search_name
                                    or search_name.replace("'", "").replace("_", "") in name.replace("'", "").replace("_", "")
                                ):
                                    persona_simulation_id = pid
                                    target_persona = next((p for p in personas if p['id'] == persona_simulation_id), None)
                                    break

                    

                    if target_persona and orchestrator.langchain_enabled:
                        # Initialize persona_name and persona_id before try block so they're available in exception handler
                        persona_name = target_persona['identity']['name']
                        persona_id = target_persona.get('db_id')
                        try:
                            # Stream response directly from agent
                            current_scene = orchestrator.simulation.get('scenes', [{}])[orchestrator.state.current_scene_index]

                            # Get persona agent and stream its response
                            if str(persona_simulation_id) in orchestrator.persona_agents:
                                persona_agent = orchestrator.persona_agents[str(persona_simulation_id)]
                                # Use persona's session_id for user message so it matches when loading history
                                user_message_session_id = persona_agent.persona_session_id
                                
                                if _is_dev:
                                    logger.debug(
                                        f"Saving user message with session_id={user_message_session_id}, "
                                        f"persona_session_id={persona_agent.persona_session_id}"
                                    )
                                
                                # Save user message with persona's session_id (if not already saved)
                                # CRITICAL: Commit before calling agent.chat() so history loading can see it
                                if not is_command:
                                    next_order = self.repository.get_next_message_order(user_progress_id)
                                    self.repository.create_conversation_log(
                                        user_progress_id=user_progress.id,
                                        scene_id=correct_scene_id,
                                        message_type="user",
                                        sender_name="User",
                                        message_content=message,
                                        message_order=next_order,
                                        session_id=user_message_session_id
                                    )
                                    self.db.commit()  # Commit so agent.chat() can see this message when loading history
                                    
                                    # Append to conversation cache
                                    conversation_cache.append_message(
                                        user_progress_id=user_progress.id,
                                        scene_id=correct_scene_id,
                                        message_data={
                                            "id": None,
                                            "user_progress_id": user_progress.id,
                                            "scene_id": correct_scene_id,
                                            "message_type": "user",
                                            "sender_name": "User",
                                            "message_content": message,
                                            "message_order": next_order,
                                            "session_id": user_message_session_id,
                                            "persona_id": None,
                                            "created_at": None,
                                        }
                                    )
                                    
                                    # NOTE: For single @mention, turn_count will be incremented when persona responds
                                    # (matching @all behavior where turn_count increments per persona response at line 217)
                                    logger.debug(
                                        f"[TURN_COUNT] User message saved - turn_count will be incremented when persona responds, "
                                        f"current turn_count={orchestrator.state.turn_count}"
                                    )
                                
                                # Build the full scene_context that _get_system_prompt() expects.
                                # Previously this was a flat dict missing the 'simulation' key,
                                # which caused the CASE STUDY CONTEXT block to always be empty.
                                scene_context = {
                                    'current_scene': {
                                        'title': current_scene.get('title'),
                                        'description': current_scene.get('description'),
                                        'objectives': current_scene.get('objectives', []),
                                    },
                                    'simulation': {
                                        'title': orchestrator.simulation.get('title'),
                                        'description': orchestrator.simulation.get('description'),
                                        'challenge': orchestrator.simulation.get('challenge'),
                                        'student_role': orchestrator.simulation.get('student_role'),
                                    },
                                }

                                # Apply AI concurrency limits around persona chat
                                async with ai_concurrency_slot() as acquired:
                                    if not acquired:
                                        logger.warning(f"[CAPACITY] AI slot unavailable for persona {persona_name} (user_progress_id={user_progress_id}) - AI system at capacity")
                                        ai_response = (
                                            "The system is handling too many AI requests at the moment. "
                                            "Please wait a few seconds and try again."
                                        )
                                        for char in ai_response:
                                            full_response += char
                                            yield f"data: {json.dumps({'content': char, 'done': False, 'persona_name': persona_name, 'persona_id': str(persona_id) if persona_id else None})}\n\n"
                                            await asyncio.sleep(0.03)
                                    else:
                                        # TRUE STREAMING: Stream tokens as they arrive from OpenAI
                                        # This dramatically reduces TTFB from ~3-4s to ~500ms
                                        try:
                                            logger.info(
                                                f"[PERSONA_CHAT] Starting TRUE STREAMING for persona={persona_name} "
                                                f"(persona_id={persona_id}), user_progress_id={user_progress_id}, "
                                                f"message='{message[:100]}...'"
                                            )
                                            
                                            # Stream tokens directly from OpenAI as they arrive
                                            response_text = ""
                                            token_count = 0
                                            async for token in persona_agent.chat_stream(
                                                message=message,
                                                scene_context=scene_context,
                                                user_progress_id=orchestrator.user_progress_id,
                                                scene_id=correct_scene_id,
                                                db=self.db,
                                            ):
                                                response_text += token
                                                full_response += token
                                                token_count += 1
                                                # Stream each token immediately - no artificial delay!
                                                yield f"data: {json.dumps({'content': token, 'done': False, 'persona_name': persona_name, 'persona_id': str(persona_id) if persona_id else None})}\n\n"
                                            
                                            if not response_text or len(response_text.strip()) == 0:
                                                logger.warning(
                                                    f"[PERSONA_CHAT] Persona {persona_name} returned empty response "
                                                    f"for user_progress_id={user_progress_id}"
                                                )
                                                response_text = "I'm sorry, I didn't understand that. Could you rephrase?"
                                                for char in response_text:
                                                    yield f"data: {json.dumps({'content': char, 'done': False, 'persona_name': persona_name, 'persona_id': str(persona_id) if persona_id else None})}\n\n"
                                            
                                            logger.info(
                                                f"[PERSONA_CHAT] Persona {persona_name} streamed {token_count} tokens, "
                                                f"{len(response_text)} chars for user_progress_id={user_progress_id}"
                                            )
                                            
                                            # CRITICAL: Increment turn_count when persona responds (matching @all behavior)
                                            turn_count_before = orchestrator.state.turn_count
                                            orchestrator.state.turn_count += 1
                                            current_turn_count = orchestrator.state.turn_count
                                            logger.info(
                                                f"[TURN_COUNT] Incremented turn_count from {turn_count_before} to {current_turn_count} "
                                                f"for single @mention persona response (user_progress_id={user_progress_id}, persona={persona_name})"
                                            )
                                            # Save orchestrator state immediately after incrementing turn_count
                                            orchestrator_manager.save_orchestrator_state(orchestrator, user_progress)
                                            self.db.commit()
                                            
                                            # Append to conversation cache (response already saved by chat_stream)
                                            persona_session_id = None
                                            if hasattr(persona_agent, 'persona_session_id'):
                                                persona_session_id = persona_agent.persona_session_id
                                            elif hasattr(orchestrator.state, 'session_id'):
                                                persona_session_id = orchestrator.state.session_id
                                            
                                            conversation_cache.append_message(
                                                user_progress_id=user_progress.id,
                                                scene_id=correct_scene_id,
                                                message_data={
                                                    "id": None,
                                                    "user_progress_id": user_progress.id,
                                                    "scene_id": correct_scene_id,
                                                    "message_type": "ai_persona",
                                                    "sender_name": persona_name,
                                                    "message_content": response_text,
                                                    "message_order": self.repository.get_next_message_order(user_progress_id) - 1,
                                                    "session_id": persona_session_id,
                                                    "persona_id": persona_id,
                                                    "created_at": None,
                                                }
                                            )
                                            
                                            # CRITICAL: Yield final metadata with turn_count (matching @all behavior)
                                            yield f"data: {json.dumps({'done': True, 'persona_name': persona_name, 'persona_id': str(persona_id) if persona_id else None, 'scene_completed': False, 'next_scene_id': None, 'turn_count': current_turn_count, 'full_content': response_text})}\n\n"
                                            
                                            # CRITICAL: Return early for single @mention (matching @all behavior)
                                            return
                                        except Exception as e:
                                            import traceback
                                            error_msg = str(e)
                                            logger.error(
                                                f"[PERSONA_CHAT] Error in persona chat for {persona_name} "
                                                f"(persona_id={persona_id}), user_progress_id={user_progress_id}: {error_msg}",
                                                exc_info=True
                                            )
                                            if _is_dev:
                                                traceback.print_exc()
                                            ai_response = "I'm sorry, I'm having trouble processing that right now. Please try again."
                                            for char in ai_response:
                                                full_response += char
                                                yield f"data: {json.dumps({'content': char, 'done': False, 'persona_name': persona_name, 'persona_id': str(persona_id) if persona_id else None})}\n\n"
                                                await asyncio.sleep(0.03)
                            else:
                                ai_response = "I'm sorry, I'm not available right now. Please try again."
                                for char in ai_response:
                                    full_response += char
                                    yield f"data: {json.dumps({'content': char, 'done': False, 'persona_name': persona_name, 'persona_id': str(persona_id) if persona_id else None})}\n\n"
                                    await asyncio.sleep(0.03)
                        except Exception as e:
                            import traceback
                            error_msg = str(e)
                            persona_id_str = str(persona_simulation_id) if 'persona_simulation_id' in locals() else 'unknown'
                            
                            # persona_name and persona_id are already set before the try block
                            # so they should be available here. If for some reason they're not set,
                            # fall back to ChatOrchestrator
                            if not persona_name or persona_name == "ChatOrchestrator":
                                persona_name = "ChatOrchestrator"
                                persona_id = None
                            
                            logger.error(
                                f"Error streaming persona response for persona {persona_id_str} "
                                f"(persona_name={persona_name}, persona_id={persona_id}): {error_msg}",
                                exc_info=True
                            )
                            if _is_dev:
                                traceback.print_exc()
                            ai_response = f"I'm sorry, I'm having trouble processing that right now. Please try again or ask the orchestrator for help."
                            for char in ai_response:
                                full_response += char
                                yield f"data: {json.dumps({'content': char, 'done': False, 'persona_name': persona_name, 'persona_id': str(persona_id) if persona_id else None})}\n\n"
                                await asyncio.sleep(0.03)
                    else:
                        ai_response = f"I don't recognize that persona. Available team members: {', '.join([p['id'] for p in orchestrator.simulation.get('personas', [])])}. Please use @mentions to talk to specific team members."
                        persona_name = "ChatOrchestrator"
                        persona_id = None
                        for char in ai_response:
                            full_response += char
                            yield f"data: {json.dumps({'content': char, 'done': False, 'persona_name': persona_name, 'persona_id': None})}\n\n"
                            await asyncio.sleep(0.03)
            else:
                # General orchestrator response
                # Save user message for non-@mention messages (if not already saved)
                if not is_command and not mention_matches:
                    next_order = self.repository.get_next_message_order(user_progress_id)
                    self.repository.create_conversation_log(
                        user_progress_id=user_progress.id,
                        scene_id=correct_scene_id,
                        message_type="user",
                        sender_name="User",
                        message_content=message,
                        message_order=next_order,
                        session_id=user_message_session_id
                    )
                    self.db.flush()
                    
                    # CRITICAL: Increment turn_count when user sends message (not when orchestrator responds)
                    # This ensures user messages count toward timeout turns
                    turn_count_before = orchestrator.state.turn_count
                    orchestrator.state.turn_count += 1
                    logger.info(
                        f"[TURN_COUNT] Incremented turn_count from {turn_count_before} to {orchestrator.state.turn_count} "
                        f"for user message to orchestrator (user_progress_id={user_progress_id}, message='{message[:50]}...')"
                    )
                    # Save orchestrator state immediately after incrementing turn_count
                    orchestrator_manager.save_orchestrator_state(orchestrator, user_progress)
                    # CRITICAL: Commit immediately to persist turn_count (not just flush)
                    # This ensures turn_count is saved even if later processing fails
                    self.db.commit()
                    
                    # Append to conversation cache
                    conversation_cache.append_message(
                        user_progress_id=user_progress.id,
                        scene_id=correct_scene_id,
                        message_data={
                            "id": None,
                            "user_progress_id": user_progress.id,
                            "scene_id": correct_scene_id,
                            "message_type": "user",
                            "sender_name": "User",
                            "message_content": message,
                            "message_order": next_order,
                            "session_id": user_message_session_id,
                            "persona_id": None,
                            "created_at": None,
                        }
                    )
                    
                    logger.debug(
                        f"[TURN_COUNT] Committed turn_count={orchestrator.state.turn_count} "
                        f"for user_progress_id={user_progress_id}"
                    )
                
                ai_response = "I'm here to help guide your business simulation. Use @mentions to talk to specific team members or ask me for strategic guidance."
                persona_name = "ChatOrchestrator"
                persona_id = None
                for char in ai_response:
                    full_response += char
                    yield f"data: {json.dumps({'content': char, 'done': False, 'persona_name': persona_name, 'persona_id': None})}\n\n"
                    await asyncio.sleep(0.03)
            
            # Save AI response to database (only if not @all and not single @mention)
            # NOTE: For persona responses, PersonaCallbackHandler already saves and commits
            # the response immediately when the LLM finishes. We only need to save here for
            # orchestrator responses (non-persona messages).
            # For @all and single @mention, we already yielded the final metadata, so skip the final yield
            if not is_all_message_global and not persona_id:
                # Only save orchestrator responses (not persona responses)
                # Ensure next_order is defined (should be set when user message was saved)
                if 'next_order' not in locals():
                    next_order = self.repository.get_next_message_order(user_progress_id)
                
                # Use orchestrator's session_id for orchestrator responses
                ai_response_session_id = orchestrator.state.session_id if hasattr(orchestrator.state, 'session_id') else None
                
                self.repository.create_conversation_log(
                    user_progress_id=user_progress.id,
                    scene_id=correct_scene_id,
                    message_type="orchestrator",
                    sender_name=persona_name,
                    persona_id=None,
                    message_content=full_response,
                    message_order=next_order + 1,
                    session_id=ai_response_session_id
                )
                self.db.flush()
                
                # Append orchestrator response to conversation cache
                conversation_cache.append_message(
                    user_progress_id=user_progress.id,
                    scene_id=correct_scene_id,
                    message_data={
                        "id": None,
                        "user_progress_id": user_progress.id,
                        "scene_id": correct_scene_id,
                        "message_type": "orchestrator",
                        "sender_name": persona_name,
                        "message_content": full_response,
                        "message_order": next_order + 1,
                        "session_id": ai_response_session_id,
                        "persona_id": None,
                        "created_at": None,
                    }
                )
            
            # NOTE: For @all messages, turn_count is incremented per persona response (line 217)
            # and we already yielded the final metadata per persona (line 227), so we can return early.
            # For single @mention messages, turn_count is incremented when persona responds (line 391)
            # and we already yielded the final metadata (line 479), so we can return early.
            # Only orchestrator messages need to continue to the final yield.
            if is_all_message_global:
                # @all messages: already yielded per persona, no need for final yield
                logger.debug(
                    f"[TURN_COUNT] @all message - turn_count already incremented per persona response, "
                    f"already yielded final metadata per persona, current turn_count={orchestrator.state.turn_count}"
                )
                return
            elif persona_id:
                # Single @mention messages: already yielded final metadata at line 479, no need for final yield
                logger.debug(
                    f"[TURN_COUNT] Single @mention message - turn_count already incremented when persona responded, "
                    f"already yielded final metadata at line 479, current turn_count={orchestrator.state.turn_count}"
                )
                return
            
            # Only orchestrator messages continue here
            # Save orchestrator state (CRITICAL: must save before timeout check)
            orchestrator_manager.save_orchestrator_state(orchestrator, user_progress)
            user_progress.last_activity = datetime.utcnow()
            self.db.commit()
            
            # Check for timeout (uses orchestrator.state.turn_count which was just saved)
            timeout_result = await handle_timeout(
                orchestrator=orchestrator,
                user_progress=user_progress,
                current_scene=current_scene,
                current_scene_id=correct_scene_id,
                full_response=full_response,
                persona_name=persona_name,
                persona_id=persona_id,
                scene_progression_handler=scene_progression_handler,
                orchestrator_manager=orchestrator_manager,
                generate_scene_intro_fn=generate_scene_intro_fn
            )
            
            if timeout_result is not None:
                # Clean up sandbox if simulation completed via timeout
                try:
                    timeout_data = json.loads(timeout_result)
                    if timeout_data.get("simulation_complete") and user_progress.sandbox_id:
                        from common.services.sandbox_service import sandbox_service
                        deleted = await sandbox_service.delete_sandbox(user_progress.sandbox_id)
                        if deleted:
                            user_progress.sandbox_id = None
                            self.db.commit()
                        else:
                            logger.warning(
                                "[DAYTONA] Timeout cleanup could not delete sandbox_id=%s for user_progress_id=%s; keeping ID for retry",
                                user_progress.sandbox_id,
                                user_progress.id,
                            )
                except json.JSONDecodeError:
                    logger.warning(
                        "[DAYTONA] Timeout result was not valid JSON; skipping sandbox cleanup for user_progress_id=%s",
                        user_progress.id,
                    )
                except Exception:
                    logger.exception(
                        "[DAYTONA] Unexpected error during timeout sandbox cleanup for user_progress_id=%s, sandbox_id=%s",
                        user_progress.id,
                        user_progress.sandbox_id,
                    )
                yield f"data: {timeout_result}\n\n"
                return
            
            # Send final metadata (only for orchestrator messages)
            yield f"data: {json.dumps({'done': True, 'persona_name': persona_name, 'persona_id': str(persona_id) if persona_id else None, 'scene_completed': scene_completed, 'next_scene_id': next_scene_id, 'turn_count': orchestrator.state.turn_count, 'full_content': full_response})}\n\n"
            
        except Exception as e:
            # Note: Rollback handled by service layer
            if _is_dev:
                import traceback
                traceback.print_exc()
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
