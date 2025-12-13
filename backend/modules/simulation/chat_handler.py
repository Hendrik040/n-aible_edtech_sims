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

from modules.simulation.repository import SimulationRepository
from modules.simulation.orchestrator import ChatOrchestrator
from modules.simulation.orchestrator_manager import OrchestratorManager
from modules.simulation.scene_progression import SceneProgressionHandler
from common.db.models import UserProgress
from common.config import get_settings

settings = get_settings()
_is_dev = settings.environment != "production"


class ChatHandler:
    """Handles chat streaming and message processing."""
    
    def __init__(self, db: Session, repository: SimulationRepository):
        self.db = db
        self.repository = repository
    
    async def handle_begin_command(
        self,
        orchestrator: ChatOrchestrator,
        user_progress: UserProgress,
        message: str,
        current_scene: Dict[str, Any],
        generate_scene_intro_fn: callable
    ) -> AsyncGenerator[str, None]:
        """
        Handle the "begin" command.
        
        Args:
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
        last_msg = self.repository.get_last_conversation_log(user_progress.id)
        begin_order = (last_msg.message_order + 1) if last_msg else 1
        
        orchestrator.state.simulation_started = True
        orchestrator.state.user_ready = True
        user_progress.simulation_status = "in_progress"
        
        # Save orchestrator state
        orchestrator_manager = OrchestratorManager(self.db, self.repository)
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
        self.repository.create_conversation_log(
            user_progress_id=user_progress.id,
            scene_id=user_progress.current_scene_id,
            message_type="orchestrator",
            sender_name="ChatOrchestrator",
            message_content=welcome_msg,
            message_order=begin_order + 1
        )
        
        # Save scene intro message
        self.repository.create_conversation_log(
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
    
    async def handle_all_mention(
        self,
        orchestrator: ChatOrchestrator,
        message: str,
        current_scene: Dict[str, Any],
        scene_id: int
    ) -> Dict[str, Any]:
        """
        Handle @all mention - get responses from all personas in scene.
        
        Args:
            orchestrator: ChatOrchestrator instance
            message: User message with @all
            current_scene: Current scene data
            scene_id: Current scene ID
            
        Returns:
            Dictionary with responses list and persona count
        """
        personas_involved = current_scene.get('personas_involved', [])
        scene_personas = []
        
        for persona in orchestrator.simulation.get('personas', []):
            persona_name = persona['identity']['name']
            if persona_name in personas_involved:
                scene_personas.append(persona)
        
        if not scene_personas:
            return {
                'ai_response': "There are no personas available in this scene to respond to your @all message.",
                'persona_name': "ChatOrchestrator",
                'persona_id': None,
                'responses': []
            }
        
        # Execute all persona responses in parallel
        if orchestrator.langchain_enabled:
            try:
                tasks = []
                for persona in scene_personas:
                    persona_db_id = persona.get('db_id')
                    persona_simulation_id = persona.get('id')
                    if persona_db_id and persona_simulation_id:
                        tasks.append(
                            orchestrator.chat_with_persona_langchain(
                                message=message,
                                persona_id=persona_simulation_id,
                                scene_id=scene_id
                            )
                        )
                
                responses = await asyncio.gather(*tasks, return_exceptions=True)
                
                all_responses = []
                for i, response in enumerate(responses):
                    if isinstance(response, Exception):
                        all_responses.append({
                            'persona_name': scene_personas[i]['identity']['name'],
                            'persona_id': scene_personas[i].get('db_id'),
                            'response': f"I'm sorry, I'm having trouble processing that right now."
                        })
                    else:
                        all_responses.append({
                            'persona_name': scene_personas[i]['identity']['name'],
                            'persona_id': scene_personas[i].get('db_id'),
                            'response': response
                        })
                
                return {
                    'ai_response': "",  # Will be handled separately
                    'persona_name': "All Personas",
                    'persona_id': None,
                    'responses': all_responses,
                    'personas_count': len(scene_personas)
                }
            except Exception as e:
                if _is_dev:
                    import traceback
                    traceback.print_exc()
                return {
                    'ai_response': f"I'm sorry, I'm having trouble processing the @all message right now. Please try again.",
                    'persona_name': "ChatOrchestrator",
                    'persona_id': None,
                    'responses': []
                }
        else:
            return {
                'ai_response': f"I'm sorry, the @all feature requires LangChain integration which is not available right now.",
                'persona_name': "ChatOrchestrator",
                'persona_id': None,
                'responses': []
            }
    
    async def handle_mention(
        self,
        orchestrator: ChatOrchestrator,
        message: str,
        persona_id: str,
        scene_id: int
    ) -> Dict[str, Any]:
        """
        Handle @mention to a specific persona.
        
        Args:
            orchestrator: ChatOrchestrator instance
            message: User message with @mention
            persona_id: Mentioned persona ID (from regex)
            scene_id: Current scene ID
            
        Returns:
            Dictionary with ai_response, persona_name, persona_id
        """
        # Build name mapping for persona lookup
        name_mapping = {}
        for persona in orchestrator.simulation.get('personas', []):
            name = persona['identity']['name'].lower()
            name_mapping[name] = persona['id']
            name_mapping[name.replace("'", "").replace(" ", "_")] = persona['id']
            name_mapping[name.replace("'", "").replace(" ", "")] = persona['id']
            first_name = name.split()[0]
            name_mapping[first_name] = persona['id']
            name_mapping[first_name.replace("'", "")] = persona['id']
        
        search_name = persona_id.lower()
        target_persona = None
        
        if search_name in name_mapping:
            persona_id = name_mapping[search_name]
            target_persona = next((p for p in orchestrator.simulation.get('personas', []) if p['id'] == persona_id), None)
        else:
            # Try fuzzy matching
            for name, pid in name_mapping.items():
                if (search_name in name or name in search_name or
                    search_name.replace("'", "").replace("_", "") in name.replace("'", "").replace("_", "")):
                    persona_id = pid
                    target_persona = next((p for p in orchestrator.simulation.get('personas', []) if p['id'] == persona_id), None)
                    break
        
        if target_persona:
            if orchestrator.langchain_enabled:
                try:
                    ai_response = await orchestrator.chat_with_persona_langchain(
                        message=message,
                        persona_id=persona_id,
                        scene_id=scene_id
                    )
                    return {
                        'ai_response': ai_response,
                        'persona_name': target_persona['identity']['name'],
                        'persona_id': target_persona.get('db_id')
                    }
                except Exception as e:
                    import logging
                    import traceback
                    logger = logging.getLogger(__name__)
                    error_msg = str(e)
                    logger.error(f"Error in chat_with_persona_langchain for persona {persona_id}: {error_msg}")
                    if _is_dev:
                        traceback.print_exc()
                    return {
                        'ai_response': f"I'm sorry, I'm having trouble processing that right now. Please try again or ask the orchestrator for help. (Error: {error_msg})",
                        'persona_name': "ChatOrchestrator",
                        'persona_id': None
                    }
            else:
                return {
                    'ai_response': f"I'm sorry, the persona interaction system is not available right now. Please try again later.",
                    'persona_name': "ChatOrchestrator",
                    'persona_id': None
                }
        else:
            return {
                'ai_response': f"I don't recognize that persona. Available team members: {', '.join([p['id'] for p in orchestrator.simulation.get('personas', [])])}. Please use @mentions to talk to specific team members.",
                'persona_name': "ChatOrchestrator",
                'persona_id': None
            }
    
    async def handle_timeout(
        self,
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
            await orchestrator_manager.initialize_langchain_session(orchestrator, user_progress.id)
            
            # Load saved state
            orchestrator_manager.load_orchestrator_state(orchestrator, user_progress)
            
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
                async for chunk in self.handle_begin_command(
                    orchestrator, user_progress, message, current_scene, generate_scene_intro_fn
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
            
            # Only save user messages if they're not command words
            # Commands (begin, help) should not be stored in database or used in grading
            if not is_command:
                last_msg = self.repository.get_last_conversation_log(user_progress_id)
                next_order = (last_msg.message_order + 1) if last_msg else 1
                
                self.repository.create_conversation_log(
                    user_progress_id=user_progress.id,
                    scene_id=correct_scene_id,
                    message_type="user",
                    sender_name="User",
                    message_content=message,
                    message_order=next_order
                )
                self.db.flush()
            
            # Increment turn count (only for non-command messages)
            if not is_command and not is_all_message_global:
                orchestrator.state.turn_count += 1
            
            # Handle @mention
            mention_match = re.search(r'@(\w+)', message.lower())
            if mention_match:
                persona_id_str = mention_match.group(1)
                
                if persona_id_str.lower() == 'all':
                    # Handle @all
                    all_result = await self.handle_all_mention(
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
                                message_order=current_order
                            )
                            current_order += 1
                        
                        ai_response = ""  # Already streamed
                else:
                    # Handle single @mention - stream directly from agent
                    target_persona = None
                    # Build name mapping for persona lookup
                    name_mapping = {}
                    for persona in orchestrator.simulation.get('personas', []):
                        name = persona['identity']['name'].lower()
                        name_mapping[name] = persona['id']
                        name_mapping[name.replace("'", "").replace(" ", "_")] = persona['id']
                        name_mapping[name.replace("'", "").replace(" ", "")] = persona['id']
                        first_name = name.split()[0]
                        name_mapping[first_name] = persona['id']
                        name_mapping[first_name.replace("'", "")] = persona['id']
                    
                    search_name = persona_id_str.lower()
                    if search_name in name_mapping:
                        persona_simulation_id = name_mapping[search_name]
                        target_persona = next((p for p in orchestrator.simulation.get('personas', []) if p['id'] == persona_simulation_id), None)
                    else:
                        # Try fuzzy matching
                        for name, pid in name_mapping.items():
                            if (search_name in name or name in search_name or
                                search_name.replace("'", "").replace("_", "") in name.replace("'", "").replace("_", "")):
                                persona_simulation_id = pid
                                target_persona = next((p for p in orchestrator.simulation.get('personas', []) if p['id'] == persona_simulation_id), None)
                                break
                    
                    if target_persona and orchestrator.langchain_enabled:
                        try:
                            # Stream response directly from agent
                            persona_name = target_persona['identity']['name']
                            persona_id = target_persona.get('db_id')
                            current_scene = orchestrator.simulation.get('scenes', [{}])[orchestrator.state.current_scene_index]
                            
                            # Get persona agent and stream its response
                            if str(persona_simulation_id) in orchestrator.persona_agents:
                                persona_agent = orchestrator.persona_agents[str(persona_simulation_id)]
                                scene_context = {
                                    'id': current_scene.get('id'),
                                    'title': current_scene.get('title'),
                                    'description': current_scene.get('description'),
                                    'objectives': current_scene.get('objectives', [])
                                }
                                
                                # Get full response and stream it character by character
                                # Note: AgentExecutor doesn't support true streaming, so we get the response
                                # and stream it character-by-character to create the streaming effect
                                try:
                                    response_text = await persona_agent.chat(
                                        message=message,
                                        scene_context=scene_context,
                                        user_progress_id=orchestrator.user_progress_id,
                                        scene_id=correct_scene_id
                                    )
                                    # Stream the response character by character with a delay
                                    # This creates the streaming effect even though we have the full response
                                    for char in response_text:
                                        full_response += char
                                        yield f"data: {json.dumps({'content': char, 'done': False, 'persona_name': persona_name, 'persona_id': str(persona_id) if persona_id else None})}\n\n"
                                        await asyncio.sleep(0.02)  # 20ms delay per character for visible streaming
                                except Exception as e:
                                    import traceback
                                    import logging
                                    logger = logging.getLogger(__name__)
                                    error_msg = str(e)
                                    logger.error(f"Error in persona chat: {error_msg}")
                                    if _is_dev:
                                        traceback.print_exc()
                                    ai_response = f"I'm sorry, I'm having trouble processing that right now. Please try again."
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
                            import logging
                            import traceback
                            logger = logging.getLogger(__name__)
                            error_msg = str(e)
                            logger.error(f"Error streaming persona response for persona {persona_simulation_id}: {error_msg}")
                            if _is_dev:
                                traceback.print_exc()
                            ai_response = f"I'm sorry, I'm having trouble processing that right now. Please try again or ask the orchestrator for help."
                            persona_name = "ChatOrchestrator"
                            persona_id = None
                            for char in ai_response:
                                full_response += char
                                yield f"data: {json.dumps({'content': char, 'done': False, 'persona_name': persona_name, 'persona_id': None})}\n\n"
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
                ai_response = "I'm here to help guide your business simulation. Use @mentions to talk to specific team members or ask me for strategic guidance."
                persona_name = "ChatOrchestrator"
                persona_id = None
                for char in ai_response:
                    full_response += char
                    yield f"data: {json.dumps({'content': char, 'done': False, 'persona_name': persona_name, 'persona_id': None})}\n\n"
                    await asyncio.sleep(0.03)
            
            # Save AI response to database (only if not @all)
            if not is_all_message_global:
                self.repository.create_conversation_log(
                    user_progress_id=user_progress.id,
                    scene_id=correct_scene_id,
                    message_type="ai_persona" if persona_id else "orchestrator",
                    sender_name=persona_name,
                    persona_id=persona_id,
                    message_content=full_response,
                    message_order=next_order + 1
                )
                self.db.flush()
            
            # Save orchestrator state
            orchestrator_manager.save_orchestrator_state(orchestrator, user_progress)
            user_progress.last_activity = datetime.utcnow()
            # Note: Commit handled by service layer
            
            # Check for timeout
            timeout_result = await self.handle_timeout(
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

