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
from services.grading_vector_store import search_grading_materials_tool

class GradingCallbackHandler(BaseCallbackHandler):
    """Callback handler for grading operations"""
    
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
            max_iterations=5
        )
    
    def _create_grading_tools(self) -> List[BaseTool]:
        """Create tools for grading operations"""
        from langchain.tools import tool
        
        @tool
        def analyze_business_thinking(responses: str, success_metric: str) -> str:
            """Analyze user responses for business thinking quality and strategic analysis"""
            return f"Analyzing business thinking in {len(responses.split())} words against success metric: {success_metric}. Evaluating strategic perspective, problem identification, and solution development."
        
        @tool
        def evaluate_strategic_depth(responses: str, objectives: str) -> str:
            """Evaluate responses for strategic thinking depth and analytical rigor"""
            return f"Evaluating strategic depth against {len(objectives.split(','))} learning objectives. Assessing long-term thinking, stakeholder consideration, and critical analysis."
        
        @tool
        def assess_practical_application(responses: str, scene_context: str) -> str:
            """Assess how well responses demonstrate practical business application"""
            return f"Assessing practical application in responses within scene context: {scene_context}. Evaluating implementation feasibility and real-world relevance."
        
        @tool
        def generate_business_feedback(score: int, reasoning: str, criteria_breakdown: str) -> str:
            """Generate detailed business-focused feedback with criteria breakdown"""
            return f"Generating business feedback for score {score} with reasoning: {reasoning}. Criteria breakdown: {criteria_breakdown}"
        
        @tool
        def calculate_weighted_score(scene_scores: str, weights: str) -> str:
            """Calculate overall simulation score with weighted criteria"""
            try:
                scores = []
                for s in scene_scores.split(','):
                    s = s.strip()
                    if s.isdigit():
                        scores.append(int(s))
                    elif s:  # Non-empty, non-digit string
                        return f"Invalid score format: '{s}' is not a valid number"
                
                # Parse weights if provided
                weight_list = []
                if weights:
                    for w in weights.split(','):
                        w = w.strip()
                        if w.replace('.', '').isdigit():
                            weight_list.append(float(w))
                
                if scores:
                    if weight_list and len(weight_list) == len(scores):
                        weighted_score = sum(s * w for s, w in zip(scores, weight_list))
                        return f"Weighted overall score: {weighted_score:.1f} (weighted average of {len(scores)} scenes)"
                    else:
                        avg_score = sum(scores) / len(scores)
                        return f"Overall score: {avg_score:.1f} (average of {len(scores)} scenes)"
                return "No valid scores to calculate"
            except Exception as e:
                return f"Error parsing scores: {str(e)}"
        
        @tool
        def identify_learning_gaps(responses: str, expected_outcomes: str) -> str:
            """Identify specific learning gaps and areas for improvement"""
            return f"Identifying learning gaps in responses against expected outcomes: {expected_outcomes}. Analyzing knowledge gaps and skill development needs."
        
        @tool
        def assess_context_awareness(responses: str, scene_context: str, uploaded_materials: str) -> str:
            """Assess how well the response demonstrates context awareness and references to uploaded materials"""
            return f"Assessing context awareness in responses within scene context: {scene_context}. Evaluating references to uploaded materials: {uploaded_materials}. Looking for sophisticated business thinking and research awareness."
        
        @tool
        def evaluate_business_acumen(responses: str, business_concepts: str) -> str:
            """Evaluate the overall business acumen and strategic thinking demonstrated"""
            return f"Evaluating business acumen in responses. Assessing strategic thinking, business concepts understanding: {business_concepts}. Looking for sophisticated analysis and practical application."
        
        return [search_grading_materials_tool, analyze_business_thinking, evaluate_strategic_depth, 
                assess_practical_application, generate_business_feedback, calculate_weighted_score, 
                identify_learning_gaps, assess_context_awareness, evaluate_business_acumen]
    
    def _create_grading_prompt(self) -> ChatPromptTemplate:
        """Create grading prompt template"""
        return ChatPromptTemplate.from_messages([
            ("system", self._get_system_prompt()),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
    
    def _get_system_prompt(self) -> str:
        """Generate system prompt for grading"""
        return """You are an expert grading agent for business simulation education with expertise in business case analysis and strategic thinking.

Your role is to:
1. Evaluate user responses against specific rubric criteria and performance levels
2. Assess business analysis quality, strategic thinking, and practical application
3. Provide fair, constructive feedback that helps students learn
4. Award appropriate scores based on demonstrated understanding
5. Focus on learning outcomes and business acumen development

CONTEXT-AWARE GRADING APPROACH:
- Recognize when students demonstrate high-quality business thinking, even if it doesn't perfectly align with the specific scene goal
- Consider the broader business context and learning objectives
- Reward students who reference uploaded materials and show sophisticated understanding
- Be flexible in evaluation while maintaining academic standards
- Focus on demonstrated business acumen and strategic thinking

RUBRIC-BASED GRADING APPROACH:
- Use the provided rubric criteria and performance levels for evaluation
- Each criterion has specific point values for Outstanding, Excellent, Good, Fair, and Poor performance
- Score based on the rubric's point structure, not arbitrary percentages
- Provide detailed feedback referencing specific rubric criteria
- Consider the educational context and learning objectives

GRADING PRINCIPLES:
- Award points based on rubric performance levels (Outstanding, Excellent, Good, Fair, Poor)
- Provide specific, actionable feedback with business context
- Reference rubric criteria in your evaluation
- Consider the educational context and learning objectives
- Focus on demonstrated understanding and application
- Be generous when students show sophisticated business thinking
- Recognize references to uploaded materials and research

FLEXIBLE EVALUATION PROCESS:
1. First, assess the overall quality of business thinking demonstrated
2. Check if the response references uploaded materials or shows research awareness
3. Evaluate alignment with scene goals, but don't penalize good business analysis
4. Consider alternative interpretations and business applications
5. Award points generously for demonstrated business acumen
6. Provide constructive feedback that builds on strengths

Use your tools to analyze responses, evaluate objectives, and generate comprehensive feedback.

IMPORTANT: Before grading any scene, use the search_grading_materials tool to retrieve relevant grading materials, rubrics, and criteria for the simulation. This will ensure consistent and accurate grading based on the professor's specific requirements."""
    
    async def grade_scene(self, 
                         scene: ScenarioScene,
                         user_responses: List[Dict[str, Any]],
                         user_progress_id: int,
                         rubric_criteria: Optional[List[Dict[str, Any]]] = None,
                         rubric_title: Optional[str] = None,
                         rubric_performance_levels: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Grade a single scene"""
        
        # Create callback handler
        callback_handler = GradingCallbackHandler(user_progress_id, scene.id)
        
        # Prepare user responses text
        responses_text = "\n".join([
            f"{i+1}. {response.get('content', '')}" 
            for i, response in enumerate(user_responses)
        ])
        
        # Prepare rubric information
        rubric_info = ""
        if rubric_criteria and rubric_title and rubric_performance_levels:
            rubric_info = f"""
RUBRIC INFORMATION:
Rubric Title: {rubric_title}

Performance Levels:
"""
            for level in rubric_performance_levels:
                rubric_info += f"- {level.get('name', 'Unnamed Level')}: {level.get('points', 0)} points\n"

            rubric_info += "\nRubric Criteria:\n"
            for i, criterion in enumerate(rubric_criteria, 1):
                rubric_info += f"""
{i}. {criterion.get('description', 'No description provided')}
"""
                # Add performance level descriptions
                descriptions = criterion.get('descriptions', {})
                for level in rubric_performance_levels:
                    level_name = level.get('name', 'Unnamed Level')
                    description = descriptions.get(level_name, 'No description provided')
                    rubric_info += f"   {level_name} ({level.get('points', 0)} pts): {description}\n"

        # Prepare input
        input_data = {
            "input": f"""
Grade this business simulation scene: {scene.title}
Simulation ID: {scene.scenario_id}

SUCCESS METRIC: {scene.success_metric or scene.user_goal}
SCENE GOAL: {scene.user_goal}
SCENE CONTEXT: {scene.description}

{rubric_info}

USER RESPONSES:
{responses_text}

CONTEXT-AWARE GRADING INSTRUCTIONS:
1. First, use the search_grading_materials tool to find relevant grading materials for simulation {scene.scenario_id}
2. Use the retrieved grading materials as reference for evaluation criteria and standards
3. Assess the overall quality of business thinking demonstrated in the response
4. Check if the response references uploaded materials, research, or shows sophisticated understanding
5. Evaluate alignment with scene goals, but be flexible - don't penalize good business analysis
6. Consider alternative business applications and interpretations
7. Award points generously for demonstrated business acumen and strategic thinking
8. Provide constructive feedback that builds on strengths

GRADING APPROACH:
- Be generous when students show sophisticated business thinking
- Recognize references to uploaded materials and research
- Consider the broader business context and learning objectives
- Focus on demonstrated understanding rather than perfect alignment
- Reward strategic thinking and business acumen

Provide a comprehensive evaluation with detailed feedback including:
1. Overall assessment of business thinking quality
2. Recognition of references to uploaded materials and research
3. Score breakdown by rubric criteria with performance level justification
4. Specific strengths demonstrated for each criterion
5. Areas for improvement with actionable recommendations
6. Business context and real-world application insights
7. Reference to grading materials used (if any)

Use your tools to retrieve grading materials and analyze the business thinking quality. Specifically:
- Use assess_context_awareness to evaluate references to uploaded materials
- Use evaluate_business_acumen to assess overall strategic thinking
- Use analyze_business_thinking to evaluate the quality of business analysis
- Be generous in scoring when students demonstrate sophisticated understanding
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
Grade the overall business simulation performance:
Simulation ID: {scenario_id}

LEARNING OBJECTIVES:
{chr(10).join(f"• {obj}" for obj in learning_objectives)}

SCENE PERFORMANCE SUMMARY:
{scene_summary}

CALCULATED OVERALL SCORE: {overall_score:.1f}

CONTEXT-AWARE GRADING INSTRUCTIONS:
1. First, use the search_grading_materials tool to find relevant grading materials for simulation {scenario_id}
2. Use the retrieved grading materials as reference for evaluation criteria and standards
3. Assess overall strategic thinking and business perspective demonstrated
4. Evaluate problem-solving approach across scenes with flexibility
5. Review communication and presentation skills
6. Analyze critical thinking and consideration of alternatives
7. Evaluate practical application and real-world relevance
8. Assess learning integration across scenarios
9. Be generous when students show sophisticated business understanding
10. Recognize references to uploaded materials and research throughout

BUSINESS SIMULATION EVALUATION CRITERIA:
- Overall Strategic Thinking: How well did the student demonstrate strategic business perspective?
- Problem-Solving Approach: Quality of problem identification and solution development across scenes
- Communication & Presentation: Professional communication skills and clarity
- Critical Analysis: Depth of analysis and consideration of alternatives
- Practical Application: Real-world relevance and implementation feasibility
- Learning Integration: How well concepts were applied across different scenarios

Provide comprehensive feedback including:
1. Overall performance assessment with business context
2. Key strengths demonstrated across the simulation
3. Specific areas for improvement with actionable recommendations
4. Business acumen development insights
5. Recommendations for continued learning and skill development
6. Reference to grading materials used (if any)

Use your tools to retrieve grading materials and evaluate strategic depth.
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
Evaluate if the user has achieved the business simulation scene goal:

SCENE GOAL: {scene_goal}
SCENE DESCRIPTION: {scene_description}
CURRENT ATTEMPTS: {current_attempts}/{max_attempts}

CONVERSATION HISTORY:
{conversation_history}

BUSINESS SIMULATION EVALUATION CRITERIA:
- Goal Achievement: Has the user demonstrated understanding and addressed the core business challenge?
- Strategic Thinking: Shows evidence of strategic business perspective and analysis
- Practical Application: Demonstrates real-world business application and feasibility
- Communication Quality: Professional communication appropriate for business context
- Learning Progress: Shows progression in understanding business concepts

Determine:
1. Has the user achieved the scene goal? (true/false)
2. Confidence score (0.0-1.0) based on business analysis quality
3. Brief reasoning focusing on business acumen demonstrated
4. Next action: "continue", "progress", "hint", or "force_progress"
5. Optional hint message if action is "hint" - provide business-focused guidance

Be moderately lenient but maintain business standards: If the user's response shows good-faith business analysis and addresses the core challenge, mark the goal as achieved.
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
