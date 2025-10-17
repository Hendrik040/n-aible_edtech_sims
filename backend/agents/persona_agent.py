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
    
    def __init__(self, persona: ScenarioPersona, session_id: str):
        self.persona = persona
        self.session_id = session_id
        self.memory = langchain_manager.create_conversation_memory(
            session_id, 
            memory_type="buffer_window"
        )
        self.llm = langchain_manager.llm
        self.vectorstore = langchain_manager.vectorstore
        
        # Create persona-specific tools
        self.tools = self._create_persona_tools()
        
        # Create agent prompt
        self.prompt = self._create_persona_prompt()
        
        # Create agent
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
                print(f"Error in get_scene_context: {e}")
                raise e
        
        @tool
        def get_conversation_history() -> str:
            """Get recent conversation history using vector search"""
            try:
                if self.vectorstore:
                    # Search for recent conversation context
                    docs = self.vectorstore.similarity_search(
                        "conversation history",
                        k=5,
                        filter={"persona_id": str(self.persona.id), "context_type": "conversation"}
                    )
                    
                    if docs:
                        history_parts = []
                        for doc in docs:
                            history_parts.append(f"- {doc.page_content}")
                        return f"Recent conversation context:\n" + "\n".join(history_parts)
                    else:
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
            def json_serializer(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
            
            scene_context_str = f"\n\nCURRENT SCENE CONTEXT:\n{json.dumps(scene_context, default=json_serializer, indent=2)}"
        
        # If a custom system prompt exists, ignore attempt examples and use it verbatim
        if isinstance(self.persona.system_prompt, str) and self.persona.system_prompt.strip():
            system_prompt = self.persona.system_prompt + scene_context_str
            # For custom system prompts, don't escape anything - let LangChain handle it
            # The template variables are handled by the ChatPromptTemplate structure
            escaped_prompt = system_prompt
            
            return ChatPromptTemplate.from_messages([
                ("system", escaped_prompt),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad")
            ])
        
        # Default with attempt-specific few-shot only when no custom prompt provided
        system_prompt = self._get_system_prompt(attempt_number) + scene_context_str
        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
    
    def _get_system_prompt(self, attempt_number: int = 1) -> str:
        """Generate system prompt for the persona with few-shot examples"""
        # If custom system prompt is provided, use it directly
        if self.persona.system_prompt:
            print(f"[DEBUG] Using custom system prompt for {self.persona.name}")
            # Escape JSON content but preserve LangChain template variables
            import re
            escaped_prompt = self.persona.system_prompt
            
            # Find JSON objects and escape them, but preserve LangChain template variables
            # Use a more robust pattern that handles multiline JSON
            json_pattern = r'\{[^}]*"[^"]*"[^}]*\}'
            matches = re.findall(json_pattern, escaped_prompt, re.DOTALL)
            for match in matches:
                # Only escape if it's not a LangChain template variable
                if not any(var in match for var in ['{input}', '{chat_history}', '{agent_scratchpad}']):
                    escaped_match = match.replace("{", "{{").replace("}", "}}")
                    escaped_prompt = escaped_prompt.replace(match, escaped_match)
            
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
        
        system_prompt = f"""You are {self.persona.name}, a {self.persona.role} in this business simulation.

{examples}

PERSONA BACKGROUND:
{self.persona.background}

CORRELATION TO CASE:
{self.persona.correlation}

PERSONALITY TRAITS:
{json.dumps(personality_traits, indent=2)}

PRIMARY GOALS:
{chr(10).join(f"• {goal}" for goal in primary_goals)}

INSTRUCTIONS:
- Stay in character as {self.persona.name} at all times
- Respond based on your role, background, and personality traits
- Help guide the user toward scene objectives through realistic business interaction
- Don't directly give away answers, but provide realistic business insights
- Keep responses concise and professional (2-4 sentences typically)
- Use your tools to access relevant context and knowledge
- If the user seems stuck, provide subtle hints through natural conversation
- Follow the examples above to maintain consistent character behavior

Remember: You are {self.persona.name}, not an AI assistant. Respond as this character would in a real business situation."""
        
        # Escape curly braces in JSON content to prevent LangChain variable interpretation
        escaped_prompt = system_prompt
        if personality_traits:
            # Find and escape the JSON personality traits section
            import re
            json_pattern = r'PERSONALITY TRAITS:\s*\n(\{.*?\})'
            match = re.search(json_pattern, escaped_prompt, re.DOTALL)
            if match:
                json_content = match.group(1)
                escaped_json = json_content.replace("{", "{{").replace("}", "}}")
                escaped_prompt = escaped_prompt.replace(json_content, escaped_json)
        
        return escaped_prompt
    
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
        
        # Update the prompt with attempt-specific examples and scene context
        self.prompt = self._create_persona_prompt_with_attempt(attempt_number, scene_context)
        
        # Only pass the required input key for LangChain memory compatibility
        input_data = {
            "input": message
        }
        
        try:
            # Execute the agent
            response = await self.agent_executor.ainvoke(
                input_data,
                callbacks=[callback_handler]
            )
            
            response_text = response.get("output", "I'm not sure how to respond to that.")
            
            # Store conversation in PGVector for semantic search (if available)
            if self.vectorstore:
                try:
                    # Store the user message
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
                    
                    # Store the persona response
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
        """Clear the conversation memory"""
        if hasattr(self.memory, 'clear'):
            self.memory.clear()
    
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
