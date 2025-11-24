"""
Simulation Orchestrator API
Handles orchestrated chat interactions with streaming 
Allows interaction with personas 
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from typing import Dict, Any
import json
import asyncio
from datetime import datetime
import re

from database.connection import get_db, settings

# Helper to check if we're in development
_is_dev = getattr(settings, "environment", "development") != "production"
from database.models import (
    User,
    UserProgress,
    SceneProgress,
    ConversationLog,
)
from common.utils.auth import get_current_user
from database.schemas import SimulationChatRequest
from .chat_orchestrator import ChatOrchestrator

# Create router for orchestrator endpoints
orchestrator_router = APIRouter()


@orchestrator_router.post("/linear-chat-stream")
async def linear_simulation_chat_stream(
    request: SimulationChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Handle orchestrated chat interactions with streaming responses"""
    
    async def generate_stream(db_session: Session):
        """Generator function for streaming OpenAI responses"""
        # Import ChatOrchestrator at the top of the function
        from modules.simulation.chat_orchestrator import ChatOrchestrator
        
        # logging removed
        scene_completed = False
        next_scene_id = None
        timeout_turns = 15
        scene_intro_message = None
        full_response = ""
        
        try:
            # Get user progress
            if not request.user_progress_id:
                yield f"data: {json.dumps({'error': 'user_progress_id is required'})}\n\n"
                return
            
            user_progress = db_session.query(UserProgress).filter(
                UserProgress.id == request.user_progress_id
            ).first()
            
            if not user_progress:
                yield f"data: {json.dumps({'error': 'User progress not found'})}\n\n"
                return
            
            # Verify ownership
            if user_progress.user_id != current_user.id:
                yield f"data: {json.dumps({'error': 'Access denied'})}\n\n"
                return
            
            if not user_progress.orchestrator_data:
                yield f"data: {json.dumps({'error': 'Simulation not properly initialized'})}\n\n"
                return
            
            # Initialize orchestrator with LangChain enabled
            # Check if this is a professor test simulation
            is_professor_test = current_user.role in ['professor', 'admin']
            orchestrator = ChatOrchestrator(user_progress.orchestrator_data, enable_langchain=True, is_professor_test=is_professor_test)
            orchestrator.user_progress_id = user_progress.id
            
            # Initialize LangChain session if not already done
            if orchestrator.langchain_enabled and not orchestrator.state.scene_memory_initialized:
                await orchestrator.initialize_langchain_session(user_progress.id)
            
            # Load saved state
            if user_progress.orchestrator_data and 'state' in user_progress.orchestrator_data:
                saved_state = user_progress.orchestrator_data['state']
                orchestrator.state.simulation_started = saved_state.get('simulation_started', False)
                orchestrator.state.user_ready = saved_state.get('user_ready', False)
                orchestrator.state.current_scene_index = saved_state.get('current_scene_index', 0)
                orchestrator.state.turn_count = saved_state.get('turn_count', 0)
                orchestrator.state.state_variables = saved_state.get('state_variables', {})
            
            # Professor test simulations will only clear conversation history on scene transitions
            # This preserves context within the same test session until the user moves to a new scene
            if current_user.role in ['professor', 'admin'] and user_progress.user_id == current_user.id and orchestrator.langchain_enabled:
                print("Professor test simulation detected - conversation history will be cleared on scene transitions only")
            
            # Check if this is a new scene (scene transition) and clear conversation history
            # This ensures each scene starts with fresh conversation context
            if orchestrator.langchain_enabled:
                # Initialize _last_scene_id if not set
                if not hasattr(orchestrator, '_last_scene_id'):
                    orchestrator._last_scene_id = None
                
                # Initialize current_scene_id from user progress if not set
                if _is_dev:
                    print(f"[DEBUG] Before initialization - orchestrator.state.current_scene_id: {getattr(orchestrator.state, 'current_scene_id', 'NOT_SET')}")
                    print(f"[DEBUG] user_progress.current_scene_id: {user_progress.current_scene_id}")
                if not hasattr(orchestrator.state, 'current_scene_id') or orchestrator.state.current_scene_id is None or orchestrator.state.current_scene_id == "":
                    orchestrator.state.current_scene_id = user_progress.current_scene_id
                    if _is_dev:
                        print(f"[DEBUG] Initialized orchestrator.state.current_scene_id from user_progress: {orchestrator.state.current_scene_id}")
                else:
                    if _is_dev:
                        print(f"[DEBUG] orchestrator.state.current_scene_id already set to: {orchestrator.state.current_scene_id}")
                
                # Check if we're in a different scene than before
                current_scene_id = orchestrator.state.current_scene_id
                if _is_dev:
                    print(f"[DEBUG] Scene transition check - _last_scene_id: {orchestrator._last_scene_id}, current_scene_id: {current_scene_id}")
                
                # Clear conversation history on scene transitions
                if orchestrator._last_scene_id is not None and orchestrator._last_scene_id != current_scene_id:
                    if _is_dev:
                        print(f"Scene transition detected: {orchestrator._last_scene_id} -> {current_scene_id}")
                        print("Scene transition detected - clearing conversation history for new scene")
                    
                    # Clear conversation history for all existing persona agents
                    if hasattr(orchestrator, 'persona_agents') and orchestrator.persona_agents:
                        if _is_dev:
                            print(f"[DEBUG] Found {len(orchestrator.persona_agents)} existing persona agents to clear")
                        for persona_id, agent in orchestrator.persona_agents.items():
                            if _is_dev:
                                print(f"[DEBUG] Clearing conversation history for existing agent: {persona_id}")
                            agent.clear_conversation_history(user_progress.id)
                            if _is_dev:
                                print(f"Cleared conversation history for existing persona agent: {persona_id}")
                elif orchestrator._last_scene_id is None:
                    if _is_dev:
                        print(f"[DEBUG] First time setting _last_scene_id to: {current_scene_id}")
                
                # Store current scene ID for next comparison
                orchestrator._last_scene_id = current_scene_id
            
            current_scene = orchestrator.scenario.get('scenes', [{}])[orchestrator.state.current_scene_index]
            timeout_turns = current_scene.get('timeout_turns') or current_scene.get('max_turns', 15)
            correct_scene_id = current_scene.get('id')
            
            # Handle "begin" command
            if request.message.lower().strip() == "begin":
                # Check if simulation is already started - if so, ignore the begin command
                if orchestrator.state.simulation_started:
                    if _is_dev:
                        print(f"[STREAM DEBUG] Simulation already started, ignoring 'begin' command")
                    # Return a message saying simulation is already running
                    already_started_msg = "The simulation is already in progress. You can continue interacting with the personas."
                    for char in already_started_msg:
                        yield f"data: {json.dumps({'content': char, 'done': False})}\n\n"
                        await asyncio.sleep(0.03)
                    yield f"data: {json.dumps({'done': True, 'persona_name': 'ChatOrchestrator', 'persona_id': None, 'scene_completed': False, 'next_scene_id': None, 'turn_count': orchestrator.state.turn_count, 'full_content': already_started_msg})}\n\n"
                    return
                
                last_msg = db_session.query(ConversationLog).filter(
                    ConversationLog.user_progress_id == user_progress.id
                ).order_by(desc(ConversationLog.message_order)).first()
                begin_order = (last_msg.message_order + 1) if last_msg else 1
                
                begin_user_log = ConversationLog(
                    user_progress_id=user_progress.id,
                    scene_id=user_progress.current_scene_id,
                    message_type="user",
                    sender_name="User",
                    message_content=request.message,
                    message_order=begin_order,
                    timestamp=datetime.utcnow()
                )
                db_session.add(begin_user_log)
                db_session.flush()
                
                orchestrator.state.simulation_started = True
                orchestrator.state.user_ready = True
                user_progress.simulation_status = "in_progress"
                
                # Save orchestrator state
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
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(user_progress, "orchestrator_data")
                db_session.commit()
                if _is_dev:
                    print(f"[STREAM DEBUG] Saved state after begin - simulation_started: {state_dict['simulation_started']}, simulation_status: {user_progress.simulation_status}")
                
                # Generate scene intro message
                from .simulation import generate_scene_intro_message
                scene_intro_message = generate_scene_intro_message(current_scene)
                
                # Stream welcome message with natural typing speed
                welcome_msg = "🎬 **Simulation Started!**\n\nThe simulation has begun. You can now interact with the personas in this scene."
                for char in welcome_msg:
                    full_response += char
                    yield f"data: {json.dumps({'content': char, 'done': False})}\n\n"
                    await asyncio.sleep(0.03)  
                
                # Save the welcome message to database so it appears on resume
                welcome_log = ConversationLog(
                    user_progress_id=user_progress.id,
                    scene_id=user_progress.current_scene_id,
                    message_type="orchestrator",
                    sender_name="ChatOrchestrator",
                    message_content=welcome_msg,
                    message_order=begin_order + 1,
                    timestamp=datetime.utcnow()
                )
                db_session.add(welcome_log)
                if _is_dev:
                    print(f"[STREAM DEBUG] Saved welcome message: order={begin_order + 1}")
                
                # Save scene intro message to database
                scene_intro_log = ConversationLog(
                    user_progress_id=user_progress.id,
                    scene_id=user_progress.current_scene_id,
                    message_type="system",
                    sender_name="System",
                    message_content=scene_intro_message,
                    message_order=begin_order + 2,
                    timestamp=datetime.utcnow()
                )
                db_session.add(scene_intro_log)
                db_session.commit()
                if _is_dev:
                    print(f"[STREAM DEBUG] Saved scene intro message: order={begin_order + 2}")
                
                # Send metadata
                yield f"data: {json.dumps({'done': True, 'persona_name': 'ChatOrchestrator', 'persona_id': None, 'scene_completed': False, 'next_scene_id': None, 'turn_count': 0, 'scene_intro_message': scene_intro_message, 'full_content': full_response})}\n\n"
                return
            
            # Initialize variables before they're used
            is_all_message_global = False
            scene_personas_count = 0
            ai_response = ""
            persona_name = "ChatOrchestrator"
            persona_id = None
            
            # Check if this is an @all message early (before saving user message)
            mention_match_precheck = re.search(r'@(\w+)', request.message.lower())
            if mention_match_precheck and mention_match_precheck.group(1).lower() == 'all':
                is_all_message_global = True
            
            # Save user message
            next_order = 1
            last_msg = db_session.query(ConversationLog).filter(
                ConversationLog.user_progress_id == user_progress.id
            ).order_by(desc(ConversationLog.message_order)).first()
            next_order = (last_msg.message_order + 1) if last_msg else 1
            
            user_log = ConversationLog(
                user_progress_id=user_progress.id,
                scene_id=correct_scene_id,
                message_type="user",
                sender_name="User",
                message_content=request.message,
                message_order=next_order,
                timestamp=datetime.utcnow()
            )
            db_session.add(user_log)
            db_session.flush()
            if _is_dev:
                print(f"[STREAM] User msg saved: order={next_order}, scene_id={correct_scene_id}")
            
            # Note: Turn count increment is handled differently for @all vs regular messages
            # @all increments by number of personas during @all handling above
            # Regular messages increment by 1 here
            # "begin" and "help" don't increment turn count
            if request.message.lower().strip() not in ["begin", "help"]:
                if not is_all_message_global:
                    # Regular message - increment by 1
                    orchestrator.state.turn_count += 1
                # else: @all already incremented by number of personas
            
            # Get conversation history
            conversation_logs = db_session.query(ConversationLog).filter(
                ConversationLog.user_progress_id == user_progress.id
            ).order_by(ConversationLog.message_order).all()
            
            conversation_context = []
            for log in conversation_logs[-20:]:  # Last 20 messages
                if log.message_type == "user":
                    conversation_context.append({"role": "user", "content": log.message_content})
                elif log.message_type in ["ai_persona", "system", "orchestrator"]:
                    conversation_context.append({"role": "assistant", "content": log.message_content})
            
            # Determine which persona to respond using LangChain integration
            # Note: persona_name, persona_id, ai_response are already initialized above
            
            # Memory context for any response
            memory_context = ""
            if hasattr(orchestrator, 'memory_service') and orchestrator.memory_service:
                relevant_memories = orchestrator.memory_service.retrieve_relevant_context(
                    request.message, scene_id=correct_scene_id
                )
                if relevant_memories:
                    memory_context = "\n\n**Relevant Context from Previous Interactions:**\n" + "\n".join(
                        [f"- {mem['content']}" for mem in relevant_memories[:3]]
                    )
            
            # Check for @mention in the message
            prompt_locked = False
            mention_match = re.search(r'@(\w+)', request.message.lower())
            # logging removed
            
            # Note: is_all_message_global, scene_personas_count, ai_response, persona_name, persona_id
            # are already initialized above before saving user message
            
            if mention_match:
                persona_id = mention_match.group(1)
                
                # Handle @all special case
                if persona_id.lower() == 'all':
                    is_all_message_global = True
                    # Get all personas in the current scene
                    personas_involved = current_scene.get('personas_involved', [])
                    scene_personas = []
                    
                    # Filter personas that are in the current scene
                    for persona in orchestrator.scenario.get('personas', []):
                        persona_name = persona['identity']['name']
                        # Check if persona is involved in this scene
                        if persona_name in personas_involved:
                            scene_personas.append(persona)
                    
                    if not scene_personas:
                        # No personas in scene
                        ai_response = "There are no personas available in this scene to respond to your @all message."
                        persona_name = "ChatOrchestrator"
                        persona_id = None
                    else:
                        # Execute all persona responses in parallel
                        if orchestrator.langchain_enabled:
                            try:
                                # Create tasks for all personas
                                tasks = []
                                for persona in scene_personas:
                                    persona_db_id = persona.get('db_id')
                                    persona_scenario_id = persona.get('id')
                                    if persona_db_id and persona_scenario_id:
                                        tasks.append(
                                            orchestrator.chat_with_persona_langchain(
                                                message=request.message,
                                                persona_id=persona_scenario_id,
                                                scene_id=correct_scene_id
                                            )
                                        )
                                
                                # Execute all tasks in parallel
                                responses = await asyncio.gather(*tasks, return_exceptions=True)
                                
                                # Collect successful responses
                                all_responses = []
                                for i, response in enumerate(responses):
                                    if isinstance(response, Exception):
                                        print(f"Error getting response from persona {scene_personas[i]['identity']['name']}: {response}")
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
                                
                                # Stream each persona's response separately as its own message bubble
                                # Each persona gets their own complete message with streaming
                                current_order = next_order + 1
                                scene_personas_count = len(scene_personas)
                                
                                # Track the starting turn count (before incrementing)
                                starting_turn_count = orchestrator.state.turn_count
                                
                                # Save each persona's response separately to database and stream them
                                for idx, resp_data in enumerate(all_responses):
                                    persona_resp = resp_data['response']
                                    persona_name_resp = resp_data['persona_name']
                                    persona_id_resp = resp_data['persona_id']
                                    
                                    # Increment turn count for this persona (one turn per persona response)
                                    orchestrator.state.turn_count += 1
                                    current_turn_count = orchestrator.state.turn_count
                                    
                                    # Stream this persona's response character by character
                                    persona_full_response = ""
                                    for char in persona_resp:
                                        persona_full_response += char
                                        yield f"data: {json.dumps({'content': char, 'done': False, 'persona_name': persona_name_resp, 'persona_id': str(persona_id_resp) if persona_id_resp else None})}\n\n"
                                        await asyncio.sleep(0.03)
                                    
                                    # Send done message for this persona with updated turn count
                                    yield f"data: {json.dumps({'done': True, 'persona_name': persona_name_resp, 'persona_id': str(persona_id_resp) if persona_id_resp else None, 'scene_completed': False, 'next_scene_id': None, 'turn_count': current_turn_count, 'full_content': persona_full_response})}\n\n"
                                    
                                    # Save this persona's response to database
                                    persona_response_log = ConversationLog(
                                        user_progress_id=user_progress.id,
                                        scene_id=correct_scene_id,
                                        message_type="ai_persona",
                                        sender_name=persona_name_resp,
                                        persona_id=persona_id_resp,
                                        message_content=persona_resp,
                                        message_order=current_order,
                                        timestamp=datetime.utcnow()
                                    )
                                    db_session.add(persona_response_log)
                                    current_order += 1
                                
                                if _is_dev:
                                    print(f"[STREAM] @all message: {scene_personas_count} personas responded, turn_count incremented from {starting_turn_count} to {orchestrator.state.turn_count}")
                                
                                # Set ai_response to empty since we've already streamed all responses separately
                                # This prevents the generic streaming code below from streaming an empty response
                                ai_response = ""
                                # Set persona info - these won't be used since ai_response is empty, but set for consistency
                                persona_name = "All Personas"
                                persona_id = None
                                
                                # Note: Persona responses are already saved to database in the loop above
                                # We'll commit them along with state updates below
                                if _is_dev:
                                    print(f"[STREAM] @all responses saved for {scene_personas_count} personas")
                                
                            except Exception as e:
                                print(f"LangChain @all error: {e}")
                                import traceback
                                traceback.print_exc()
                                ai_response = f"I'm sorry, I'm having trouble processing the @all message right now. Please try again."
                                persona_name = "ChatOrchestrator"
                                persona_id = None
                        else:
                            # Fallback if LangChain not available
                            ai_response = f"I'm sorry, the @all feature requires LangChain integration which is not available right now."
                            persona_name = "ChatOrchestrator"
                            persona_id = None
                
                else:
                    # Regular @mention logic for single persona
                    # Build name mapping for persona lookup
                    name_mapping = {}
                    for persona in orchestrator.scenario.get('personas', []):
                        name = persona['identity']['name'].lower()
                        # Add various name variations
                        name_mapping[name] = persona['id']
                        name_mapping[name.replace("'", "").replace(" ", "_")] = persona['id']
                        name_mapping[name.replace("'", "").replace(" ", "")] = persona['id']
                        # Add first name only
                        first_name = name.split()[0]
                        name_mapping[first_name] = persona['id']
                        name_mapping[first_name.replace("'", "")] = persona['id']
                    
                    # Try to find the persona by name
                    search_name = persona_id.lower()
                    target_persona = None
                    
                    if search_name in name_mapping:
                        persona_id = name_mapping[search_name]
                        target_persona = next((p for p in orchestrator.scenario.get('personas', []) if p['id'] == persona_id), None)
                    else:
                        # Try fuzzy matching
                        for name, pid in name_mapping.items():
                            if (search_name in name or name in search_name or
                                search_name.replace("'", "").replace("_", "") in name.replace("'", "").replace("_", "")):
                                persona_id = pid
                                target_persona = next((p for p in orchestrator.scenario.get('personas', []) if p['id'] == persona_id), None)
                                break
                    
                    if target_persona:
                        # Use LangChain persona agent for response
                        if orchestrator.langchain_enabled:
                            try:
                                ai_response = await orchestrator.chat_with_persona_langchain(
                                    message=request.message,
                                    persona_id=persona_id,
                                    scene_id=correct_scene_id
                                )
                                persona_name = target_persona['identity']['name']
                                persona_id = target_persona.get('db_id')
                            except Exception as e:
                                print(f"LangChain persona chat error: {e}")
                                # Fallback to orchestrator response
                                ai_response = f"I'm sorry, I'm having trouble processing that right now. Please try again or ask the orchestrator for help."
                                persona_name = "ChatOrchestrator"
                                persona_id = None
                        else:
                            # Fallback if LangChain not available
                            ai_response = f"I'm sorry, the persona interaction system is not available right now. Please try again later."
                            persona_name = "ChatOrchestrator"
                            persona_id = None
                    else:
                        # Fallback to orchestrator with redirection
                        ai_response = f"I don't recognize that persona. Available team members: {', '.join([p['id'] for p in orchestrator.scenario.get('personas', [])])}. Please use @mentions to talk to specific team members."
                        persona_name = "ChatOrchestrator"
                        persona_id = None
            else:
                # General orchestrator response - use LangChain if available
                if orchestrator.langchain_enabled:
                    try:
                        # Use orchestrator's system prompt for general responses
                        system_prompt = orchestrator.get_system_prompt()
                        # For now, use direct OpenAI call for orchestrator responses
                        # TODO: Implement orchestrator LangChain integration
                        ai_response = "I'm here to help guide your business simulation. Use @mentions to talk to specific team members or ask me for strategic guidance."
                        persona_name = "ChatOrchestrator"
                        persona_id = None
                    except Exception as e:
                        print(f"LangChain orchestrator error: {e}")
                        ai_response = "I'm here to help guide your business simulation. Use @mentions to talk to specific team members or ask me for strategic guidance."
                        persona_name = "ChatOrchestrator"
                        persona_id = None
                else:
                    ai_response = "I'm here to help guide your business simulation. Use @mentions to talk to specific team members or ask me for strategic guidance."
                    persona_name = "ChatOrchestrator"
                    persona_id = None
            
            # Stream the LangChain response
            if ai_response:
                # Stream the response character by character for consistency with OpenAI streaming
                for char in ai_response:
                    full_response += char
                    yield f"data: {json.dumps({'content': char, 'done': False})}\n\n"
                    await asyncio.sleep(0.03)
            
            # Save AI response to database (only if not @all - @all responses are saved above)
            if not is_all_message_global:
                # Regular single response
                ai_log = ConversationLog(
                    user_progress_id=user_progress.id,
                    scene_id=correct_scene_id,
                    message_type="ai_persona" if persona_id else "orchestrator",
                    sender_name=persona_name,
                    persona_id=persona_id,
                    message_content=full_response,
                    message_order=next_order + 1,
                    timestamp=datetime.utcnow()
                )
                db_session.add(ai_log)
                db_session.flush()
                if _is_dev:
                    print(f"[STREAM] AI response saved: order={next_order + 1}, scene_id={correct_scene_id}")
            else:
                # For @all, responses were already saved above, just flush
                db_session.flush()
                if _is_dev:
                    print(f"[STREAM] @all responses saved for {scene_personas_count} personas")
            
            # Update state
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
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(user_progress, "orchestrator_data")
            user_progress.last_activity = datetime.utcnow()
            
            # Commit the AI response first so it's saved
            db_session.commit()
            if _is_dev:
                print(f"[STREAM DEBUG] Committed AI response to database. Turn count: {orchestrator.state.turn_count}")
            
            # --- CRITICAL: Check for timeout turns AFTER committing AI response ---
            current_scene = orchestrator.scenario.get('scenes', [{}])[orchestrator.state.current_scene_index]
            timeout_turns = current_scene.get('timeout_turns') or current_scene.get('max_turns', 15)
            if _is_dev:
                print(f"[STREAM DEBUG] Turn count: {orchestrator.state.turn_count}, timeout_turns: {timeout_turns}")
            
            if orchestrator.state.turn_count >= timeout_turns:
                if _is_dev:
                    print(f"[STREAM DEBUG] TIMEOUT REACHED: turn_count={orchestrator.state.turn_count}, timeout_turns={timeout_turns} - USING SUBMIT FOR GRADING LOGIC")
                
                # Use the exact same logic as the manual submit for grading
                # Check if there's a next scene available
                if _is_dev:
                    print(f"[DEBUG] (Timeout) Current scene index: {orchestrator.state.current_scene_index}")
                    print(f"[DEBUG] (Timeout) Total scenes: {len(orchestrator.scenario.get('scenes', []))}")
                
                if orchestrator.state.current_scene_index + 1 < len(orchestrator.scenario.get('scenes', [])):
                    # Move to next scene
                    next_scene_index = orchestrator.state.current_scene_index + 1
                    next_scene = orchestrator.scenario.get('scenes', [])[next_scene_index]
                    next_scene_id = next_scene.get('id')
                    if _is_dev:
                        print(f"[DEBUG] (Timeout) Moving to next scene: index={next_scene_index}, id={next_scene_id}, title={next_scene.get('title')}")
                    
                    # No timeout message needed - using loading screen approach
                    
                    # Update orchestrator state
                    orchestrator.state.current_scene_index = next_scene_index
                    orchestrator.state.turn_count = 0
                    if _is_dev:
                        print(f"[DEBUG] TURN COUNT RESET TO 0 ON TIMEOUT PROGRESSION")
                    orchestrator.state.scene_completed = False
                    orchestrator.state.current_scene_id = next_scene_id
                    
                    # Clear conversation history and restart all agents for scene transition
                    if orchestrator.langchain_enabled:
                        if _is_dev:
                            print(f"[DEBUG] TIMEOUT - Clearing conversation history and restarting agents for scene transition")
                        from modules.simulation.agents.persona_agent import PersonaAgent, PersonaAgentManager
                        
                        # Clear all existing agents for this session to force restart
                        if hasattr(orchestrator, 'persona_agent_manager'):
                            orchestrator.persona_agent_manager.clear_session_agents(f"user_{user_progress.id}")
                            if _is_dev:
                                print(f"[DEBUG] TIMEOUT - Cleared all existing agents for session")
                        
                        # Clear the ACTUAL persona agents in the orchestrator, not temporary ones
                        if hasattr(orchestrator, 'persona_agents') and orchestrator.persona_agents:
                            if _is_dev:
                                print(f"[DEBUG] TIMEOUT - Found {len(orchestrator.persona_agents)} existing persona agents to clear")
                            for agent_id, persona_agent in orchestrator.persona_agents.items():
                                if _is_dev:
                                    print(f"[DEBUG] TIMEOUT - Clearing conversation history for existing agent: {agent_id}")
                                result = persona_agent.clear_conversation_history(user_progress.id)
                                if _is_dev:
                                    print(f"[DEBUG] TIMEOUT - clear_conversation_history result: {result}")
                                    print(f"[DEBUG] TIMEOUT - Cleared conversation history for existing persona agent: {agent_id}")
                        else:
                            if _is_dev:
                                print(f"[DEBUG] TIMEOUT - No existing persona agents found in orchestrator - skipping clearing")
                    
                    if _is_dev:
                        print(f"[DEBUG] NEW SCENE START (after timeout progression): index={orchestrator.state.current_scene_index}, turn_count={orchestrator.state.turn_count}, scene_id={next_scene_id}")
                    
                    # CRITICAL: Update UserProgress.current_scene_id to match the orchestrator state
                    user_progress.current_scene_id = next_scene_id
                    if _is_dev:
                        print(f"[DEBUG] Updated UserProgress.current_scene_id to {next_scene_id}")
                    
                    # Clear the ACTUAL persona agents in the orchestrator, not temporary ones
                    if orchestrator.langchain_enabled:
                        if _is_dev:
                            print("Scene transition detected - clearing conversation history for new scene")
                        if hasattr(orchestrator, 'persona_agents') and orchestrator.persona_agents:
                            if _is_dev:
                                print(f"[DEBUG] Found {len(orchestrator.persona_agents)} existing persona agents to clear")
                            for agent_id, persona_agent in orchestrator.persona_agents.items():
                                if _is_dev:
                                    print(f"[DEBUG] Clearing conversation history for existing agent: {agent_id}")
                                persona_agent.clear_conversation_history(user_progress.id)
                                if _is_dev:
                                    print(f"Cleared conversation history for existing persona agent: {agent_id}")
                        else:
                            if _is_dev:
                                print(f"[DEBUG] No existing persona agents found in orchestrator - skipping clearing")
                    
                    # Mark current scene as completed in UserProgress
                    completed_scenes = user_progress.scenes_completed or []
                    if correct_scene_id and correct_scene_id not in completed_scenes:
                        completed_scenes.append(correct_scene_id)
                        user_progress.scenes_completed = completed_scenes
                        if _is_dev:
                            print(f"[DEBUG] Added scene {correct_scene_id} to completed scenes: {completed_scenes}")
                    
                    # Update SceneProgress for the completed scene
                    scene_progress = db_session.query(SceneProgress).filter(
                        and_(
                            SceneProgress.user_progress_id == user_progress.id,
                            SceneProgress.scene_id == correct_scene_id
                        )
                    ).first()
                    
                    if scene_progress:
                        scene_progress.status = "completed"
                        scene_progress.completed_at = datetime.utcnow()
                        if _is_dev:
                            print(f"[DEBUG] Marked SceneProgress {correct_scene_id} as completed")
                    
                    # Create SceneProgress for the new scene
                    new_scene_progress = db_session.query(SceneProgress).filter(
                        and_(
                            SceneProgress.user_progress_id == user_progress.id,
                            SceneProgress.scene_id == next_scene_id
                        )
                    ).first()
                    
                    if not new_scene_progress:
                        new_scene_progress = SceneProgress(
                            user_progress_id=user_progress.id,
                            scene_id=next_scene_id,
                            status="in_progress",
                            started_at=datetime.utcnow()
                        )
                        db_session.add(new_scene_progress)
                        if _is_dev:
                            print(f"[DEBUG] Created SceneProgress for new scene {next_scene_id}")
                    else:
                        new_scene_progress.status = "in_progress"
                        new_scene_progress.started_at = datetime.utcnow()
                        if _is_dev:
                            print(f"[DEBUG] Reactivated SceneProgress for scene {next_scene_id}")
                    
                    # Update timeout_turns for the new scene
                    new_scene = orchestrator.scenario.get('scenes', [{}])[next_scene_index]
                    new_timeout_turns = new_scene.get('timeout_turns') or new_scene.get('max_turns', 15)
                    if _is_dev:
                        print(f"[DEBUG] NEW SCENE timeout_turns: {new_timeout_turns}")
                    
                    # --- PATCH: Persist orchestrator state to DB after progression ---
                    state_dict = {
                        'current_scene_id': orchestrator.state.current_scene_id,
                        'current_scene_index': orchestrator.state.current_scene_index,
                        'turn_count': orchestrator.state.turn_count,
                        'simulation_started': orchestrator.state.simulation_started,
                        'user_ready': orchestrator.state.user_ready,
                        'state_variables': orchestrator.state.state_variables
                    }
                    user_progress.orchestrator_data['state'] = state_dict
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(user_progress, "orchestrator_data")
                    db_session.commit()
                    if _is_dev:
                        print(f"[DEBUG] TIMEOUT - Saved orchestrator state after progression: {state_dict}")
                    
                    # No timeout message saved - using loading screen approach
                    
                    # Send final metadata with scene completion and next scene info
                    # No timeout message - using loading screen approach
                    response_data = {'done': True, 'persona_name': persona_name, 'persona_id': str(persona_id) if persona_id else None, 'scene_completed': True, 'next_scene_id': next_scene_id, 'turn_count': 0, 'full_content': full_response}
                    if _is_dev:
                        print(f"[DEBUG] TIMEOUT STREAMING RESPONSE: {response_data}")
                    yield f"data: {json.dumps(response_data)}\n\n"
                    return
                else:
                    # No more scenes - simulation complete
                    user_progress.simulation_status = "completed"
                    user_progress.completed_at = datetime.utcnow()
                    
                    # No timeout message needed - using loading screen approach
                    
                    # Send final metadata with simulation completion
                    # No timeout message - using loading screen approach
                    yield f"data: {json.dumps({'done': True, 'persona_name': persona_name, 'persona_id': str(persona_id) if persona_id else None, 'scene_completed': True, 'next_scene_id': None, 'turn_count': orchestrator.state.turn_count, 'simulation_complete': True, 'full_content': full_response})}\n\n"
                    return
            else:
                # No timeout - AI response already committed above
                if _is_dev:
                    print(f"[STREAM DEBUG] No timeout. Turn count: {orchestrator.state.turn_count}, simulation_started: {orchestrator.state.simulation_started}")
            
            # Send final metadata
            yield f"data: {json.dumps({'done': True, 'persona_name': persona_name, 'persona_id': str(persona_id) if persona_id else None, 'scene_completed': scene_completed, 'next_scene_id': next_scene_id, 'turn_count': orchestrator.state.turn_count, 'full_content': full_response})}\n\n"
            
        except Exception as e:
            db_session.rollback()
            print(f"[ERROR] Streaming chat error: {str(e)}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(generate_stream(db), media_type="text/event-stream")

