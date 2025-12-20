"""
Persona Agent for AI Agent Education Platform
Handles persona-specific interactions with context awareness and memory
"""

# Standard library imports
import asyncio
import json
import logging
import time
import traceback
from datetime import datetime
from typing import Dict, List, Any, Optional

# Third-party imports
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.memory import ConversationBufferWindowMemory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import BaseTool, tool
from sqlalchemy import delete, and_, or_
from sqlalchemy.orm import Session

# Local application imports
from common.config import get_settings
from common.db.core import SessionLocal
from common.db.models import SimulationPersona, ConversationLog
from common.services.ai_gateway import langchain_manager
from modules.simulation.agents.callbacks import PersonaCallbackHandler
from modules.simulation.agents.manager import persona_agent_manager

# Initialize settings and helpers
settings = get_settings()
_is_dev = settings.environment != "production"
debug_log = logging.getLogger(__name__).debug
logger = logging.getLogger(__name__)

class PersonaAgent:
    """LangChain-based persona agent with context awareness and memory.
    
    Stateless per request: Memory and chain are created fresh for each chat() call.
    This ensures complete isolation between concurrent requests and prevents state leakage.
    """
    
    def __init__(self, persona: SimulationPersona, session_id: str, user_progress_id: int = None):
        self.persona = persona
        self.session_id = session_id
        self.user_progress_id = user_progress_id
        
        # Use the provided session_id directly (ChatOrchestrator now provides unique session IDs)
        self.persona_session_id = session_id
        
        # Shared resources (stateless, can be reused across requests)
        # Use isolated LLM instance per persona agent to avoid connection pooling issues
        # Each agent gets its own LLM instance, but they all use the same OpenAI API
        self.llm = langchain_manager.create_fresh_llm()  # Isolated instance
        self.vectorstore = langchain_manager.vectorstore  # Shared vectorstore is fine
        
        # Tools are stateless - create once (they don't hold conversation state)
        self.tools = self._create_persona_tools()
        
        # REMOVED: self.memory, self.agent, self.agent_executor
        # These will be created fresh per request in chat() method for full statelessness
    
    def _create_persona_tools(self) -> List[BaseTool]:
        """Create tools specific to this persona"""
        @tool
        def get_scene_context(scene_description: str) -> str:
            """Get relevant context about the current scene using semantic search"""
            if not scene_description:
                return "No scene context available"
            
            try:
                # Use PGVector for semantic search
                if self.vectorstore:
                    # Search for relevant context using the scene description
                    docs = self.vectorstore.similarity_search(
                        scene_description,
                        k=3,
                        filter={"persona_id": str(self.persona.id), "context_type": "scene"}
                    )
                    
                    if docs:
                        context_parts = []
                        for doc in docs:
                            context_parts.append(f"- {doc.page_content}")
                        return f"Relevant scene context:\n" + "\n".join(context_parts)
                    else:
                        # Store the scene description for future reference, but avoid
                        # unbounded growth by only storing when it is sufficiently long
                        # and likely to be useful as reusable context.
                        if len(scene_description) > 100:
                            self.vectorstore.add_texts(
                                [scene_description],
                                metadatas=[{
                                    "persona_id": str(self.persona.id),
                                    "context_type": "scene",
                                    "timestamp": str(datetime.now())
                                }]
                            )
                        return f"Scene context: {scene_description}"
                else:
                    raise ValueError("PGVector not available - vectorstore is required")
            except Exception as e:
                debug_log(f"Error in get_scene_context: {e}")
                raise e
        
        @tool
        def get_persona_knowledge(query: str) -> str:
            """Get persona-specific knowledge using semantic search"""
            try:
                if self.vectorstore:
                    # Search for persona-specific knowledge
                    docs = self.vectorstore.similarity_search(
                        query,
                        k=3,
                        filter={"persona_id": str(self.persona.id), "context_type": "knowledge"}
                    )
                    
                    if docs:
                        knowledge_parts = []
                        for doc in docs:
                            knowledge_parts.append(f"- {doc.page_content}")
                        return f"Relevant knowledge for {self.persona.name}:\n" + "\n".join(knowledge_parts)
                    else:
                        # Store the persona background for future reference once, but
                        # avoid repeated writes on every call by checking for existing
                        # knowledge documents first.
                        existing_docs = self.vectorstore.similarity_search(
                            f"{self.persona.name} background",
                            k=1,
                            filter={
                                "persona_id": str(self.persona.id),
                                "context_type": "knowledge",
                            },
                        )
                        if not existing_docs:
                            self.vectorstore.add_texts(
                                [f"{self.persona.name} background: {self.persona.background}"],
                                metadatas=[{
                                    "persona_id": str(self.persona.id),
                                    "context_type": "knowledge",
                                    "timestamp": str(datetime.now())
                                }]
                            )
                        return f"Persona knowledge for {self.persona.name}: {self.persona.background}"
                else:
                    raise ValueError("PGVector not available - vectorstore is required")
            except Exception as e:
                debug_log(f"Error in get_persona_knowledge: {e}")
                raise e
        
        return [get_scene_context, get_persona_knowledge]
    
    def _create_persona_prompt(self) -> ChatPromptTemplate:
        """Create persona-specific prompt template"""
        # If a custom system prompt exists, honor it verbatim and avoid injecting
        # additional scaffolding that could override intent.
        if isinstance(self.persona.system_prompt, str) and self.persona.system_prompt.strip():
            # Use the escaped system prompt from _get_system_prompt to ensure JSON is properly escaped
            escaped_system_prompt = self._get_system_prompt()
            return ChatPromptTemplate.from_messages([
                ("system", escaped_system_prompt),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad")
            ])
        # Default persona prompt with history/tools when no custom prompt provided
        return ChatPromptTemplate.from_messages([
            ("system", self._get_system_prompt()),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
    
    def _create_persona_prompt_with_attempt(self, attempt_number: int, scene_context: Dict[str, Any] = None) -> ChatPromptTemplate:
        """Create persona-specific prompt template with scene context"""
        # Prepare scene context for inclusion in system prompt
        scene_context_str = ""
        if scene_context:
            # Create a simple text representation instead of JSON
            context_parts = []
            if isinstance(scene_context, dict):
                for key, value in scene_context.items():
                    if isinstance(value, dict):
                        context_parts.append(f"{key}:")
                        for sub_key, sub_value in value.items():
                            # Escape any curly braces in the values
                            safe_value = str(sub_value).replace("{", "{{").replace("}", "}}")
                            context_parts.append(f"  {sub_key}: {safe_value}")
                    else:
                        # Escape any curly braces in the values
                        safe_value = str(value).replace("{", "{{").replace("}", "}}")
                        context_parts.append(f"{key}: {safe_value}")
            
            scene_context_str = f"\nCURRENT SCENE CONTEXT:\n" + "\n".join(context_parts)
        
        # If a custom system prompt exists, use it verbatim
        if isinstance(self.persona.system_prompt, str) and self.persona.system_prompt.strip():
            # Add case study context to custom system prompt as well
            case_study_context = ""
            conversation_instruction = """

NOTE: Conversation history is already available in your memory. You have access to recent messages in this conversation through your chat history."""
            if scene_context and isinstance(scene_context, dict):
                simulation = scene_context.get('simulation', {})
                if isinstance(simulation, dict):
                    case_study_context = f"""

CASE STUDY CONTEXT:
Title: {simulation.get('title', 'Business Simulation')}
Description: {simulation.get('description', '')}
Challenge: {simulation.get('challenge', '')}

STUDENT ROLE: You are interacting with a student who is playing the role of: {simulation.get('student_role', 'a business student')}

CURRENT SCENE: {scene_context.get('current_scene', {}).get('title', 'Business Meeting') if scene_context.get('current_scene') else 'Business Meeting'}
Scene Description: {scene_context.get('current_scene', {}).get('description', '') if scene_context.get('current_scene') else ''}
Scene Objectives: {', '.join(scene_context.get('current_scene', {}).get('objectives', [])) if scene_context.get('current_scene') and scene_context.get('current_scene', {}).get('objectives') else 'To discuss business matters'}

"""
            
            system_prompt = self.persona.system_prompt + case_study_context + scene_context_str + conversation_instruction
            # Escape any curly braces in the custom system prompt to prevent LangChain template variable errors
            escaped_prompt = system_prompt.replace("{", "{{").replace("}", "}}")
            
            return ChatPromptTemplate.from_messages([
                ("system", escaped_prompt),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad")
            ])
        
        # Default with attempt-specific few-shot only when no custom prompt provided
        system_prompt = self._get_system_prompt(attempt_number, scene_context) + scene_context_str
        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
    
    def _get_system_prompt(self, attempt_number: int = 1, scene_context: Dict[str, Any] = None) -> str:
        """Generate system prompt for the persona based on traits, background, and goals"""
        # If custom system prompt is provided, use it directly and completely isolate it
        if self.persona.system_prompt:
            # Use the custom system prompt exactly as provided - no modifications
            # This ensures complete isolation from orchestrator prompts
            return self.persona.system_prompt
        
        # Otherwise, generate the default system prompt
        personality_traits = self.persona.personality_traits or {}
        primary_goals = self.persona.primary_goals or []
        
        # Add case study and simulation context
        case_study_context = ""
        if scene_context and isinstance(scene_context, dict):
            # Prefer simulation key; fall back to legacy scenario key
            simulation = scene_context.get('simulation') or scene_context.get('scenario') or {}
            if isinstance(simulation, dict):
                case_study_context = f"""

CASE STUDY CONTEXT:
Title: {simulation.get('title', 'Business Simulation')}
Description: {simulation.get('description', '')}
Challenge: {simulation.get('challenge', '')}

STUDENT ROLE: You are interacting with a student who is playing the role of: {simulation.get('student_role', 'a business student')}

CURRENT SCENE: {scene_context.get('current_scene', {}).get('title', 'Business Meeting') if scene_context.get('current_scene') else 'Business Meeting'}
Scene Description: {scene_context.get('current_scene', {}).get('description', '') if scene_context.get('current_scene') else ''}
Scene Objectives: {', '.join(scene_context.get('current_scene', {}).get('objectives', [])) if scene_context.get('current_scene') and scene_context.get('current_scene', {}).get('objectives') else 'To discuss business matters'}

"""
            else:
                if _is_dev:
                    debug_log("No simulation/scenario found in scene_context")
        else:
            if _is_dev:
                debug_log(f"No scene_context or not a dict: {type(scene_context)}")
        
        system_prompt = f"""You are {self.persona.name}, a {self.persona.role} in this business simulation.{case_study_context}

PERSONA BACKGROUND:
{self.persona.background}

CORRELATION TO CASE:
{self.persona.correlation}

PERSONALITY TRAITS:
{', '.join([f"{k}: {v}" for k, v in personality_traits.items()]) if personality_traits else 'None specified'}

PRIMARY GOALS:
{chr(10).join(f"• {goal}" for goal in primary_goals)}

INSTRUCTIONS:
- CONVERSATION HISTORY: You have access to recent conversation history in your memory. Use it to maintain context and respond appropriately.
- CONVERSATION ANALYSIS: When analyzing conversation history, pay attention to the chronological order of messages to determine what happened first, last, etc.
- PERSONA ISOLATION: NEVER copy or mimic other personas' responses, patterns, or behaviors. Stay true to YOUR unique character and role.
- Stay in character as {self.persona.name} at all times
- Respond based on your role, background, and personality traits
- Help guide the user toward scene objectives through realistic business interaction
- Don't directly give away answers, but provide realistic business insights
- Keep responses concise and professional (2-4 sentences typically)
- Use your tools to access relevant context and knowledge
- If the user seems stuck, provide subtle hints through natural conversation
- Maintain consistent character behavior based on your personality traits, goals, and role

Remember: You are {self.persona.name}, not an AI assistant. Respond as this character would in a real business situation."""
        
        if _is_dev:
            debug_log(
                f"System prompt generated for persona {self.persona.name}; "
                f"has_case_study={'CASE STUDY CONTEXT' in system_prompt}, "
                f"has_student_role={'STUDENT ROLE' in system_prompt}"
            )
        
        return system_prompt
    
    def _load_conversation_history_from_db(
        self,
        user_progress_id: int,
        scene_id: int,
        current_message: str = None,
        db: Optional[Session] = None,
    ) -> List[ConversationLog]:
        """Load conversation history from database with full scene context.
        
        Loads ALL messages in the scene conversation so personas have context of:
        - All user messages (to any persona or general)
        - All persona responses (from any persona)
        - Orchestrator messages
        
        Returns list of ConversationLog objects in chronological order.
        This method is stateless - it just queries and returns data.
        Memory loading happens in chat() method with fresh memory instance.
        
        Args:
            user_progress_id: The user progress ID
            scene_id: The scene ID
            current_message: Optional current message to exclude from loading (will be added by LangChain)
            db: Optional database session (preferred over creating new one)
            
        Returns:
            List of ConversationLog objects in chronological order (oldest first)
            
        Raises:
            RuntimeError: If query fails (timeout, connection error, etc.)
        """
        try:
            # Prefer the request-scoped session if provided; otherwise use a short-lived SessionLocal.
            if db is not None:
                session = db
                own_session = False
            else:
                session = SessionLocal()
                own_session = True

            try:
                # Extract base session_id from persona_session_id
                # persona_session_id format: "session_abc123_persona_1" -> base: "session_abc123"
                # If no "_persona_" suffix, use the session_id as-is
                base_session_id = self.persona_session_id
                if "_persona_" in self.persona_session_id:
                    base_session_id = self.persona_session_id.rsplit("_persona_", 1)[0]
                
                # Get bounded conversation logs for this scene
                # Load messages from BOTH base session_id AND persona-specific session_id
                # This ensures we see:
                # - General messages (saved with base session_id)
                # - Persona-specific messages (saved with persona_session_id)
                # - All personas' responses (saved with various session_ids)
                max_messages = getattr(settings, "max_conversation_history_messages", 20)
                
                # Use SQLAlchemy timeout via execution_options to prevent query hangs
                # This works cross-platform and is more reliable than signal-based timeouts
                query = (
                    session.query(ConversationLog)
                    .filter(
                        ConversationLog.user_progress_id == user_progress_id,
                        ConversationLog.scene_id == scene_id,
                        # Include messages from base session_id OR persona-specific session_id
                        # This allows personas to see the full scene conversation
                        or_(
                            ConversationLog.session_id == base_session_id,
                            ConversationLog.session_id == self.persona_session_id,
                            # Also include messages that start with base_session_id (for other personas in same scene)
                            ConversationLog.session_id.like(f"{base_session_id}_%")
                        )
                    )
                    .order_by(ConversationLog.message_order.desc())
                    .execution_options(timeout=5)  # 5 second query timeout to prevent hangs
                )
                if max_messages and max_messages > 0:
                    query = query.limit(max_messages)
                # Reverse so we replay in chronological order (oldest first)
                try:
                    conversation_logs = list(reversed(query.all()))
                except Exception as query_err:
                    # Query failed - log error and raise to prevent silent failure
                    # This ensures we know when memory loading fails and can fix the root cause
                    error_msg = (
                        f"Failed to load conversation history: {query_err}. "
                        f"user_progress_id={user_progress_id}, scene_id={scene_id}, "
                        f"base_session_id={base_session_id}, persona_session_id={self.persona_session_id}"
                    )
                    logger.error(error_msg, exc_info=True)
                    # Re-raise to fail fast - don't silently continue with empty memory
                    raise RuntimeError(f"Memory loading failed: {error_msg}") from query_err

                # Filter out current message if provided (to avoid duplicate when LangChain adds it)
                if current_message:
                    conversation_logs = [
                        log for log in conversation_logs
                        if not (log.message_type == "user" and log.message_content == current_message)
                    ]
                
                # Include ALL messages in the scene conversation for full context
                # This allows personas to see:
                # - All user messages (to any persona or general)
                # - All persona responses (from any persona)
                # - Orchestrator messages
                # No filtering needed - we want the full scene context
                filtered_logs = conversation_logs
                
                if _is_dev:
                    user_count = sum(1 for log in filtered_logs if log.message_type == "user")
                    ai_persona_count = sum(1 for log in filtered_logs if log.message_type == "ai_persona")
                    orchestrator_count = sum(1 for log in filtered_logs if log.message_type == "orchestrator")
                    debug_log(
                        f"Loaded {len(filtered_logs)} conversation messages from DB for persona {self.persona.name} "
                        f"(user: {user_count}, ai_persona: {ai_persona_count}, orchestrator: {orchestrator_count}, "
                        f"from {len(conversation_logs)} total logs, max={max_messages}) "
                        f"base_session_id={base_session_id}, persona_session_id={self.persona_session_id}"
                    )
                
                return filtered_logs

            finally:
                if own_session:
                    session.close()
        except RuntimeError:
            # Re-raise RuntimeError (query failures) as-is
            raise
        except Exception as e:
            # Wrap other exceptions
            error_msg = (
                f"Unexpected error loading conversation history: {e}. "
                f"user_progress_id={user_progress_id}, scene_id={scene_id}, "
                f"session_id={self.persona_session_id}"
            )
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(f"Memory loading failed: {error_msg}") from e
    
    async def chat(self, 
                   message: str, 
                   scene_context: Dict[str, Any],
                   user_progress_id: int,
                   scene_id: int,
                   attempt_number: int = 1,
                   db: Optional[Session] = None) -> str:
        """Chat with persona agent - stateless per request.
        
        Creates fresh memory and chain for each request to ensure complete isolation.
        Follows stateless inference pattern: Load from DB → Create fresh memory → Create fresh chain → Run
        
        Args:
            message: User message
            scene_context: Current scene context
            user_progress_id: User progress ID
            scene_id: Current scene ID
            attempt_number: Attempt number (for few-shot examples)
            db: Optional database session
            
        Returns:
            Persona response text
        """
        timings = {
            "total_start": time.time(),
            "memory_load_time": 0,
            "memory_setup_time": 0,
            "chain_creation_time": 0,
            "agent_execution_time": 0,
            "vectorstore_time": 0
        }
        
        try:
            # Step 1: Load conversation history from DB (with session_id filter)
            memory_load_start = time.time()
            if _is_dev:
                debug_log(
                    f"Loading conversation history for persona {self.persona.name} "
                    f"with session_id={self.persona_session_id}, "
                    f"user_progress_id={user_progress_id}, scene_id={scene_id}"
                )
            conversation_logs = self._load_conversation_history_from_db(
                user_progress_id,
                scene_id,
                current_message=message,
                db=db,
            )
            timings["memory_load_time"] = time.time() - memory_load_start
            
            # Step 2: Create FRESH memory instance per request
            memory_setup_start = time.time()
            memory = langchain_manager.create_conversation_memory(
                self.persona_session_id,
                memory_type="buffer_window"
            )
            
            # Step 3: Load history into fresh memory
            # Include ALL messages for full scene context:
            # - User messages (to any persona or general)
            # - All persona responses (from any persona)
            # - Orchestrator messages
            loaded_user_messages = 0
            loaded_ai_messages = 0
            loaded_orchestrator_messages = 0
            for log in conversation_logs:
                if log.message_type == "user":
                    memory.chat_memory.add_user_message(log.message_content)
                    loaded_user_messages += 1
                elif log.message_type == "ai_persona":
                    # Include ALL persona responses (not just this persona's)
                    # This gives personas context of what other personas said
                    memory.chat_memory.add_ai_message(log.message_content)
                    loaded_ai_messages += 1
                elif log.message_type == "orchestrator":
                    # Include orchestrator messages for full scene context
                    memory.chat_memory.add_ai_message(log.message_content)
                    loaded_orchestrator_messages += 1
            
            if _is_dev:
                debug_log(
                    f"Memory loaded: {loaded_user_messages} user messages, {loaded_ai_messages} AI persona messages, "
                    f"{loaded_orchestrator_messages} orchestrator messages "
                    f"(total in memory: {len(memory.chat_memory.messages) if hasattr(memory, 'chat_memory') else 0})"
                )
            
            timings["memory_setup_time"] = time.time() - memory_setup_start
            
            # Step 4: Create FRESH prompt with scene context
            prompt = self._create_persona_prompt_with_attempt(attempt_number, scene_context)
            
            # Step 5: Create FRESH agent
            chain_creation_start = time.time()
            agent = create_openai_tools_agent(
                llm=self.llm,
                tools=self.tools,
                prompt=prompt
            )
            
            # Step 6: Create FRESH executor with fresh memory
            import os
            max_iter = int(os.getenv("PERSONA_AGENT_MAX_ITERATIONS", "2"))
            agent_executor = AgentExecutor(
                agent=agent,
                tools=self.tools,
                memory=memory,  # Fresh memory attached to fresh executor
                verbose=(getattr(settings, "environment", "development") != "production"),
                handle_parsing_errors=True,
                max_iterations=max_iter
            )
            timings["chain_creation_time"] = time.time() - chain_creation_start
            
            # Create callback handler for logging
            callback_handler = PersonaCallbackHandler(
                persona_id=self.persona.id,
                user_progress_id=user_progress_id,
                scene_id=scene_id,
                session_id=self.persona_session_id,  # CRITICAL: Must match session_id used when loading history
                db=db,
            )
            
            # Store the user message in PGVector in background - non-blocking
            # To keep vector usage bounded, we only embed user messages that are likely to be semantically meaningful
            if self.vectorstore and len(message.strip()) >= 16:
                def _store_user_message_sync():
                    try:
                        self.vectorstore.add_texts(
                            [f"User: {message}"],
                            metadatas=[{
                                "persona_id": str(self.persona.id),
                                "context_type": "conversation",
                                "message_type": "user",
                                "user_progress_id": str(user_progress_id),
                                "scene_id": str(scene_id),
                                "timestamp": str(datetime.now()),
                                "session_id": self.persona_session_id
                            }]
                        )
                    except Exception as e:
                        # Non-critical: log but don't block
                        if _is_dev:
                            debug_log(f"Could not store user message in PGVector: {e}")
                
                # Fire and forget - run in background executor
                try:
                    loop = asyncio.get_event_loop()
                    loop.run_in_executor(None, _store_user_message_sync)
                except Exception:
                    # If event loop not available, skip (non-critical)
                    pass
            
            # Step 7: Run executor with fresh chain
            if _is_dev:
                debug_log(
                    f"Executing agent with message length={len(message)}; "
                    f"memory_messages={len(memory.chat_memory.messages) if hasattr(memory, 'chat_memory') else 0}"
                )
            
            execution_start = time.time()
            response = await agent_executor.ainvoke(
                {"input": message},
                callbacks=[callback_handler]
            )
            timings["agent_execution_time"] = time.time() - execution_start
            
            response_text = response.get("output", "I'm not sure how to respond to that.")
            
            # Store the persona response in PGVector in background - non-blocking
            # To keep the vectorstore size manageable, only embed non-trivial responses
            if self.vectorstore and response_text and len(response_text.strip()) >= 32:
                def _store_persona_response_sync():
                    try:
                        self.vectorstore.add_texts(
                            [f"{self.persona.name}: {response_text}"],
                            metadatas=[{
                                "persona_id": str(self.persona.id),
                                "context_type": "conversation",
                                "message_type": "assistant",
                                "user_progress_id": str(user_progress_id),
                                "scene_id": str(scene_id),
                                "timestamp": str(datetime.now()),
                                "session_id": self.persona_session_id
                            }]
                        )
                    except Exception as e:
                        # Non-critical: log but don't block or raise
                        if _is_dev:
                            debug_log(f"Could not store persona response in PGVector: {e}")
                
                # Fire and forget - run in background executor
                try:
                    loop = asyncio.get_event_loop()
                    loop.run_in_executor(None, _store_persona_response_sync)
                except Exception:
                    # If event loop not available, skip (non-critical)
                    pass
            
            timings["total_time"] = time.time() - timings["total_start"]
            # Log performance metrics only in development to avoid Railway log overflow
            if _is_dev:
                debug_log(
                    f"PersonaAgent.chat timings total={timings['total_time']:.2f}s, "
                    f"load={timings['memory_load_time']:.2f}s, "
                    f"setup={timings['memory_setup_time']:.2f}s, "
                    f"chain={timings['chain_creation_time']:.2f}s, "
                    f"execution={timings['agent_execution_time']:.2f}s, "
                    f"user_progress_id={user_progress_id}"
                )
            
            # Step 8: Return response (memory auto-saves via ConversationLog, no explicit save needed)
            return response_text
            
        except Exception as e:
            logger.error(
                f"Error in persona agent chat: {e}. "
                f"Persona: {self.persona.name if self.persona else 'None'}, "
                f"user_progress_id={user_progress_id}, scene_id={scene_id}",
                exc_info=True
            )
            raise e
    
    def clear_conversation_history(self, user_progress_id: int):
        """
        Clear conversation history from vectorstore.
        
        NOTE: This is an expensive operation and should be called only from
        explicit reset/cleanup flows (e.g., when a simulation is reset), not
        on the per-message hot path.
        
        Since memory is created fresh per request, we don't need to clear
        LangChain memory - only need to clear vectorstore embeddings.
        """
        if _is_dev:
            debug_log(f"clear_conversation_history called for persona {self.persona.name} (ID: {self.persona.id})")

        try:
            if self.vectorstore:
                # Use direct SQL deletion instead of LangChain's delete method
                if _is_dev:
                    debug_log("clear_conversation_history - Using direct SQL deletion from PGVector")

                # Get the database session from the vectorstore
                with Session(self.vectorstore._bind) as session:
                    # Delete conversation documents using direct SQL with STRICT metadata filtering
                    delete_filter = {
                        "persona_id": str(self.persona.id),
                        "context_type": "conversation",
                        "user_progress_id": str(user_progress_id),
                        "session_id": str(self.persona_session_id)  # Session isolation
                    }

                    if _is_dev:
                        debug_log(f"clear_conversation_history - Delete filter: {delete_filter}")

                    # Build the delete statement with JSONB metadata filtering including session isolation
                    stmt = delete(self.vectorstore.EmbeddingStore).where(
                        and_(
                            self.vectorstore.EmbeddingStore.cmetadata['persona_id'].astext == str(self.persona.id),
                            self.vectorstore.EmbeddingStore.cmetadata['context_type'].astext == 'conversation',
                            self.vectorstore.EmbeddingStore.cmetadata['user_progress_id'].astext == str(user_progress_id),
                            self.vectorstore.EmbeddingStore.cmetadata['session_id'].astext == str(self.persona_session_id)
                        )
                    )

                    # Execute the deletion
                    result = session.execute(stmt)
                    session.commit()

                    if _is_dev:
                        debug_log(f"clear_conversation_history - Deleted {result.rowcount} conversation documents")
            
            if _is_dev:
                debug_log(f"Conversation history cleared for persona: {self.persona.name}")
            return True
        except Exception as e:
            logger.error(f"Error clearing conversation history: {e}", exc_info=True)
            return False
    
    def update_persona_context(self, new_context: Dict[str, Any]):
        """Update persona context with new information"""
        # This could be used to update the persona's knowledge base
        # or modify their behavior based on new information
        pass

__all__ = ["PersonaAgent", "persona_agent_manager"]
