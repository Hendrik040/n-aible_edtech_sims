"""
Persona Agent for AI Agent Education Platform
Handles persona-specific interactions with context awareness and memory
"""

from typing import Dict, List, Any, Optional
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import BaseMessage, HumanMessage, AIMessage
from langchain.memory import ConversationBufferWindowMemory
from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema.output import LLMResult
import json
from datetime import datetime

from langchain_config import langchain_manager, settings

# Helper to check if we're in development
_is_dev = getattr(settings, "environment", "development") != "production"
from database.models import ScenarioPersona, ConversationLog
from database.connection import get_db, SessionLocal
from services.few_shot_examples import few_shot_examples_service
from common.utilities.debug_logging import debug_log

class PersonaCallbackHandler(BaseCallbackHandler):
    """Callback handler for persona interactions"""
    
    def __init__(self, persona_id: int, user_progress_id: int, scene_id: int):
        self.persona_id = persona_id
        self.user_progress_id = user_progress_id
        self.scene_id = scene_id
        self.start_time = None
        self.tokens_used = 0
        
    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs) -> None:
        """Called when LLM starts"""
        self.start_time = datetime.utcnow()
        
    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        """Called when LLM ends"""
        if self.start_time:
            processing_time = (datetime.utcnow() - self.start_time).total_seconds()
            # Log the interaction
            self._log_conversation(response.generations[0][0].text, processing_time)
    
    def _log_conversation(self, response_text: str, processing_time: float):
        """Log conversation to database"""
        db = None
        try:
            db = SessionLocal()
            conversation_log = ConversationLog(
                user_progress_id=self.user_progress_id,
                scene_id=self.scene_id,
                message_type="ai_persona",
                sender_name="Persona",
                persona_id=self.persona_id,
                message_content=response_text,
                message_order=self._next_message_order(db),
                ai_model_version=settings.openai_model,
                processing_time=processing_time,
                timestamp=datetime.utcnow()
            )
            db.add(conversation_log)
            db.commit()
            db.close()
        except Exception as e:
            debug_log(f"Error logging conversation: {e}")
            raise
        finally:
            if db is not None:
                db.close()
                
    def _next_message_order(self, db):
        last = (
            db.query(ConversationLog.message_order)
            .filter(
                ConversationLog.user_progress_id == self.user_progress_id,
                ConversationLog.scene_id == self.scene_id,
            )
            .order_by(ConversationLog.message_order.desc())
            .first()
        )
        return (last[0] if last else 0) + 1

class PersonaAgent:
    """LangChain-based persona agent with context awareness and memory"""
    
    def __init__(self, persona: ScenarioPersona, session_id: str, user_progress_id: int = None):
        self.persona = persona
        self.session_id = session_id
        self.user_progress_id = user_progress_id
        
        # Use the provided session_id directly (ChatOrchestrator now provides unique session IDs)
        self.persona_session_id = session_id
        
        # Create isolated memory for this specific persona
        self.memory = langchain_manager.create_conversation_memory(
            self.persona_session_id, 
            memory_type="buffer_window"
        )
        # Use isolated LLM instance per persona agent to avoid connection pooling issues
        # Each agent gets its own LLM instance, but they all use the same OpenAI API
        self.llm = langchain_manager.create_fresh_llm()  # Isolated instance
        self.vectorstore = langchain_manager.vectorstore  # Shared vectorstore is fine
        
        # Create persona-specific tools
        self.tools = self._create_persona_tools()
        
        # Create agent prompt
        self.prompt = self._create_persona_prompt()
        
        # Create agent with explicit tool usage
        self.agent = create_openai_tools_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=self.prompt
        )
        
        # Create agent executor
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            memory=self.memory,
            verbose=(getattr(settings, "environment", "development") != "production"),
            handle_parsing_errors=True,
            max_iterations=3
        )
    
    def _create_persona_tools(self) -> List[BaseTool]:
        """Create tools specific to this persona"""
        from langchain.tools import tool
        
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
                        # Store the scene description for future reference
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
        def get_conversation_history(context_type: str = "both") -> str:
            """Get conversation history based on context type. 
            
            Args:
                context_type: Choose from:
                    - "personal": Use when user asks about YOUR specific interactions (e.g., "what did I say to you?", "our conversation", "what did you tell me?")
                    - "scene": Use when user asks about broader scene context, other people, or general scene information
                    - "both": Use when query could benefit from both contexts, or when unsure (default)
            """
            try:
                if self.vectorstore:
                    # Base search filter
                    base_filter = {
                        "context_type": "conversation"
                    }

                    # Add user_progress_id filter if we have it
                    if hasattr(self, 'user_progress_id') and self.user_progress_id:
                        base_filter["user_progress_id"] = str(self.user_progress_id)

                    # Add scene_id filter for additional isolation
                    if hasattr(self, 'current_scene_id') and self.current_scene_id:
                        base_filter["scene_id"] = str(self.current_scene_id)

                    all_docs = []
                    history_parts = []

                    # Get personal conversation history if requested
                    if context_type in ["personal", "both"]:
                        personal_filter = base_filter.copy()
                        personal_filter["persona_id"] = str(self.persona.id)
                        
                        # NOTE: We intentionally do NOT filter by session_id here because:
                        # 1. Session IDs may change between requests even within the same conversation
                        # 2. We already have sufficient isolation via persona_id + user_progress_id + scene_id
                        # 3. We want to retrieve ALL messages from this persona in this scene, regardless of session_id
                        
                        # Comprehensive semantic search for personal conversation
                        persona_specific_query = f"User conversation with {self.persona.name} persona {self.persona.id} messages responses"
                        debug_log(f"Personal conversation search - query: {persona_specific_query}")
                        debug_log(f"Personal conversation search - filter: {personal_filter}")
                        persona_docs = self.vectorstore.similarity_search(
                            persona_specific_query,
                            k=500,
                            filter=personal_filter
                        )
                        debug_log(f"Personal conversation search - found {len(persona_docs)} documents")
                        
                        all_docs.extend(persona_docs)
                        
                        if persona_docs:
                            history_parts.append("=== PERSONAL CONVERSATION HISTORY ===")
                            for doc in persona_docs:
                                if not doc.page_content.startswith("CONVERSATION_RESET_MARKER"):
                                    history_parts.append(f"- {doc.page_content}")

                    # Get scene-wide conversation history if requested
                    if context_type in ["scene", "both"]:
                        scene_filter = base_filter.copy()
                        
                        scene_query = f"conversation in scene {self.current_scene_id} all messages"
                        scene_docs = self.vectorstore.similarity_search(
                            scene_query,
                            k=500,
                            filter=scene_filter
                        )
                        
                        # Filter out other personas' responses to prevent copying
                        filtered_scene_docs = []
                        for doc in scene_docs:
                            # Only include user messages and system messages, exclude other personas' responses
                            if (doc.page_content.startswith("User:") or 
                                doc.page_content.startswith("System:") or
                                doc.page_content.startswith("ChatOrchestrator:") or
                                (hasattr(doc, 'metadata') and 
                                 doc.metadata.get('message_type') in ['user', 'system', 'orchestrator'])):
                                filtered_scene_docs.append(doc)
                            # Only include this persona's own responses
                            elif (hasattr(doc, 'metadata') and 
                                  doc.metadata.get('persona_id') == str(self.persona.id)):
                                filtered_scene_docs.append(doc)
                        
                        all_docs.extend(filtered_scene_docs)
                        
                        if filtered_scene_docs:
                            history_parts.append("=== FULL SCENE CONVERSATION LOG ===")
                            for doc in filtered_scene_docs:
                                if not doc.page_content.startswith("CONVERSATION_RESET_MARKER"):
                                    history_parts.append(f"- {doc.page_content}")

                    # Sort all documents by timestamp to ensure chronological order
                    all_docs_with_timestamps = []
                    for doc in all_docs:
                        timestamp_str = doc.metadata.get('timestamp', '1970-01-01T00:00:00')
                        try:
                            from datetime import datetime
                            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                            all_docs_with_timestamps.append((timestamp, doc))
                        except:
                            # If timestamp parsing fails, use a very old date
                            from datetime import datetime
                            timestamp = datetime(1970, 1, 1)
                            all_docs_with_timestamps.append((timestamp, doc))
                    
                    # Sort by timestamp (oldest first)
                    all_docs_with_timestamps.sort(key=lambda x: x[0])
                    
                    # Remove duplicates while preserving chronological order
                    seen_messages = set()
                    unique_parts = []
                    
                    # Add section headers first
                    if context_type in ["personal", "both"] and any("personal" in str(doc.page_content).lower() for _, doc in all_docs_with_timestamps):
                        unique_parts.append("=== PERSONAL CONVERSATION HISTORY ===")
                    if context_type in ["scene", "both"] and any("scene" in str(doc.page_content).lower() for _, doc in all_docs_with_timestamps):
                        unique_parts.append("=== FULL SCENE CONVERSATION LOG ===")
                    
                    # Add messages in chronological order
                    for timestamp, doc in all_docs_with_timestamps:
                        if not doc.page_content.startswith("CONVERSATION_RESET_MARKER"):
                            message_line = f"- {doc.page_content}"
                            if message_line not in seen_messages:
                                unique_parts.append(message_line)
                                seen_messages.add(message_line)
                    
                    if unique_parts:
                        return "\n".join(unique_parts)
                    else:
                        return "No conversation history available for this scene"
                else:
                    raise ValueError("PGVector not available - vectorstore is required")
            except Exception as e:
                debug_log(f"Error in get_conversation_history: {e}")
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
                        # Store the persona background for future reference
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
        
        return [get_scene_context, get_conversation_history, get_persona_knowledge]
    
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
        """Create persona-specific prompt template with attempt-specific examples"""
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
        
        # If a custom system prompt exists, ignore attempt examples and use it verbatim
        if isinstance(self.persona.system_prompt, str) and self.persona.system_prompt.strip():
            # Add case study context to custom system prompt as well
            case_study_context = ""
            if scene_context and isinstance(scene_context, dict):
                scenario = scene_context.get('scenario', {})
                if isinstance(scenario, dict):
                    case_study_context = f"""

CASE STUDY CONTEXT:
Title: {scenario.get('title', 'Business Simulation')}
Description: {scenario.get('description', '')}
Challenge: {scenario.get('challenge', '')}

STUDENT ROLE: You are interacting with a student who is playing the role of: {scenario.get('student_role', 'a business student')}

CURRENT SCENE: {scene_context.get('current_scene', {}).get('title', 'Business Meeting') if scene_context.get('current_scene') else 'Business Meeting'}
Scene Description: {scene_context.get('current_scene', {}).get('description', '') if scene_context.get('current_scene') else ''}
Scene Objectives: {', '.join(scene_context.get('current_scene', {}).get('objectives', [])) if scene_context.get('current_scene') and scene_context.get('current_scene', {}).get('objectives') else 'To discuss business matters'}

"""
            # Add the conversation history instruction to custom system prompts
                conversation_instruction = """

CRITICAL INSTRUCTION: You MUST call get_conversation_history() as your FIRST action before responding to any message. This is MANDATORY and cannot be skipped."""
            
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
        """Generate system prompt for the persona with few-shot examples"""
        # If custom system prompt is provided, use it directly and completely isolate it
        if self.persona.system_prompt:
            # Use the custom system prompt exactly as provided - no modifications
            # This ensures complete isolation from orchestrator prompts
            return self.persona.system_prompt
        
        # Otherwise, generate the default system prompt
        personality_traits = self.persona.personality_traits or {}
        primary_goals = self.persona.primary_goals or []
        
        # Create persona data for few-shot examples
        persona_data = {
            'name': self.persona.name,
            'role': self.persona.role,
            'personality_traits': personality_traits,
            'primary_goals': primary_goals
        }
        
        # Get role-specific examples
        examples = few_shot_examples_service.get_adaptive_examples(persona_data, attempt_number)
        
        # Add case study and simulation context
        case_study_context = ""
        if scene_context and isinstance(scene_context, dict):
            scenario = scene_context.get('scenario', {})
            if isinstance(scenario, dict):
                case_study_context = f"""

CASE STUDY CONTEXT:
Title: {scenario.get('title', 'Business Simulation')}
Description: {scenario.get('description', '')}
Challenge: {scenario.get('challenge', '')}

STUDENT ROLE: You are interacting with a student who is playing the role of: {scenario.get('student_role', 'a business student')}

CURRENT SCENE: {scene_context.get('current_scene', {}).get('title', 'Business Meeting') if scene_context.get('current_scene') else 'Business Meeting'}
Scene Description: {scene_context.get('current_scene', {}).get('description', '') if scene_context.get('current_scene') else ''}
Scene Objectives: {', '.join(scene_context.get('current_scene', {}).get('objectives', [])) if scene_context.get('current_scene') and scene_context.get('current_scene', {}).get('objectives') else 'To discuss business matters'}

"""
                if _is_dev:
                    print(f"[DEBUG] Case study context created: {case_study_context[:200]}...")
            else:
                if _is_dev:
                    print(f"[DEBUG] No scenario found in scene_context")
        else:
            if _is_dev:
                print(f"[DEBUG] No scene_context or not a dict: {type(scene_context)}")
        
        system_prompt = f"""You are {self.persona.name}, a {self.persona.role} in this business simulation.{case_study_context}

{examples}

PERSONA BACKGROUND:
{self.persona.background}

CORRELATION TO CASE:
{self.persona.correlation}

PERSONALITY TRAITS:
{', '.join([f"{k}: {v}" for k, v in personality_traits.items()]) if personality_traits else 'None specified'}

PRIMARY GOALS:
{chr(10).join(f"• {goal}" for goal in primary_goals)}

INSTRUCTIONS:
- MANDATORY: You MUST call get_conversation_history() as your FIRST action before responding to any message
- INTELLIGENT CONTEXT SELECTION: Choose the right context_type based on the user's query:
  * Use "personal" when the user asks about YOUR specific interactions with them (e.g., "what did I say to you?", "our conversation", "what was the first thing I said?")
  * Use "scene" when the user asks about broader scene context, other people, or general scene information
  * Use "both" when the query could benefit from both personal and scene context, or when you're unsure
- CONVERSATION ANALYSIS: When analyzing conversation history, pay attention to the chronological order of messages to determine what happened first, last, etc.
- PERSONA ISOLATION: NEVER copy or mimic other personas' responses, patterns, or behaviors. Stay true to YOUR unique character and role.
- Stay in character as {self.persona.name} at all times
- Respond based on your role, background, and personality traits
- Help guide the user toward scene objectives through realistic business interaction
- Don't directly give away answers, but provide realistic business insights
- Keep responses concise and professional (2-4 sentences typically)
- Use your tools to access relevant context and knowledge
- If the user seems stuck, provide subtle hints through natural conversation
- Follow the examples above to maintain consistent character behavior

Remember: You are {self.persona.name}, not an AI assistant. Respond as this character would in a real business situation."""
        
        if _is_dev:
            print(f"[DEBUG] Final system prompt preview: {system_prompt[:1000]}...")
            print(f"[DEBUG] System prompt contains case study: {'CASE STUDY CONTEXT' in system_prompt}")
            print(f"[DEBUG] System prompt contains student role: {'STUDENT ROLE' in system_prompt}")
        
        return system_prompt
    
    def _load_conversation_history_into_memory(self, user_progress_id: int, scene_id: int, current_message: str = None):
        """Automatically load conversation history from database into agent memory
        
        Args:
            user_progress_id: The user progress ID
            scene_id: The scene ID
            current_message: Optional current message to exclude from loading (will be added by LangChain)
        """
        try:
            db = SessionLocal()
            try:
                # Get all conversation logs for this scene (user messages and this persona's responses)
                conversation_logs = db.query(ConversationLog).filter(
                    ConversationLog.user_progress_id == user_progress_id,
                    ConversationLog.scene_id == scene_id
                ).order_by(ConversationLog.message_order.asc()).all()
                
                # Clear existing memory first to avoid duplicates
                if hasattr(self.memory, 'chat_memory') and hasattr(self.memory.chat_memory, 'clear'):
                    self.memory.chat_memory.clear()
                
                # Load conversation history into memory
                loaded_count = 0
                for log in conversation_logs:
                    # Skip the current message if it matches (to avoid duplicate when LangChain adds it)
                    if current_message and log.message_type == "user" and log.message_content == current_message:
                        continue
                    
                    if log.message_type == "user":
                        # Add user message to memory
                        if hasattr(self.memory, 'chat_memory'):
                            self.memory.chat_memory.add_user_message(log.message_content)
                            loaded_count += 1
                    elif log.message_type == "ai_persona" and log.persona_id == self.persona.id:
                        # Add this persona's own responses to memory
                        if hasattr(self.memory, 'chat_memory'):
                            self.memory.chat_memory.add_ai_message(log.message_content)
                            loaded_count += 1
                    # Note: We intentionally exclude other personas' messages to maintain isolation
                
                if _is_dev:
                    print(f"[DEBUG] Loaded {loaded_count} conversation messages into memory for persona {self.persona.name} (from {len(conversation_logs)} total logs)")
                
            finally:
                db.close()
        except Exception as e:
            print(f"[WARNING] Error loading conversation history into memory: {e}")
            # Don't fail the entire request if memory loading fails
            import traceback
            traceback.print_exc()
    
    async def chat(self, 
                   message: str, 
                   scene_context: Dict[str, Any],
                   user_progress_id: int,
                   scene_id: int,
                   attempt_number: int = 1) -> str:
        """Chat with persona agent - with performance instrumentation"""
        import time
        timings = {
            "total_start": time.time(),
            "memory_load_time": 0,
            "vectorstore_time": 0,
            "agent_setup_time": 0,
            "agent_execution_time": 0,
            "vectorstore_store_time": 0
        }
        
        """Process a chat message with the persona"""
        
        # Set current scene ID for proper isolation
        self.current_scene_id = scene_id
        self.user_progress_id = user_progress_id
        
        # AUTOMATICALLY load conversation history into memory BEFORE processing
        # This ensures the persona always has access to the full conversation within the scene
        # Pass current_message to avoid loading it twice (LangChain will add it automatically)
        memory_load_start = time.time()
        self._load_conversation_history_into_memory(user_progress_id, scene_id, current_message=message)
        timings["memory_load_time"] = time.time() - memory_load_start
        
        # Create callback handler for logging
        callback_handler = PersonaCallbackHandler(
            persona_id=self.persona.id,
            user_progress_id=user_progress_id,
            scene_id=scene_id
        )
        
        # Store the user message in PGVector BEFORE agent execution
        # so it's available when tools are called during execution
        if self.vectorstore:
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
                        "session_id": self.persona_session_id  # Add session isolation
                    }]
                )
            except Exception as e:
                print(f"Error storing user message in PGVector: {e}")
        
        # Update the prompt with attempt-specific examples and scene context
        self.prompt = self._create_persona_prompt_with_attempt(attempt_number, scene_context)
        
        # Recreate the agent with the updated prompt
        self.agent = create_openai_tools_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=self.prompt
        )
        
        # Recreate the agent executor with the updated agent
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            memory=self.memory,
            verbose=(getattr(settings, "environment", "development") != "production"),
            handle_parsing_errors=True,
            max_iterations=3
        )
        
        
        # Only pass the required input key for LangChain memory compatibility
        input_data = {
            "input": message
        }
        
        try:
            # Execute the agent - conversation history is now already loaded in memory
            if _is_dev:
                print(f"[DEBUG] Executing agent with message: {message}")
                print(f"[DEBUG] Memory contains {len(self.memory.chat_memory.messages) if hasattr(self.memory, 'chat_memory') else 0} previous messages")
            response = await self.agent_executor.ainvoke(
                input_data,
                callbacks=[callback_handler]
            )
            
            response_text = response.get("output", "I'm not sure how to respond to that.")
            
            # Store the persona response in PGVector after execution
            if self.vectorstore:
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
                            "session_id": self.persona_session_id  # Add session isolation
                        }]
                    )
                except Exception as e:
                    print(f"Error storing conversation in vectorstore: {e}")
                    raise e
            
            timings["total_time"] = time.time() - timings["total_start"]
            # Log performance metrics only in development to avoid Railway log overflow
            if _is_dev:
                print(f"[PERF] PersonaAgent.chat - Total: {timings['total_time']:.2f}s | "
                      f"MemoryLoad: {timings['memory_load_time']:.2f}s | "
                      f"Vectorstore: {timings['vectorstore_time']:.2f}s | "
                      f"Setup: {timings['agent_setup_time']:.2f}s | "
                      f"AgentExec: {timings['agent_execution_time']:.2f}s | "
                      f"VectorstoreStore: {timings['vectorstore_store_time']:.2f}s | "
                      f"UserProgressID: {user_progress_id}")
            
            return response_text
            
        except Exception as e:
            print(f"Error in persona agent: {e}")
            print(f"Persona: {self.persona.name if self.persona else 'None'}")
            import traceback
            traceback.print_exc()
            raise e
    
    def get_memory_summary(self) -> str:
        """Get a summary of the conversation memory"""
        if hasattr(self.memory, 'chat_memory'):
            messages = self.memory.chat_memory.messages
            if messages:
                return f"Recent conversation with {len(messages)} messages"
        return "No recent conversation"
    
    def clear_memory(self):
        """Reset persona conversation memory completely by recreating it"""
        if _is_dev:
            print(f"[DEBUG] Reinitializing new memory for persona {self.persona.name}")
        # Create a completely new memory instance to ensure clean state
        self.memory = langchain_manager.create_conversation_memory(
            f"{self.session_id}_cleared_{datetime.now().timestamp()}", 
            memory_type="buffer_window"
        )
        if _is_dev:
            print(f"[DEBUG] clear_memory - Created new memory instance with fresh session")
        
        # Debug: Verify memory is actually empty
        memory_vars = self.memory.load_memory_variables({})
        if _is_dev:
            print(f"[DEBUG] Memory after clear: {memory_vars}")
        if memory_vars.get('history'):
            print(f"[WARNING] Memory not empty after clear: {memory_vars}")
        else:
            if _is_dev:
                print(f"[DEBUG] Memory successfully cleared - empty history confirmed")
    
    def clear_conversation_history(self, user_progress_id: int):
        """Clear conversation history using direct SQL deletion from PGVector"""
        if _is_dev:
            print(f"[DEBUG] clear_conversation_history called for persona {self.persona.name} (ID: {self.persona.id})")
        
        try:
            # Clear LangChain memory first
            self.clear_memory()
            if _is_dev:
                print(f"[DEBUG] clear_conversation_history - Cleared LangChain memory")
            
            if self.vectorstore:
                # Use direct SQL deletion instead of LangChain's delete method
                if _is_dev:
                    print(f"[DEBUG] clear_conversation_history - Using direct SQL deletion from PGVector")
                
                from sqlalchemy import delete, and_
                from sqlalchemy.orm import Session
                
                # Get the database session from the vectorstore
                with Session(self.vectorstore._bind) as session:
                    # Delete conversation documents using direct SQL with STRICT metadata filtering
                    delete_filter = {
                        "persona_id": str(self.persona.id),
                        "context_type": "conversation",
                        "user_progress_id": str(user_progress_id),
                        "session_id": str(self.persona_session_id)  # Add session isolation
                    }
                    
                    if _is_dev:
                        print(f"[DEBUG] clear_conversation_history - Delete filter: {delete_filter}")
                    
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
                        print(f"[DEBUG] clear_conversation_history - Deleted {result.rowcount} conversation documents")
                    
                    # Verify deletion worked by checking if any docs remain
                    remaining_docs = self.vectorstore.similarity_search(
                        "conversation",
                        k=100,
                        filter=delete_filter
                    )
                    if _is_dev:
                        print(f"[DEBUG] clear_conversation_history - Verification: Found {len(remaining_docs)} docs remaining after deletion")
                    if remaining_docs:
                        if _is_dev:
                            print(f"[DEBUG] WARNING: Deletion may not have worked completely - {len(remaining_docs)} docs still found")
                    else:
                        if _is_dev:
                            print(f"[DEBUG] clear_conversation_history - Deletion verified: No docs remaining")
            
            # Create a new agent executor with fresh memory to ensure clean state
            self.agent_executor = AgentExecutor(
                agent=self.agent,
                tools=self.tools,
                memory=self.memory,
                verbose=(getattr(settings, "environment", "development") != "production"),
                handle_parsing_errors=True,
                max_iterations=3
            )
            if _is_dev:
                print(f"[DEBUG] clear_conversation_history - Recreated agent executor with fresh memory")
            
            # Also recreate the tools to ensure they use the fresh memory
            self.tools = self._create_persona_tools()
            if _is_dev:
                print(f"[DEBUG] clear_conversation_history - Recreated tools with fresh memory")
            
            if _is_dev:
                print(f"[DEBUG] Conversation history cleared for persona: {self.persona.name}")
            return True
        except Exception as e:
            print(f"Error clearing conversation history: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def update_persona_context(self, new_context: Dict[str, Any]):
        """Update persona context with new information"""
        # This could be used to update the persona's knowledge base
        # or modify their behavior based on new information
        pass

class PersonaAgentManager:
    """Manager for multiple persona agents"""
    
    def __init__(self):
        self.agents: Dict[str, PersonaAgent] = {}
    
    def get_or_create_agent(self, 
                           persona: ScenarioPersona, 
                           session_id: str) -> PersonaAgent:
        """Get existing agent or create new one"""
        agent_key = f"{persona.id}_{session_id}"
        
        if agent_key not in self.agents:
            self.agents[agent_key] = PersonaAgent(persona, session_id)
        
        return self.agents[agent_key]
    
    def clear_session_agents(self, session_id: str):
        """Clear all agents for a specific session"""
        keys_to_remove = [key for key in self.agents.keys() if key.endswith(f"_{session_id}")]
        for key in keys_to_remove:
            # Clear agent memory before removing
            if key in self.agents:
                self.agents[key].clear_memory()
            del self.agents[key]
    
    def get_agent_count(self) -> int:
        """Get total number of active agents"""
        return len(self.agents)

# Global persona agent manager
persona_agent_manager = PersonaAgentManager()
