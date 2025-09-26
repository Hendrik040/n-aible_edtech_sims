"""
Grading Agent for AI Agent Education Platform
Handles LLM-driven grading and feedback with LangChain
"""

from typing import Dict, List, Any, Optional, Tuple
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import BaseMessage
from langchain.callbacks.base import BaseCallbackHandler
from langchain_core.outputs.llm_result import LLMResult
import json
from datetime import datetime

from langchain_config import langchain_manager, settings
from database.models import ScenarioScene, ConversationLog, UserProgress

class GradingCallbackHandler(BaseCallbackHandler):
    """Callback handler for grading operations  1121"""
    
    def __init__(self, user_progress_id: int, scene_id: int):
        self.user_progress_id = user_progress_id
        self.scene_id = scene_id
        self.start_time = None
        self.grading_metadata = {}
        
    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs) -> None:
        """Called when LLM starts"""
        self.start_time = datetime.utcnow()
        
    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        """Called when LLM ends"""
        if self.start_time:
            processing_time = (datetime.utcnow() - self.start_time).total_seconds()
            self.grading_metadata["processing_time"] = processing_time
            self.grading_metadata["timestamp"] = datetime.utcnow().isoformat()

class GradingAgent:
    """LangChain-based grading agent for scene and overall simulation evaluation"""
    
    def __init__(self):
        self.llm = langchain_manager.llm
        self.tools = self._create_grading_tools()
        self.prompt = self._create_grading_prompt()
        
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
            verbose=(getattr(settings, "environment", "development") != "production"),
            handle_parsing_errors=True,
            max_iterations=2
        )
    
    def _create_grading_tools(self) -> List[BaseTool]:
        """Create tools for grading operations"""
        from langchain.tools import tool
        
        @tool
        def analyze_user_responses(user_responses: str, success_metric: str) -> str:
            """Analyze user responses against success metrics"""
            return f"Analyzing {len(user_responses.split())} words of user responses against success metric: {success_metric}"
        
        @tool
        def evaluate_learning_objectives(responses: str, objectives: str) -> str:
            """Evaluate responses against learning objectives"""
            return f"Evaluating responses against {len(objectives.split(','))} learning objectives"
        
        @tool
        def generate_detailed_feedback(score: int, reasoning: str) -> str:
            """Generate detailed feedback based on score and reasoning"""
            return f"Generating feedback for score {score} with reasoning: {reasoning}"
        
        @tool
        def calculate_overall_score(scene_scores: str) -> str:
            """Calculate overall simulation score from scene scores"""
            try:
                scores = []
                for s in scene_scores.split(','):
                    s = s.strip()
                    if s.isdigit():
                        scores.append(int(s))
                    elif s:  # Non-empty, non-digit string
                        return f"Invalid score format: '{s}' is not a valid number"
            except Exception as e:
                return f"Error parsing scores: {str(e)}"
            
            if scores:
                avg_score = sum(scores) / len(scores)
                return f"Overall score: {avg_score:.1f} (average of {len(scores)} scenes)"
            return "No valid scores to calculate"
        
        return [analyze_user_responses, evaluate_learning_objectives, 
                generate_detailed_feedback, calculate_overall_score]
    
    def _create_grading_prompt(self) -> ChatPromptTemplate:
        """Create grading prompt template"""
        return ChatPromptTemplate.from_messages([
            ("system", self._get_system_prompt()),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
    
    def _get_system_prompt(self) -> str:
        """Generate system prompt for grading"""
        return """You are an expert grading agent for business simulation education.

Your role is to:
1. Evaluate user responses against specific success metrics and learning objectives
2. Provide fair, constructive feedback that helps students learn
3. Award appropriate scores based on demonstrated understanding
4. Be moderately lenient - award partial credit for reasonable attempts
5. Focus on learning outcomes rather than perfect answers

GRADING PRINCIPLES:
- Score 0-100 based on alignment with success metrics
- Award at least 60 points for on-topic, good-faith attempts
- Only give very low scores for completely off-topic responses
- Provide specific, actionable feedback
- Consider the educational context and learning objectives

Use your tools to analyze responses, evaluate objectives, and generate comprehensive feedback."""
    
    async def grade_scene(self, 
                         scene: ScenarioScene,
                         user_responses: List[Dict[str, Any]],
                         user_progress_id: int) -> Dict[str, Any]:
        """Grade a single scene"""
        
        # Create callback handler
        callback_handler = GradingCallbackHandler(user_progress_id, scene.id)
        
        # Prepare user responses text
        responses_text = "\n".join([
            f"{i+1}. {response.get('content', '')}" 
            for i, response in enumerate(user_responses)
        ])
        
        # Prepare input
        input_data = {
            "input": f"""
Grade this scene: {scene.title}

SUCCESS METRIC: {scene.success_metric or scene.user_goal}
SCENE GOAL: {scene.user_goal}

USER RESPONSES:
{responses_text}

Provide a score (0-100) and detailed feedback. Use your tools to analyze the responses.
"""
        }
        
        try:
            # Execute grading
            response = await self.agent_executor.ainvoke(
                input_data,
                callbacks=[callback_handler]
            )
            
            # Parse the response to extract score and feedback
            result = self._parse_grading_response(response.get("output", ""))
            
            # Add metadata
            result.update({
                "scene_id": scene.id,
                "scene_title": scene.title,
                "user_progress_id": user_progress_id,
                "grading_metadata": callback_handler.grading_metadata,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            })
            
            return result
            
        except Exception as e:
            print(f"Error in scene grading: {e}")
            return {
                "score": 0,
                "feedback": f"Grading error: {str(e)}",
                "scene_id": scene.id,
                "error": True
            }
    
    async def grade_overall_simulation(self,
                                     scenario_id: int,
                                     scene_grades: List[Dict[str, Any]],
                                     learning_objectives: List[str],
                                     user_progress_id: int) -> Dict[str, Any]:
        """Grade the overall simulation"""
        
        # Create callback handler
        callback_handler = GradingCallbackHandler(user_progress_id, 0)
        
        # Prepare scene grades summary
        scene_summary = "\n".join([
            f"Scene {i+1}: {grade.get('scene_title', 'Unknown')} - Score: {grade.get('score', 0)}"
            for i, grade in enumerate(scene_grades)
        ])
        
        # Calculate overall score
        scores = [grade.get('score', 0) for grade in scene_grades if isinstance(grade.get('score'), (int, float))]
        overall_score = sum(scores) / len(scores) if scores else 0
        
        # Prepare input
        input_data = {
            "input": f"""
Grade the overall simulation performance:

LEARNING OBJECTIVES:
{chr(10).join(f"• {obj}" for obj in learning_objectives)}

SCENE PERFORMANCE:
{scene_summary}

OVERALL SCORE: {overall_score:.1f}

Provide comprehensive feedback on the overall simulation performance, highlighting strengths and areas for improvement.
"""
        }
        
        try:
            # Execute overall grading
            response = await self.agent_executor.ainvoke(
                input_data,
                callbacks=[callback_handler]
            )
            
            # Parse the response
            result = self._parse_grading_response(response.get("output", ""))
            
            # Add metadata
            result.update({
                "overall_score": round(overall_score, 1),
                "scenario_id": scenario_id,
                "user_progress_id": user_progress_id,
                "scene_count": len(scene_grades),
                "grading_metadata": callback_handler.grading_metadata,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            })
            
            return result
            
        except Exception as e:
            print(f"Error in overall grading: {e}")
            return {
                "overall_score": round(overall_score, 1),
                "feedback": f"Overall grading error: {str(e)}",
                "scenario_id": scenario_id,
                "error": True
            }
    
    def _parse_grading_response(self, response: str) -> Dict[str, Any]:
        """Parse grading response to extract score and feedback"""
        try:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                json_str = json_match.group(0)
                result = json.loads(json_str)
                return {
                    "score": result.get("score", 0),
                    "feedback": result.get("feedback", response)
                }
            
            # Try to extract score from text
            score_match = re.search(r'score[:\s]*(\d+)', response.lower())
            if score_match:
                score = int(score_match.group(1))
                return {
                    "score": score,
                    "feedback": response
                }
            
            # Default fallback
            return {
                "score": 70,  # Default moderate score
                "feedback": response
            }
            
        except Exception as e:
            print(f"Error parsing grading response: {e}")
            return {
                "score": 70,
                "feedback": response
            }
    
    async def validate_goal_achievement(self,
                                      conversation_history: str,
                                      scene_goal: str,
                                      scene_description: str,
                                      current_attempts: int,
                                      max_attempts: int) -> Dict[str, Any]:
        """Validate if user has achieved the scene goal"""
        
        # Pre-check for generic responses
        irrelevant_responses = {"test", "hello", "ok", "hi", "thanks", "hey", "goodbye", "bye"}
        last_user_message = ""
        for line in reversed(conversation_history.strip().split("\n")):
            if line.lower().startswith("user:"):
                last_user_message = line[5:].strip()
                break
        
        if last_user_message.lower() in irrelevant_responses or len(last_user_message) < 3:
            return {
                "goal_achieved": False,
                "confidence_score": 0.0,
                "reasoning": "Your last message did not address the scene's goal.",
                "next_action": "continue",
                "hint_message": "Please provide a response that directly addresses the scene's goal and aligns with the success metric."
            }
        
        # Use LangChain agent for goal validation
        input_data = {
            "input": f"""
Evaluate if the user has achieved the scene goal:

SCENE GOAL: {scene_goal}
SCENE DESCRIPTION: {scene_description}
CURRENT ATTEMPTS: {current_attempts}/{max_attempts}

CONVERSATION HISTORY:
{conversation_history}

Determine:
1. Has the user achieved the scene goal? (true/false)
2. Confidence score (0.0-1.0)
3. Brief reasoning
4. Next action: "continue", "progress", "hint", or "force_progress"
5. Optional hint message if action is "hint"

Be moderately lenient: If the user's response is on-topic and makes a good-faith attempt, mark the goal as achieved.
"""
        }
        
        try:
            response = await self.agent_executor.ainvoke(input_data)
            return self._parse_goal_validation_response(response.get("output", ""))
            
        except Exception as e:
            print(f"Error in goal validation: {e}")
            return {
                "goal_achieved": False,
                "confidence_score": 0.0,
                "reasoning": f"Validation error: {str(e)}",
                "next_action": "continue",
                "hint_message": None
            }
    
    def _parse_goal_validation_response(self, response: str) -> Dict[str, Any]:
        """Parse goal validation response"""
        try:
            # Try to extract JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                json_str = json_match.group(0)
                result = json.loads(json_str)
                return {
                    "goal_achieved": result.get("goal_achieved", False),
                    "confidence_score": result.get("confidence_score", 0.0),
                    "reasoning": result.get("reasoning", ""),
                    "next_action": result.get("next_action", "continue"),
                    "hint_message": result.get("hint_message")
                }
            
            # Fallback parsing
            goal_achieved = "achieved" in response.lower() or "true" in response.lower()
            return {
                "goal_achieved": goal_achieved,
                "confidence_score": 0.7 if goal_achieved else 0.3,
                "reasoning": response,
                "next_action": "progress" if goal_achieved else "continue",
                "hint_message": None
            }
            
        except Exception as e:
            print(f"Error parsing goal validation: {e}")
            return {
                "goal_achieved": False,
                "confidence_score": 0.0,
                "reasoning": f"Parsing error: {str(e)}",
                "next_action": "continue",
                "hint_message": None
            }

# Global grading agent instance
grading_agent = GradingAgent()
