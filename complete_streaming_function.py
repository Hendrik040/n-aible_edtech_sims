async def linear_simulation_chat_stream(
    request: SimulationChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Handle orchestrated chat interactions with streaming responses"""
    
    async def generate_stream(db_session: Session):
        """Generator function for streaming OpenAI responses"""
        # Import ChatOrchestrator at the top of the function
        from api.chat_orchestrator import ChatOrchestrator
        
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
                print(f"[DEBUG] Before initialization - orchestrator.state.current_scene_id: {getattr(orchestrator.state, 'current_scene_id', 'NOT_SET')}")
                print(f"[DEBUG] user_progress.current_scene_id: {user_progress.current_scene_id}")
                if not hasattr(orchestrator.state, 'current_scene_id') or orchestrator.state.current_scene_id is None or orchestrator.state.current_scene_id == "":
                    orchestrator.state.current_scene_id = user_progress.current_scene_id
                    print(f"[DEBUG] Initialized orchestrator.state.current_scene_id from user_progress: {orchestrator.state.current_scene_id}")
                else:
                    print(f"[DEBUG] orchestrator.state.current_scene_id already set to: {orchestrator.state.current_scene_id}")
                
                # Check if we're in a different scene than before
                current_scene_id = orchestrator.state.current_scene_id
                print(f"[DEBUG] Scene transition check - _last_scene_id: {orchestrator._last_scene_id}, current_scene_id: {current_scene_id}")
                
                # Clear conversation history on scene transitions
                if orchestrator._last_scene_id is not None and orchestrator._last_scene_id != current_scene_id:
                    print(f"Scene transition detected: {orchestrator._last_scene_id} -> {current_scene_id}")
                    print("Scene transition detected - clearing conversation history for new scene")
                    
                    # Clear conversation history for all existing persona agents
                    if hasattr(orchestrator, 'persona_agents') and orchestrator.persona_agents:
                        print(f"[DEBUG] Found {len(orchestrator.persona_agents)} existing persona agents to clear")
                        for persona_id, agent in orchestrator.persona_agents.items():
                            print(f"[DEBUG] Clearing conversation history for existing agent: {persona_id}")
                            agent.clear_conversation_history(user_progress.id)
                            print(f"Cleared conversation history for existing persona agent: {persona_id}")
                elif orchestrator._last_scene_id is None:
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
                    print(f"[STREAM DEBUG] Simulation already started, ignoring 'begin' command")
                    # Return a message saying simulation is already running
                    already_started_msg = "The simulation is already in progress. You can continue interacting with the personas."
                    for char in already_started_msg:
                        yield f"data: {json.dumps({'content': char, 'done': False})}\n\n"
                        await asyncio.sleep(0.02)
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
                print(f"[STREAM DEBUG] Saved state after begin - simulation_started: {state_dict['simulation_started']}, simulation_status: {user_progress.simulation_status}")
                
                # Generate scene intro message
                scene_intro_message = generate_scene_intro_message(current_scene)
                
                # Stream welcome message with natural typing speed
                welcome_msg = "🎬 **Simulation Started!**\n\nThe simulation has begun. You can now interact with the personas in this scene."
                for char in welcome_msg:
                    full_response += char
                    yield f"data: {json.dumps({'content': char, 'done': False})}\n\n"
                    await asyncio.sleep(0.02)  # 40ms delay for slower, more deliberate typing
                
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
                print(f"[STREAM DEBUG] Saved scene intro message: order={begin_order + 2}")
                
                # Send metadata
                yield f"data: {json.dumps({'done': True, 'persona_name': 'ChatOrchestrator', 'persona_id': None, 'scene_completed': False, 'next_scene_id': None, 'turn_count': 0, 'scene_intro_message': scene_intro_message, 'full_content': full_response})}\n\n"
                return
            
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
            print(f"[STREAM] User msg saved: order={next_order}, scene_id={correct_scene_id}")
            
            # Increment turn count
            if request.message.lower().strip() not in ["begin", "help"]:
                orchestrator.state.turn_count += 1
            
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
            import re
            persona_name = "ChatOrchestrator"
            persona_id = None
            ai_response = ""
            
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
            
            if mention_match:
                persona_id = mention_match.group(1)
                
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
                    await asyncio.sleep(0.02)
            
            # Save AI response to database
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
            print(f"[STREAM] AI response saved: order={next_order + 1}, scene_id={correct_scene_id}")
            
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
            db_session.commit()
            print(f"[STREAM DEBUG] Committed to database. Turn count: {orchestrator.state.turn_count}, simulation_started: {orchestrator.state.simulation_started}")
            
            # Send final metadata
            yield f"data: {json.dumps({'done': True, 'persona_name': persona_name, 'persona_id': str(persona_id) if persona_id else None, 'scene_completed': scene_completed, 'next_scene_id': next_scene_id, 'turn_count': orchestrator.state.turn_count, 'full_content': full_response})}\n\n"
            
        except Exception as e:
            db_session.rollback()
            print(f"[ERROR] Streaming chat error: {str(e)}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(generate_stream(db), media_type="text/event-stream")
