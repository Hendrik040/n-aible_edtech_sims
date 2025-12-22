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
            mention_match_precheck = re.search(r'@(\w+)', message.lower())
            if mention_match_precheck and mention_match_precheck.group(1).lower() == 'all':
                is_all_message_global = True
            
            # Determine session_id for user message based on @mention target
            # Default to orchestrator session_id, will be updated if @mention targets specific persona
            user_message_session_id = orchestrator.state.session_id if hasattr(orchestrator.state, 'session_id') else None
            
            # Handle @mention
            mention_match = re.search(r'@(\w+)', message.lower())
            if mention_match:
                persona_id_str = mention_match.group(1)
                
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
                        
                        # NOTE: For @all messages, turn_count is incremented per persona response (line 209)
                        # We don't increment here because each persona response counts as a separate turn
                        # This matches the user's expectation that @all messages work correctly
                        logger.debug(
                            f"[TURN_COUNT] @all message saved - turn_count will be incremented per persona response, "
                            f"current turn_count={orchestrator.state.turn_count}"
                        )
                    
                    all_result = await handle_all_mention(
                        orchestrator, message, current_scene, correct_scene_id
                    )
                    ai_response = all_result['ai_response']
                    persona_name = all_result['persona_name']
                    persona_id = all_result['persona_id']
                    all_responses = all_result.get('responses', [])
                    scene_personas_count = all_result.get('personas_count', 0)
                    is_all_message_global = bool(all_responses)
                    
                    # Stream each persona's response separately
                    if all_responses:
                        # Ensure next_order is defined (should be set when user message was saved)
                        if 'next_order' not in locals():
                            next_order = self.repository.get_next_message_order(user_progress_id)
                        current_order = next_order + 1
                        for resp_data in all_responses:
                            persona_resp = resp_data['response']
                            persona_name_resp = resp_data['persona_name']
                            persona_id_resp = resp_data['persona_id']
                            
                            orchestrator.state.turn_count += 1
                            current_turn_count = orchestrator.state.turn_count
                            
                            # Stream this persona's response
                            persona_full_response = ""
                            for char in persona_resp:
                                persona_full_response += char
                                yield f"data: {json.dumps({'content': char, 'done': False, 'persona_name': persona_name_resp, 'persona_id': str(persona_id_resp) if persona_id_resp else None})}\n\n"
                                await asyncio.sleep(0.03)
                            
                            yield f"data: {json.dumps({'done': True, 'persona_name': persona_name_resp, 'persona_id': str(persona_id_resp) if persona_id_resp else None, 'scene_completed': False, 'next_scene_id': None, 'turn_count': current_turn_count, 'full_content': persona_full_response})}\n\n"
                            
                            # Save persona response
                            self.repository.create_conversation_log(
                                user_progress_id=user_progress.id,
                                scene_id=correct_scene_id,
                                message_type="ai_persona",
                                sender_name=persona_name_resp,
                                persona_id=persona_id_resp,
                                message_content=persona_resp,
                                message_order=current_order,
                                session_id=orchestrator.state.session_id if hasattr(orchestrator.state, 'session_id') else None
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
                            first_name = name.split()[0]
                            name_mapping[first_name] = persona['id']
                            name_mapping[first_name.replace("'", "")] = persona['id']

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
                                    
                                    # CRITICAL: Increment turn_count when user sends message (not when persona responds)
                                    # This ensures user messages count toward timeout turns
                                    turn_count_before = orchestrator.state.turn_count
                                    orchestrator.state.turn_count += 1
                                    logger.info(
                                        f"[TURN_COUNT] Incremented turn_count from {turn_count_before} to {orchestrator.state.turn_count} "
                                        f"for user message (user_progress_id={user_progress_id}, message='{message[:50]}...')"
                                    )
                                    # Save orchestrator state immediately after incrementing turn_count
                                    orchestrator_manager.save_orchestrator_state(orchestrator, user_progress)
                                    # CRITICAL: Commit immediately to persist turn_count (not just flush)
                                    # This ensures turn_count is saved even if later processing fails
                                    self.db.commit()
                                    logger.debug(
                                        f"[TURN_COUNT] Committed turn_count={orchestrator.state.turn_count} "
                                        f"for user_progress_id={user_progress_id}"
                                    )
                                
                                scene_context = {
                                    'id': current_scene.get('id'),
                                    'title': current_scene.get('title'),
                                    'description': current_scene.get('description'),
                                    'objectives': current_scene.get('objectives', [])
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
                                        # Get full response and stream it character by character
                                        # Note: AgentExecutor doesn't support true streaming, so we get the response
                                        # and stream it character-by-character to create the streaming effect
                                        try:
                                            logger.info(
                                                f"[PERSONA_CHAT] Starting persona chat: persona={persona_name} "
                                                f"(persona_id={persona_id}), user_progress_id={user_progress_id}, "
                                                f"message='{message[:100]}...'"
                                            )
                                            response_text = await persona_agent.chat(
                                                message=message,
                                                scene_context=scene_context,
                                                user_progress_id=orchestrator.user_progress_id,
                                                scene_id=correct_scene_id,
                                                db=self.db,
                                            )
                                            if not response_text or len(response_text.strip()) == 0:
                                                logger.warning(
                                                    f"[PERSONA_CHAT] Persona {persona_name} returned empty response "
                                                    f"for user_progress_id={user_progress_id}"
                                                )
                                                response_text = "I'm sorry, I didn't understand that. Could you rephrase?"
                                            
                                            logger.info(
                                                f"[PERSONA_CHAT] Persona {persona_name} responded with {len(response_text)} chars "
                                                f"for user_progress_id={user_progress_id}"
                                            )
                                            
                                            # CRITICAL: Save persona response directly as fallback
                                            # PersonaCallbackHandler should save it, but if callbacks aren't working,
                                            # we need to save it here to ensure it's persisted
                                            try:
                                                # Check if response was already saved by checking recent logs
                                                from common.db.models import ConversationLog
                                                from sqlalchemy import func
                                                
                                                # Get the most recent persona log for this user_progress_id
                                                recent_persona_log = self.db.query(ConversationLog).filter(
                                                    ConversationLog.user_progress_id == user_progress_id,
                                                    ConversationLog.persona_id == persona_id,
                                                    ConversationLog.message_type == "ai_persona"
                                                ).order_by(ConversationLog.message_order.desc()).first()
                                                
                                                # If no recent persona log or the content doesn't match, save it
                                                if not recent_persona_log or recent_persona_log.message_content != response_text:
                                                    logger.info(
                                                        f"[PERSONA_CHAT] PersonaCallbackHandler may not have saved response. "
                                                        f"Saving directly as fallback: persona_id={persona_id}, "
                                                        f"user_progress_id={user_progress_id}"
                                                    )
                                                    
                                                    # Get next message order
                                                    max_order = self.db.query(func.max(ConversationLog.message_order)).filter(
                                                        ConversationLog.user_progress_id == user_progress_id
                                                    ).scalar()
                                                    next_order = (max_order + 1) if max_order is not None else 1
                                                    
                                                    # Use persona's session_id (from persona_agent if available)
                                                    persona_session_id = None
                                                    if hasattr(persona_agent, 'persona_session_id'):
                                                        persona_session_id = persona_agent.persona_session_id
                                                    elif hasattr(orchestrator.state, 'session_id'):
                                                        persona_session_id = orchestrator.state.session_id
                                                    
                                                    # Save persona response
                                                    self.repository.create_conversation_log(
                                                        user_progress_id=user_progress.id,
                                                        scene_id=correct_scene_id,
                                                        message_type="ai_persona",
                                                        sender_name=persona_name,
                                                        persona_id=persona_id,
                                                        message_content=response_text,
                                                        message_order=next_order,
                                                        session_id=persona_session_id
                                                    )
                                                    self.db.commit()
                                                    logger.info(
                                                        f"[PERSONA_CHAT] ✓ Saved persona response directly: "
                                                        f"persona_id={persona_id}, user_progress_id={user_progress_id}, "
                                                        f"message_order={next_order}, session_id={persona_session_id}"
                                                    )
                                                else:
                                                    logger.debug(
                                                        f"[PERSONA_CHAT] Persona response already saved by callback "
                                                        f"(found matching log with order={recent_persona_log.message_order})"
                                                    )
                                            except Exception as e:
                                                logger.error(
                                                    f"[PERSONA_CHAT] Failed to save persona response as fallback: {e}",
                                                    exc_info=True
                                                )
                                                # Continue anyway - don't block streaming
                                            
                                            # Stream the response character by character with a delay
                                            # This creates the streaming effect even though we have the full response
                                            for char in response_text:
                                                full_response += char
                                                yield f"data: {json.dumps({'content': char, 'done': False, 'persona_name': persona_name, 'persona_id': str(persona_id) if persona_id else None})}\n\n"
                                                await asyncio.sleep(0.02)  # 20ms delay per character for visible streaming
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
                if not is_command and not mention_match:
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
            
            # Save AI response to database (only if not @all)
            # NOTE: For persona responses, PersonaCallbackHandler already saves and commits
            # the response immediately when the LLM finishes. We only need to save here for
            # orchestrator responses (non-persona messages).
            if not is_all_message_global:
                # Only save if this is NOT a persona response (persona responses are saved by callback handler)
                if not persona_id:
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
            
            # NOTE: turn_count is now incremented when user messages are saved (lines 320-330 for @mention, 
            # lines 436-445 for orchestrator messages). For @all messages, turn_count is incremented 
            # per persona response (line 209). We don't need to increment here anymore.
            # However, we still need to ensure orchestrator state is saved before timeout check.
            if is_all_message_global:
                logger.debug(
                    f"[TURN_COUNT] @all message - turn_count already incremented per persona response at line 209, "
                    f"current turn_count={orchestrator.state.turn_count}"
                )
            else:
                # For single @mention and orchestrator messages, turn_count was already incremented
                # when the user message was saved. Just log the current state.
                logger.debug(
                    f"[TURN_COUNT] Single @mention or orchestrator message - turn_count already incremented "
                    f"when user message was saved, current turn_count={orchestrator.state.turn_count}"
                )
            
            # Save orchestrator state (CRITICAL: must save before timeout check)
            # Note: turn_count was already saved when user message was saved, but we save again
            # here to ensure any other state changes (like turn_count from @all) are persisted
            orchestrator_manager.save_orchestrator_state(orchestrator, user_progress)
            user_progress.last_activity = datetime.utcnow()
            # CRITICAL: For direct processing, we need to commit here to ensure state is persisted
            # For queued processing, the worker will commit. But for direct processing, if we only flush,
            # the state might not be visible to the final commit in service.py due to transaction isolation.
            # However, we already committed turn_count earlier, so we just flush here and let service.py commit.
            self.db.flush()
            
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
                yield f"data: {timeout_result}\n\n"
                return
            
            # Send final metadata
            yield f"data: {json.dumps({'done': True, 'persona_name': persona_name, 'persona_id': str(persona_id) if persona_id else None, 'scene_completed': scene_completed, 'next_scene_id': next_scene_id, 'turn_count': orchestrator.state.turn_count, 'full_content': full_response})}\n\n"
            
        except Exception as e:
            # Note: Rollback handled by service layer
            if _is_dev:
                import traceback
                traceback.print_exc()
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
