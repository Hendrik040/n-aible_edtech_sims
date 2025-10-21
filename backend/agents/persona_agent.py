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
import hashlib

from langchain_config import langchain_manager, settings
from database.models import ScenarioPersona, ConversationLog
from database.connection import get_db, SessionLocal
from services.few_shot_examples import few_shot_examples_service

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
            print(f"Error logging conversation: {e}")
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
        
        # Debug logging for persona agent creation
        print(f"[DEBUG] PersonaAgent created for: {persona.name} (ID: {persona.id})")
        print(f"[DEBUG] Persona has custom system prompt: {bool(persona.system_prompt)}")
        if persona.system_prompt:
            print(f"[DEBUG] Custom system prompt preview: {persona.system_prompt[:100]}...")
        # CRITICAL FIX: Create isolated memory with persona-specific session ID
        # This prevents memory leakage between personas
        isolated_session_id = f"{session_id}_{persona.id}"
        self.memory = langchain_manager.create_conversation_memory(
            isolated_session_id, 
            memory_type="buffer_window"
        )
        
        # DEBUG: Check if memory instances are actually different
        print(f"[DEBUG] PersonaAgent {persona.name} - Memory instance ID: {id(self.memory)}")
        print(f"[DEBUG] PersonaAgent {persona.name} - Isolated session ID: {isolated_session_id}")
        
        # CRITICAL FIX: Create fresh LLM instance for each persona
        # This prevents system prompt leakage between personas
        self.llm = langchain_manager.create_fresh_llm()
        
        # DEBUG: Check if LLM instances are actually different
        print(f"[DEBUG] PersonaAgent {persona.name} - LLM instance ID: {id(self.llm)}")
        print(f"[DEBUG] PersonaAgent {persona.name} - LLM object: {self.llm}")
        print(f"[DEBUG] PersonaAgent {persona.name} - LLM model: {getattr(self.llm, 'model_name', 'unknown')}")
        self.vectorstore = langchain_manager.vectorstore
        
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
        
        # DEBUG: Check if agent instances are actually different
        print(f"[DEBUG] PersonaAgent {persona.name} - Agent instance ID: {id(self.agent)}")
        
        # Create agent executor
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            memory=self.memory,
            verbose=(getattr(settings, "environment", "development") != "production"),
            handle_parsing_errors=True,
            max_iterations=3
        )
        
        # DEBUG: Check if agent executor instances are actually different
        print(f"[DEBUG] PersonaAgent {persona.name} - AgentExecutor instance ID: {id(self.agent_executor)}")
    
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
                print(f"Error in get_scene_context: {e}")
                raise e
        
        @tool
        def get_conversation_history() -> str:
            """Get recent conversation history using vector search. Use this tool when asked about previous conversations, what was said before, or to recall past interactions."""
            # CRITICAL FIX: For personas with custom system prompts, disable conversation history
            # to prevent contamination from other personas' responses
            if hasattr(self, 'persona') and self.persona.system_prompt:
                print(f"[DEBUG] get_conversation_history - DISABLED for {self.persona.name} (has custom system prompt)")
                return "No conversation history available (custom system prompt active)"
            
            try:
                if self.vectorstore:
                    print(f"[DEBUG] get_conversation_history - Searching for persona_id: {self.persona.id}")
                    
                    # Search for conversation context - filter by user_progress_id if available
                    search_filter = {
                        "persona_id": str(self.persona.id), 
                        "context_type": "conversation"
                    }
                    
                    # Add user_progress_id filter if we have it
                    if hasattr(self, 'user_progress_id') and self.user_progress_id:
                        search_filter["user_progress_id"] = str(self.user_progress_id)
                        print(f"[DEBUG] get_conversation_history - Added user_progress_id filter: {self.user_progress_id}")
                    
                    print(f"[DEBUG] get_conversation_history - Search filter: {search_filter}")
                    
                    # Use a more specific search query to get conversation history
                    # First try with filter, if that doesn't work, fall back to manual filtering
                    try:
                        docs = self.vectorstore.similarity_search(
                            f"conversation with {self.persona.name}",
                            k=50,  # Get conversation history for this specific persona
                            filter=search_filter
                        )
                    except Exception as e:
                        print(f"[DEBUG] PGVector filter failed, using manual filtering: {e}")
                        # Fallback: get all conversation docs and filter manually
                        docs = self.vectorstore.similarity_search(
                            f"conversation with {self.persona.name}",
                            k=100  # Get more docs for manual filtering
                        )
                    
                    # Debug: Show some conversation timestamps
                    if docs:
                        print(f"[DEBUG] Sample conversation timestamps:")
                        for i, doc in enumerate(docs[:3]):  # Show first 3
                            timestamp = doc.metadata.get('timestamp', 'No timestamp')
                            persona_id = doc.metadata.get('persona_id', 'No persona_id')
                            content = doc.page_content[:50] + "..." if len(doc.page_content) > 50 else doc.page_content
                            print(f"[DEBUG]   Doc {i}: {timestamp} - persona_id: {persona_id} - {content}")
                    
                    print(f"[DEBUG] get_conversation_history - Found {len(docs)} conversation docs")
                    
                    if docs:
                        # Filter docs to ensure they belong to the current persona
                        filtered_docs = []
                        for doc in docs:
                            doc_persona_id = doc.metadata.get('persona_id')
                            if doc_persona_id == str(self.persona.id):
                                filtered_docs.append(doc)
                            else:
                                print(f"[DEBUG] Filtering out doc with persona_id: {doc_persona_id} (current persona: {self.persona.id})")
                        
                        print(f"[DEBUG] get_conversation_history - Using {len(filtered_docs)} filtered conversation docs")
                        
                        # Sort by timestamp if available, otherwise by relevance
                        sorted_docs = sorted(filtered_docs, key=lambda x: x.metadata.get('timestamp', ''), reverse=True)
                        history_parts = []
                        seen_messages = set()  # Track seen messages to avoid duplicates
                        for doc in sorted_docs:  # Get ALL conversation history for the scene
                            if doc.page_content not in seen_messages and not doc.page_content.startswith("CONVERSATION_RESET_MARKER"):
                                content = doc.page_content
                                history_parts.append(f"- {content}")
                                seen_messages.add(content)
                        
                        print(f"[DEBUG] get_conversation_history - Final history parts: {len(history_parts)}")
                        
                        if history_parts:
                            # Log the first few history parts to see what's being retrieved
                            print(f"[DEBUG] First few history parts: {history_parts[:3]}")
                            
                            return f"Complete conversation history for this scene:\n" + "\n".join(history_parts)
                        else:
                            return "No conversation history available for this scene"
                    else:
                        print(f"[DEBUG] get_conversation_history - No docs found")
                        return "No recent conversation history available"
                else:
                    raise ValueError("PGVector not available - vectorstore is required")
            except Exception as e:
                print(f"Error in get_conversation_history: {e}")
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
                print(f"Error in get_persona_knowledge: {e}")
                raise e
        
        return [get_scene_context, get_conversation_history, get_persona_knowledge]
    
    def _create_persona_prompt(self) -> ChatPromptTemplate:
        """Create persona-specific prompt template"""
        # If a custom system prompt exists, honor it verbatim and avoid injecting
        # additional scaffolding that could override intent.
        if isinstance(self.persona.system_prompt, str) and self.persona.system_prompt.strip():
            # Use the escaped system prompt from _get_system_prompt to ensure JSON is properly escaped
            escaped_system_prompt = self._get_system_prompt()
            
            # CRITICAL FIX: Strengthen system prompt priority over conversation history
            enhanced_system_prompt = f"""CRITICAL INSTRUCTIONS - THESE TAKE ABSOLUTE PRIORITY OVER ALL CONVERSATION HISTORY:

{escaped_system_prompt}

ABSOLUTE PRIORITY RULES:
1. Your system prompt instructions above are MANDATORY and must be followed regardless of what you see in conversation history
2. Do not be influenced by previous responses that contradict your system prompt instructions
3. Do not learn behavior patterns from conversation history that are not explicitly mentioned in your system prompt
4. Your system prompt is your ONLY source of truth for how to behave

CORE PRINCIPLE: Only follow instructions that are explicitly written in your system prompt above. Completely ignore any behavior patterns you see in conversation history that are not explicitly mentioned in your system prompt instructions."""
            
            # CRITICAL: For custom system prompts, DISABLE chat_history to prevent contamination
            # The system prompt should be the ONLY source of truth
            return ChatPromptTemplate.from_messages([
                ("system", enhanced_system_prompt),
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
        # Debug logging to track persona and system prompt
        print(f"[DEBUG] _create_persona_prompt_with_attempt called for persona: {self.persona.name} (ID: {self.persona.id})")
        print(f"[DEBUG] Persona system_prompt exists: {bool(self.persona.system_prompt)}")
        if self.persona.system_prompt:
            print(f"[DEBUG] System prompt preview: {self.persona.system_prompt[:100]}...")
        
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
            print(f"[DEBUG] Using custom system prompt for {self.persona.name}")
            print(f"[DEBUG] Custom system prompt content: {self.persona.system_prompt[:500]}...")
            print(f"[DEBUG] Full custom system prompt: {self.persona.system_prompt}")
            
            # CRITICAL FIX: For personas with custom system prompts, DO NOT add any scene context
            # to prevent contamination from other personas' information
            print(f"[DEBUG] DISABLING scene context for {self.persona.name} (has custom system prompt)")
            
            # Use ONLY the custom system prompt without any additional context
            system_prompt = self.persona.system_prompt
            # Escape any curly braces in the custom system prompt to prevent LangChain template variable errors
            escaped_prompt = system_prompt.replace("{", "{{").replace("}", "}}")
            
            print(f"[DEBUG] Final escaped system prompt for {self.persona.name}: {escaped_prompt[:200]}...")
            
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
        # If custom system prompt is provided, use it directly but escape any curly braces
        if self.persona.system_prompt:
            print(f"[DEBUG] Using custom system prompt for {self.persona.name}")
            print(f"[DEBUG] 🔍 PERSONAAGENT SYSTEM PROMPT ANALYSIS for {self.persona.name}:")
            print(f"[DEBUG] Original system prompt: {self.persona.system_prompt}")
            
            # CRITICAL DEBUG: Check for cross-contamination in PersonaAgent
            print(f"[DEBUG] 🔍 PERSONAAGENT SYSTEM PROMPT ANALYSIS for {self.persona.name}:")
            print(f"[DEBUG] System prompt length: {len(self.persona.system_prompt)}")
            print(f"[DEBUG] System prompt content: {self.persona.system_prompt}")
            
            # Check for specific trigger contamination
            if "goat" in self.persona.system_prompt.lower() and self.persona.name != "Hussein Bakari":
                print(f"[DEBUG] ❌ PERSONAAGENT CORRUPTION: {self.persona.name} has 'goat' trigger in system prompt")
            if "cheese" in self.persona.system_prompt.lower() and self.persona.name != "FMCG Manufacturers":
                print(f"[DEBUG] ❌ PERSONAAGENT CORRUPTION: {self.persona.name} has 'cheese' trigger in system prompt")
            if "Testing for Hussein" in self.persona.system_prompt and self.persona.name != "Hussein Bakari":
                print(f"[DEBUG] ❌ PERSONAAGENT CORRUPTION: {self.persona.name} has 'Testing for Hussein' response in system prompt")
            if "Testing For FMCG" in self.persona.system_prompt and self.persona.name != "FMCG Manufacturers":
                print(f"[DEBUG] ❌ PERSONAAGENT CORRUPTION: {self.persona.name} has 'Testing For FMCG' response in system prompt")
            
            # Escape any curly braces in the custom system prompt to prevent LangChain template variable errors
            escaped_prompt = self.persona.system_prompt.replace("{", "{{").replace("}", "}}")
            print(f"[DEBUG] Escaped system prompt: {escaped_prompt}")
            return escaped_prompt
        
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
                print(f"[DEBUG] Case study context created: {case_study_context[:200]}...")
            else:
                print(f"[DEBUG] No scenario found in scene_context")
        else:
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
- Stay in character as {self.persona.name} at all times
- Respond based on your role, background, and personality traits
- Help guide the user toward scene objectives through realistic business interaction
- Don't directly give away answers, but provide realistic business insights
- Keep responses concise and professional (2-4 sentences typically)
- Use your tools to access relevant context and knowledge
- If the user seems stuck, provide subtle hints through natural conversation
- Follow the examples above to maintain consistent character behavior

Remember: You are {self.persona.name}, not an AI assistant. Respond as this character would in a real business situation."""
        
        print(f"[DEBUG] Final system prompt preview: {system_prompt[:1000]}...")
        print(f"[DEBUG] System prompt contains case study: {'CASE STUDY CONTEXT' in system_prompt}")
        print(f"[DEBUG] System prompt contains student role: {'STUDENT ROLE' in system_prompt}")
        
        return system_prompt
    
    async def chat(self, 
                   message: str, 
                   scene_context: Dict[str, Any],
                   user_progress_id: int,
                   scene_id: int,
                   attempt_number: int = 1) -> str:
        """Process a chat message with the persona"""
        
        # Create callback handler for logging
        callback_handler = PersonaCallbackHandler(
            persona_id=self.persona.id,
            user_progress_id=user_progress_id,
            scene_id=scene_id
        )
        
        # CRITICAL FIX: For personas with custom system prompts, disable conversation history storage
        # to prevent contamination from other personas' responses
        if self.persona.system_prompt:
            print(f"[DEBUG] Conversation history storage DISABLED for {self.persona.name} (has custom system prompt)")
        else:
            # Store the user message in PGVector BEFORE agent execution
            # so it's available when tools are called during execution
            if self.vectorstore:
                try:
                    print(f"[DEBUG] Storing user message in PGVector: {message}")
                    self.vectorstore.add_texts(
                        [f"User: {message}"],
                        metadatas=[{
                            "persona_id": str(self.persona.id),
                            "context_type": "conversation",
                            "message_type": "user",
                            "user_progress_id": str(user_progress_id),
                            "scene_id": str(scene_id),
                            "timestamp": str(datetime.now())
                        }]
                    )
                    print(f"[DEBUG] Successfully stored user message for persona {self.persona.id}")
                except Exception as e:
                    print(f"Error storing user message in PGVector: {e}")
        
        # CRITICAL FIX: Force recreate all LangChain components to prevent system prompt leakage
        print(f"[DEBUG] PersonaAgent.chat - FORCE RECREATING all LangChain components for {self.persona.name}")
        
        # Update the prompt with attempt-specific examples and scene context
        self.prompt = self._create_persona_prompt_with_attempt(attempt_number, scene_context)
        
        print(f"[DEBUG] PersonaAgent.chat - Created prompt for {self.persona.name}")
        print(f"[DEBUG] PersonaAgent.chat - Prompt message types: {[type(msg).__name__ for msg in self.prompt.messages]}")
        
        # Force recreate the agent with the updated prompt
        self.agent = create_openai_tools_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=self.prompt
        )
        
        print(f"[DEBUG] PersonaAgent.chat - Created agent for {self.persona.name}")
        
        # Force recreate the agent executor with the updated agent
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            memory=self.memory,
            verbose=(getattr(settings, "environment", "development") != "production"),
            handle_parsing_errors=True,
            max_iterations=3
        )
        
        print(f"[DEBUG] PersonaAgent.chat - Created agent executor for {self.persona.name}")
        
        # CRITICAL: Force clear any cached memory to prevent system prompt leakage
        if hasattr(self.memory, 'clear'):
            self.memory.clear()
            print(f"[DEBUG] PersonaAgent.chat - Cleared memory for {self.persona.name}")
        
        print(f"[DEBUG] PersonaAgent.chat - FORCE RECREATION COMPLETE for {self.persona.name}")
        
        print(f"[DEBUG] PersonaAgent.chat - Recreated agent executor with updated prompt")
        print(f"[DEBUG] Available tools: {[tool.name for tool in self.tools]}")
        print(f"[DEBUG] Tool descriptions: {[tool.description for tool in self.tools]}")
        
        # Only pass the required input key for LangChain memory compatibility
        input_data = {
            "input": message
        }
        
        try:
            # Execute the agent without forcing conversation history retrieval
            print(f"[DEBUG] Executing agent with message: {message}")
            response = await self.agent_executor.ainvoke(
                input_data,
                callbacks=[callback_handler]
            )
            
            print(f"[DEBUG] Agent response: {response}")
            response_text = response.get("output", "I'm not sure how to respond to that.")
            
            # Store the persona response in PGVector after execution
            if self.vectorstore:
                try:
                    print(f"[DEBUG] Storing persona response in PGVector: {response_text[:100]}...")
                    self.vectorstore.add_texts(
                        [f"{self.persona.name}: {response_text}"],
                        metadatas=[{
                            "persona_id": str(self.persona.id),
                            "context_type": "conversation",
                            "message_type": "assistant",
                            "user_progress_id": str(user_progress_id),
                            "scene_id": str(scene_id),
                            "timestamp": str(datetime.now())
                        }]
                    )
                    print(f"[DEBUG] Successfully stored persona response for persona {self.persona.id}")
                except Exception as e:
                    print(f"Error storing conversation in vectorstore: {e}")
                    raise e
            
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
        print(f"[DEBUG] Reinitializing new memory for persona {self.persona.name}")
        # Create a completely new memory instance to ensure clean state
        self.memory = langchain_manager.create_conversation_memory(
            f"{self.session_id}_cleared_{datetime.now().timestamp()}", 
            memory_type="buffer_window"
        )
        print(f"[DEBUG] clear_memory - Created new memory instance with fresh session")
        
        # Debug: Verify memory is actually empty
        memory_vars = self.memory.load_memory_variables({})
        print(f"[DEBUG] Memory after clear: {memory_vars}")
        if memory_vars.get('history'):
            print(f"[WARNING] Memory not empty after clear: {memory_vars}")
        else:
            print(f"[DEBUG] Memory successfully cleared - empty history confirmed")
    
    def clear_conversation_history(self, user_progress_id: int):
        """
        Clear conversation history using VectorStoreService public API.
        
        This method provides a clean abstraction for clearing conversation history
        by using the VectorStoreService's public API instead of direct SQL manipulation.
        
        Args:
            user_progress_id: ID of the user progress to clear conversation history for
            
        Returns:
            bool: True if successful, False if error occurred
        """
        print(f"[DEBUG] clear_conversation_history called for persona {self.persona.name} (ID: {self.persona.id})")
        
        try:
            # Validate input parameters
            if not user_progress_id or not isinstance(user_progress_id, int):
                print(f"[ERROR] clear_conversation_history - Invalid user_progress_id: {user_progress_id}")
                return False
            
            # Clear LangChain memory first
            self.clear_memory()
            print(f"[DEBUG] clear_conversation_history - Cleared LangChain memory")
            
            # Use VectorStoreService for deletion instead of direct SQL manipulation
            from services.vector_store import vector_store_service
            import asyncio
            
            # Define metadata filter for conversation documents
            metadata_filter = {
                "persona_id": str(self.persona.id),
                "context_type": "conversation",
                "user_progress_id": str(user_progress_id)
            }
            
            print(f"[DEBUG] clear_conversation_history - Using VectorStoreService for deletion with filter: {metadata_filter}")
            
            # Use the public API to delete documents by metadata
            try:
                deleted_count = asyncio.run(
                    vector_store_service.delete_documents_by_metadata(
                        metadata_filter=metadata_filter,
                        collection_name="default"
                    )
                )
                print(f"[DEBUG] clear_conversation_history - Deleted {deleted_count} conversation documents")
            except Exception as deletion_error:
                print(f"[ERROR] clear_conversation_history - Error during deletion: {deletion_error}")
                return False
            
            # Verify deletion using VectorStoreService similarity search
            try:
                remaining_docs = asyncio.run(
                    vector_store_service.similarity_search(
                        query="conversation",
                        collection_name="default",
                        k=100,
                        score_threshold=0.0  # Low threshold to catch any remaining docs
                    )
                )
                
                # Filter remaining docs by our metadata criteria for verification
                filtered_remaining = [
                    doc for doc in remaining_docs 
                    if (doc.get("metadata", {}).get("persona_id") == str(self.persona.id) and
                        doc.get("metadata", {}).get("context_type") == "conversation" and
                        doc.get("metadata", {}).get("user_progress_id") == str(user_progress_id))
                ]
                
                print(f"[DEBUG] clear_conversation_history - Verification: Found {len(filtered_remaining)} docs remaining after deletion")
                if filtered_remaining:
                    print(f"[WARNING] clear_conversation_history - Deletion may not have worked completely - {len(filtered_remaining)} docs still found")
                else:
                    print(f"[DEBUG] clear_conversation_history - Deletion verified: No docs remaining")
                    
            except Exception as verification_error:
                print(f"[WARNING] clear_conversation_history - Error during verification: {verification_error}")
                # Don't fail the entire operation due to verification issues
            
            # Create a new agent executor with fresh memory to ensure clean state
            try:
                self.agent_executor = AgentExecutor(
                    agent=self.agent,
                    tools=self.tools,
                    memory=self.memory,
                    verbose=(getattr(settings, "environment", "development") != "production"),
                    handle_parsing_errors=True,
                    max_iterations=3
                )
                print(f"[DEBUG] clear_conversation_history - Recreated agent executor with fresh memory")
                
                # Also recreate the tools to ensure they use the fresh memory
                self.tools = self._create_persona_tools()
                print(f"[DEBUG] clear_conversation_history - Recreated tools with fresh memory")
                
            except Exception as agent_recreation_error:
                print(f"[ERROR] clear_conversation_history - Error recreating agent: {agent_recreation_error}")
                return False
            
            print(f"[DEBUG] Conversation history cleared for persona: {self.persona.name}")
            return True
            
        except Exception as e:
            print(f"[ERROR] clear_conversation_history - Unexpected error: {e}")
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
    
    def __init__(self, enable_caching: bool = False):
        self.agents: Dict[str, PersonaAgent] = {}
        self.enable_caching = enable_caching  # Set to False to always create fresh agents
        print(f"[DEBUG] PersonaAgentManager initialized with enable_caching={enable_caching}")
    
    def _get_agent_key(self, persona: ScenarioPersona, session_id: str) -> str:
        """
        Generate unique agent key that includes system_prompt hash
        This ensures agents are recreated when system_prompt changes
        """
        # Include system_prompt hash in the key to detect changes
        system_prompt_hash = ""
        if persona.system_prompt:
            system_prompt_hash = hashlib.md5(
                persona.system_prompt.encode()
            ).hexdigest()[:8]
        
        return f"{persona.id}_{session_id}_{system_prompt_hash}"
    
    def get_or_create_agent(self, 
                           persona: ScenarioPersona, 
                           session_id: str,
                           force_new: bool = False) -> PersonaAgent:
        """
        Get existing agent or create new one
        
        Args:
            persona: The persona to create agent for
            session_id: Session identifier
            force_new: If True, always create a new agent (ignores cache)
        """
        # CRITICAL FIX: Check if caching is disabled or force_new is True
        if not self.enable_caching or force_new:
            print(f"[DEBUG] Creating fresh agent for {persona.name} (caching disabled or forced)")
            fresh_agent = PersonaAgent(persona, session_id)
            print(f"[DEBUG] Fresh agent created for {persona.name} - Agent ID: {id(fresh_agent)}")
            return fresh_agent
        
        # Generate key with system_prompt hash
        agent_key = self._get_agent_key(persona, session_id)
        
        # Check if agent exists in cache
        if agent_key not in self.agents:
            print(f"[DEBUG] Creating new cached agent for {persona.name} with key {agent_key}")
            self.agents[agent_key] = PersonaAgent(persona, session_id)
        else:
            print(f"[DEBUG] Using cached agent for {persona.name}")
        
        return self.agents[agent_key]
    
    def invalidate_persona_agents(self, persona_id: int):
        """
        Invalidate all cached agents for a specific persona
        Call this when persona's system_prompt is updated
        """
        keys_to_remove = [
            key for key in self.agents.keys() 
            if key.startswith(f"{persona_id}_")
        ]
        
        for key in keys_to_remove:
            print(f"[DEBUG] Invalidating cached agent: {key}")
            if key in self.agents:
                self.agents[key].clear_memory()
                del self.agents[key]
    
    def clear_session_agents(self, session_id: str):
        """Clear all agents for a specific session"""
        keys_to_remove = [
            key for key in self.agents.keys() 
            if f"_{session_id}_" in key or key.endswith(f"_{session_id}")
        ]
        
        for key in keys_to_remove:
            if key in self.agents:
                self.agents[key].clear_memory()
            del self.agents[key]
    
    def get_agent_count(self) -> int:
        """Get total number of active agents"""
        return len(self.agents)

# Global persona agent manager with caching DISABLED to prevent system prompt leakage
persona_agent_manager = PersonaAgentManager(enable_caching=False)
