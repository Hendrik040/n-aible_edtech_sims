"""
Summarization Agent for AI Agent Education Platform
Handles conversation summarization and context management
"""

from typing import Dict, List, Any, Optional
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import BaseMessage, HumanMessage, AIMessage
from langchain.memory import ConversationSummaryBufferMemory
from langchain.text_splitter import RecursiveCharacterTextSplitter
import json
from datetime import datetime

from common.services.ai_gateway import langchain_manager
from common.services.simulation_helper.langchain_service import settings as langchain_settings
from common.config import get_settings
from common.db.models import ConversationLog

settings = get_settings()

import logging
debug_log = logging.getLogger(__name__).debug

# Note: vector_store_service removed - use langchain_manager.vectorstore directly if needed

class SummarizationAgent:
    """LangChain-based agent for conversation summarization and context management"""
    
    def __init__(self):
        self.llm = langchain_manager.llm
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=langchain_settings.chunk_size,
            chunk_overlap=langchain_settings.chunk_overlap
        )
        
        # Create tools
        self.tools = self._create_summarization_tools()
        
        # Create prompt
        self.prompt = self._create_summarization_prompt()
        
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
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=2
        )
    
    def _create_summarization_tools(self) -> List[BaseTool]:
        """Create tools for summarization operations"""
        from langchain.tools import tool
        
        # Create tool instances that can access self.llm
        summarize_tool = tool(self._summarize_conversation_tool)
        extract_tool = tool(self._extract_key_points_tool)
        learning_tool = tool(self._identify_learning_moments_tool)
        context_tool = tool(self._create_context_summary_tool)
        
        return [summarize_tool, extract_tool, learning_tool, context_tool]
    
    async def _summarize_conversation_tool(self, conversation_text: str) -> str:
        """Summarize a conversation while preserving key information"""
        try:
            prompt = f"""Please provide a concise summary of the following conversation while preserving key information, decisions made, and important context:

{conversation_text}

Summary should be:
- Clear and concise (2-3 sentences)
- Include key decisions or outcomes
- Preserve important context for future reference
- Maintain the educational value

Summary:"""
            
            response = await self.llm.ainvoke(prompt)
            return response.content
            
        except Exception as e:
            print(f"Error in summarize_conversation: {e}")
            return f"Conversation summary unavailable due to processing error. Original text length: {len(conversation_text)} words."
    
    async def _extract_key_points_tool(self, conversation_text: str) -> str:
        """Extract key points and decisions from conversation"""
        try:
            prompt = f"""Extract the key points and important decisions from this conversation:

{conversation_text}

Please identify:
- Key decisions made
- Important insights or realizations
- Action items or next steps
- Critical information for future reference

Format as a bulleted list of key points:"""
            
            response = await self.llm.ainvoke(prompt)
            return response.content
            
        except Exception as e:
            debug_log(f"Error in extract_key_points: {e}")
            return "Key points extraction unavailable due to processing error."
    
    async def _identify_learning_moments_tool(self, conversation_text: str) -> str:
        """Identify important learning moments and insights"""
        try:
            prompt = f"""Identify the most important learning moments and insights from this educational conversation:

{conversation_text}

Focus on:
- Moments where new understanding was gained
- Insights that could be applied to future situations
- Key lessons learned
- Breakthrough moments or realizations

Provide a structured analysis of the learning moments:"""
            
            response = await self.llm.ainvoke(prompt)
            return response.content
            
        except Exception as e:
            debug_log(f"Error in identify_learning_moments: {e}")
            return "Learning moments analysis unavailable due to processing error."
    
    async def _create_context_summary_tool(self, scene_context: str, persona_context: str) -> str:
        """Create a comprehensive context summary"""
        try:
            prompt = f"""Create a comprehensive context summary by combining the following scene and persona information:

SCENE CONTEXT:
{scene_context}

PERSONA CONTEXT:
{persona_context}

Please create a unified context summary that:
- Integrates both scene and persona information
- Highlights the key context elements
- Provides a clear understanding of the current situation
- Maintains important details for future reference

Comprehensive Context Summary:"""
            
            response = await self.llm.ainvoke(prompt)
            return response.content
            
        except Exception as e:
            print(f"Error in create_context_summary: {e}")
            return f"Context summary unavailable due to processing error. Scene context length: {len(scene_context)} chars, Persona context length: {len(persona_context)} chars."
    
    def _create_summarization_prompt(self) -> ChatPromptTemplate:
        """Create summarization prompt template"""
        return ChatPromptTemplate.from_messages([
            ("system", self._get_system_prompt()),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
    
    def _get_system_prompt(self) -> str:
        """Generate system prompt for summarization"""
        return """You are an expert summarization agent for educational conversations.

Your role is to:
1. Create concise, informative summaries of conversations
2. Extract key points, decisions, and learning moments
3. Preserve important context for future interactions
4. Identify patterns and insights in user behavior
5. Create context summaries for scene transitions

SUMMARIZATION PRINCIPLES:
- Preserve all important information and decisions
- Highlight key learning moments and insights
- Maintain context for future persona interactions
- Keep summaries concise but comprehensive
- Focus on educational value and progress

OUTPUT FORMAT:
Return your response as valid JSON only, with no additional text. Use this exact structure:
{
  "summary": "A concise summary of the conversation or content",
  "key_points": ["Point 1", "Point 2", "Point 3"],
  "learning_moments": ["Moment 1", "Moment 2"],
  "insights": ["Insight 1", "Insight 2"],
  "recommendations": ["Recommendation 1", "Recommendation 2"]
}

Use your tools to systematically analyze and summarize conversations."""
    
    async def summarize_conversation_history(self, 
                                           conversation_logs: List[ConversationLog],
                                           scene_id: int,
                                           user_progress_id: int) -> Dict[str, Any]:
        """Summarize conversation history for a scene"""
        
        # Prepare conversation text
        conversation_text = self._format_conversation_logs(conversation_logs)
        
        # Prepare input
        input_data = {
            "input": f"""
Summarize this conversation history for scene {scene_id}:

CONVERSATION:
{conversation_text}

Create a comprehensive summary that includes:
1. Key points discussed
2. Important decisions made
3. Learning moments and insights
4. Context for future interactions

Use your tools to analyze and summarize this conversation.
"""
        }
        
        try:
            # Execute summarization
            response = await self.agent_executor.ainvoke(input_data)
            
            # Parse the response
            result = self._parse_summarization_response(response.get("output", ""))
            
            # Add metadata
            result.update({
                "scene_id": scene_id,
                "user_progress_id": user_progress_id,
                "message_count": len(conversation_logs),
                "timestamp": datetime.utcnow().isoformat()
            })
            
            return result
            
        except Exception as e:
            print(f"Error in conversation summarization: {e}")
            return {
                "summary": f"Error summarizing conversation: {str(e)}",
                "key_points": [],
                "learning_moments": [],
                "scene_id": scene_id,
                "error": True
            }
    
    async def create_scene_transition_summary(self,
                                            current_scene: Dict[str, Any],
                                            next_scene: Dict[str, Any],
                                            conversation_summary: str) -> Dict[str, Any]:
        """Create summary for scene transition"""
        
        # Prepare input
        input_data = {
            "input": f"""
Create a transition summary from one scene to the next:

CURRENT SCENE: {current_scene.get('title', 'Unknown')}
- Description: {current_scene.get('description', '')}
- Goal: {current_scene.get('user_goal', '')}

NEXT SCENE: {next_scene.get('title', 'Unknown')}
- Description: {next_scene.get('description', '')}
- Goal: {next_scene.get('user_goal', '')}

CONVERSATION SUMMARY:
{conversation_summary}

Create a summary that:
1. Highlights what was accomplished in the current scene
2. Sets context for the next scene
3. Preserves important information for continuity
4. Identifies any carryover decisions or insights

Use your tools to create a comprehensive transition summary.
"""
        }
        
        try:
            # Execute transition summarization
            response = await self.agent_executor.ainvoke(input_data)
            
            # Parse the response
            result = self._parse_summarization_response(response.get("output", ""))
            
            # Add metadata
            result.update({
                "current_scene_id": current_scene.get('id'),
                "next_scene_id": next_scene.get('id'),
                "timestamp": datetime.utcnow().isoformat()
            })
            
            return result
            
        except Exception as e:
            print(f"Error in scene transition summarization: {e}")
            return {
                "summary": f"Error creating transition summary: {str(e)}",
                "key_points": [],
                "learning_moments": [],
                "error": True
            }
    
    async def create_session_summary(self,
                                   all_scene_summaries: List[Dict[str, Any]],
                                   user_progress_id: int) -> Dict[str, Any]:
        """Create overall session summary"""
        
        # Combine all scene summaries
        combined_summaries = "\n\n".join([
            f"Scene {i+1}: {summary.get('summary', '')}"
            for i, summary in enumerate(all_scene_summaries)
        ])
        
        # Prepare input
        input_data = {
            "input": f"""
Create an overall session summary from these scene summaries:

SCENE SUMMARIES:
{combined_summaries}

Create a comprehensive session summary that includes:
1. Overall progress and achievements
2. Key learning moments across all scenes
3. Important decisions and their implications
4. Areas of strength and improvement
5. Recommendations for future learning

Use your tools to analyze and synthesize these summaries.
"""
        }
        
        try:
            # Execute session summarization
            response = await self.agent_executor.ainvoke(input_data)
            
            # Parse the response
            result = self._parse_summarization_response(response.get("output", ""))
            
            # Add metadata
            result.update({
                "user_progress_id": user_progress_id,
                "scene_count": len(all_scene_summaries),
                "timestamp": datetime.utcnow().isoformat()
            })
            
            return result
            
        except Exception as e:
            print(f"Error in session summarization: {e}")
            return {
                "summary": f"Error creating session summary: {str(e)}",
                "key_points": [],
                "learning_moments": [],
                "error": True
            }
    
    def _format_conversation_logs(self, logs: List[ConversationLog]) -> str:
        """Format conversation logs into readable text"""
        formatted_lines = []
        
        for log in logs:
            timestamp = log.timestamp.strftime("%H:%M:%S")
            sender = log.sender_name or "Unknown"
            content = log.message_content
            
            formatted_lines.append(f"[{timestamp}] {sender}: {content}")
        
        return "\n".join(formatted_lines)
    
    def _extract_json_from_response(self, response: str) -> str:
        """Extract the first complete JSON object from response using balanced bracket matching"""
        if not response:
            return ""
        
        # Find the first opening brace
        start_idx = response.find('{')
        if start_idx == -1:
            return ""
        
        # Count braces to find the matching closing brace
        brace_count = 0
        in_string = False
        escape_next = False
        
        for i in range(start_idx, len(response)):
            char = response[i]
            
            if escape_next:
                escape_next = False
                continue
                
            if char == '\\':
                escape_next = True
                continue
                
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
                
            if not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        # Found the complete JSON object
                        return response[start_idx:i+1]
        
        # If we get here, no complete JSON object was found
        return ""
    
    def _parse_summarization_response(self, response: str) -> Dict[str, Any]:
        """Parse summarization response with robust JSON extraction and error handling"""
        import json
        import logging
        
        logger = logging.getLogger(__name__)
        
        try:
            # First, try to parse the entire response as JSON (in case it's clean JSON)
            try:
                result = json.loads(response.strip())
                debug_log("Successfully parsed entire response as JSON")
                return self._validate_and_format_result(result, response)
            except json.JSONDecodeError:
                debug_log("Response is not clean JSON, attempting extraction")
            
            # Extract JSON using balanced bracket matching
            json_str = self._extract_json_from_response(response)
            
            if json_str:
                try:
                    result = json.loads(json_str)
                    debug_log("Successfully extracted and parsed JSON from response")
                    return self._validate_and_format_result(result, response)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse extracted JSON: {e}")
                    logger.debug(f"Extracted JSON string: {json_str[:200]}...")
            else:
                logger.warning("No complete JSON object found in response")
            
            # Fallback: return response as summary
            logger.info("Using fallback parsing - returning response as summary")
            return {
                "summary": response,
                "key_points": [],
                "learning_moments": [],
                "insights": [],
                "recommendations": []
            }
            
        except Exception as e:
            logger.error(f"Unexpected error parsing summarization response: {e}")
            logger.debug(f"Response content: {response[:200]}...")
            return {
                "summary": response,
                "key_points": [],
                "learning_moments": [],
                "insights": [],
                "recommendations": []
            }
    
    def _validate_and_format_result(self, result: Dict[str, Any], original_response: str) -> Dict[str, Any]:
        """Validate and format the parsed result to ensure required fields exist"""
        return {
            "summary": result.get("summary", original_response),
            "key_points": result.get("key_points", []),
            "learning_moments": result.get("learning_moments", []),
            "insights": result.get("insights", []),
            "recommendations": result.get("recommendations", [])
        }
    
    def create_memory_summary(self, 
                            conversation_history: List[BaseMessage],
                            max_tokens: int = 1000) -> str:
        """Create a memory summary from conversation history"""
        try:
            # Create summary memory
            memory = ConversationSummaryBufferMemory(
                llm=self.llm,
                max_token_limit=max_tokens,
                return_messages=True
            )
            
            # Add conversation to memory
            for message in conversation_history:
                if isinstance(message, HumanMessage):
                    memory.chat_memory.add_user_message(message.content)
                elif isinstance(message, AIMessage):
                    memory.chat_memory.add_ai_message(message.content)
            
            # Get summary
            summary = memory.predict_new_summary(
                memory.chat_memory.messages,
                ""
            )
            
            return summary
            
        except Exception as e:
            print(f"Error creating memory summary: {e}")
            return "Unable to create summary"
    
    async def extract_learning_insights(self, 
                                      conversation_text: str,
                                      learning_objectives: List[str]) -> Dict[str, Any]:
        """Extract learning insights from conversation"""
        
        # Prepare input
        input_data = {
            "input": f"""
Extract learning insights from this conversation:

LEARNING OBJECTIVES:
{chr(10).join(f"• {obj}" for obj in learning_objectives)}

CONVERSATION:
{conversation_text}

Identify:
1. Which learning objectives were addressed
2. Key insights and understanding demonstrated
3. Areas where learning occurred
4. Gaps in understanding or missed objectives

Use your tools to analyze the conversation for learning insights.
"""
        }
        
        try:
            # Execute insight extraction
            response = await self.agent_executor.ainvoke(input_data)
            
            # Parse the response
            result = self._parse_summarization_response(response.get("output", ""))
            
            return result
            
        except Exception as e:
            print(f"Error extracting learning insights: {e}")
            return {
                "summary": f"Error extracting insights: {str(e)}",
                "key_points": [],
                "learning_moments": [],
                "error": True
            }
    
    # ===== Enhanced Methods Incorporating SimulationEngine Functionality =====
    
    def _format_conversation_for_ai(self, conversation_history: List[Dict[str, str]]) -> str:
        """Format conversation history for AI processing (from SimulationEngine)"""
        formatted_messages = []
        
        for msg in conversation_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "user":
                formatted_messages.append(f"User: {content}")
            elif role == "assistant":
                sender = msg.get("sender_name", "AI")
                formatted_messages.append(f"{sender}: {content}")
            else:
                formatted_messages.append(f"System: {content}")
        
        return "\n".join(formatted_messages)
    
    async def generate_scene_summary_enhanced(
        self,
        scene_data: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        goal_achieved: bool,
        user_progress_id: int,
        scene_id: int,
        forced_progression: bool = False,
        store_in_vector_db: bool = True
    ) -> str:
        """Enhanced scene summary incorporating SimulationEngine functionality with LangChain improvements"""
        
        try:
            # Format conversation history (using SimulationEngine method)
            conversation_text = self._format_conversation_for_ai(conversation_history[-10:])  # Last 10 messages
            
            # Store conversation in vector database for future reference (if requested)
            if store_in_vector_db and langchain_manager.vectorstore:
                try:
                    # Use langchain_manager.vectorstore to store embeddings
                    langchain_manager.vectorstore.add_texts(
                        texts=[conversation_text],
                        metadatas=[{
                            "type": "scene_conversation",
                            "user_progress_id": str(user_progress_id),
                            "scene_id": str(scene_id),
                            "goal_achieved": str(goal_achieved),
                            "forced_progression": str(forced_progression),
                            "scene_title": scene_data.get('title', 'Unknown Scene')
                        }]
                    )
                except Exception as e:
                    print(f"Warning: Failed to store conversation in vector DB: {e}")
            
            # Create enhanced prompt (combining SimulationEngine and LangChain approaches)
            summary_prompt = f"""Generate a comprehensive summary of the user's performance in this business simulation scene.

SCENE: {scene_data.get('title', 'Unknown Scene')}
GOAL: {scene_data.get('user_goal', 'Not specified')}
GOAL ACHIEVED: {goal_achieved}
FORCED PROGRESSION: {forced_progression}

CONVERSATION:
{conversation_text}

Create a detailed summary that:
1. Acknowledges what the user accomplished or attempted
2. Identifies key insights, decisions, or missed opportunities
3. Provides constructive feedback for learning
4. Encourages progression to the next scene
5. Maintains a supportive, educational tone
6. Is 2-3 sentences for brief summaries or more detailed for comprehensive analysis

Summary:"""

            # Use LangChain LLM for enhanced generation with persona awareness
            persona_name = scene_data.get('persona_name', 'the persona')
            persona_role = scene_data.get('persona_role', 'Team Member')
            summary_prompt = f"""Analyze the interaction between the user and {persona_name} in this business simulation.

PERSONA: {persona_name} - {persona_role}

SCENE: {scene_data.get('title', 'Unknown Scene')}
GOAL: {scene_data.get('user_goal', 'Not specified')}
GOAL ACHIEVED: {goal_achieved}
FORCED PROGRESSION: {forced_progression}

CONVERSATION:
{conversation_text}

Create a detailed summary that:
1. Acknowledges what the user accomplished or attempted with {persona_name}
2. Identifies key insights, decisions, or missed opportunities in the interaction
3. Analyzes the user's communication style and approach with the persona
4. Provides constructive feedback for learning and improvement
5. Encourages progression to the next scene
6. Maintains a supportive, educational tone
7. Is 2-3 sentences for brief summaries or more detailed for comprehensive analysis

Focus on the interpersonal dynamics, decision-making process, and learning outcomes from the user's interaction with {persona_name}.

Summary:"""
            response = await self.llm.ainvoke(summary_prompt)
            return response.content
            
        except Exception as e:
            print(f"Error in enhanced scene summary: {e}")
            # Fallback to simple summary (like SimulationEngine)
            status = "achieved your goal" if goal_achieved else "made progress"
            return f"You {status} in this scene. Let's continue to the next part of the simulation."
    
    async def generate_brief_scene_summary(
        self,
        scene_data: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        goal_achieved: bool,
        forced_progression: bool = False
    ) -> str:
        """Generate a brief scene summary (matching SimulationEngine's original functionality)"""
        
        try:
            # Format conversation history (using SimulationEngine method)
            conversation_text = self._format_conversation_for_ai(conversation_history[-10:])  # Last 10 messages
            
            # Create brief prompt (matching SimulationEngine's original approach)
            summary_prompt = f"""Generate a brief summary of the user's performance in this business simulation scene.

SCENE: {scene_data.get('title', 'Unknown Scene')}
GOAL: {scene_data.get('user_goal', 'Not specified')}
GOAL ACHIEVED: {goal_achieved}
FORCED PROGRESSION: {forced_progression}

CONVERSATION SUMMARY:
{conversation_text}

Create a 2-3 sentence summary that:
- Acknowledges what the user accomplished
- Notes key insights or missed opportunities
- Encourages progression to the next scene
- Maintains a supportive, educational tone

Summary:"""

            # Use LangChain LLM for generation
            response = await self.llm.ainvoke(summary_prompt)
            return response.content
            
        except Exception as e:
            print(f"Error in brief scene summary: {e}")
            # Fallback to simple summary (like SimulationEngine)
            status = "achieved your goal" if goal_achieved else "made progress"
            return f"You {status} in this scene. Let's continue to the next part of the simulation."
    
    async def generate_persona_interaction_summary(
        self,
        persona_data: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        interaction_quality: float
    ) -> str:
        """Generate a summary of persona interactions for learning insights"""
        
        try:
            conversation_text = self._format_conversation_for_ai(conversation_history)
            
            summary_prompt = f"""Analyze the interaction between the user and {persona_data.get('name', 'the persona')} in this business simulation.

PERSONA: {persona_data.get('name', 'Unknown')} - {persona_data.get('role', 'Team Member')}
INTERACTION QUALITY SCORE: {interaction_quality:.2f}/1.0

CONVERSATION:
{conversation_text}

Generate a summary that:
1. Evaluates the quality of the interaction
2. Identifies effective communication strategies used
3. Notes areas for improvement
4. Provides specific feedback for better persona engagement
5. Maintains a constructive, educational tone

Summary:"""

            response = await self.llm.ainvoke(summary_prompt)
            return response.content
            
        except Exception as e:
            print(f"Error in persona interaction summary: {e}")
            return f"Interaction with {persona_data.get('name', 'the persona')} was {'successful' if interaction_quality > 0.7 else 'challenging'}. Consider asking more specific questions to get better insights."
    
    async def generate_learning_progress_summary(
        self,
        user_progress_id: int,
        scene_summaries: List[Dict[str, Any]]
    ) -> str:
        """Generate a comprehensive learning progress summary across multiple scenes"""
        
        try:
            # Format scene summaries
            scenes_text = ""
            for i, scene_summary in enumerate(scene_summaries, 1):
                scenes_text += f"Scene {i}: {scene_summary.get('title', 'Unknown')}\n"
                scenes_text += f"Goal: {scene_summary.get('goal', 'Not specified')}\n"
                scenes_text += f"Achieved: {scene_summary.get('achieved', False)}\n"
                scenes_text += f"Summary: {scene_summary.get('summary', 'No summary available')}\n\n"
            
            summary_prompt = f"""Analyze the user's learning progress across multiple business simulation scenes.

USER PROGRESS ID: {user_progress_id}

SCENE PROGRESS:
{scenes_text}

Generate a comprehensive learning progress summary that:
1. Identifies overall learning patterns and growth
2. Highlights key achievements and breakthroughs
3. Notes consistent challenges or areas for improvement
4. Provides personalized recommendations for continued learning
5. Celebrates progress and encourages continued engagement
6. Maintains an encouraging, educational tone

Summary:"""

            response = await self.llm.ainvoke(summary_prompt)
            return response.content
            
        except Exception as e:
            print(f"Error in learning progress summary: {e}")
            return f"Great progress across {len(scene_summaries)} scenes! Continue building on your business simulation skills."

# Global summarization agent instance
summarization_agent = SummarizationAgent()
