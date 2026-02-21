"""
Grading Agent for AI Agent Education Platform
Handles LLM-driven grading and feedback with LangChain structured output
"""

import json
from typing import Dict, List, Any, Optional, Tuple
from langchain.callbacks.base import BaseCallbackHandler
from langchain_core.outputs.llm_result import LLMResult
from langchain_core.messages import SystemMessage, HumanMessage
from datetime import datetime

from common.services.ai_gateway import langchain_manager
from common.config import get_settings
from common.db.models import SimulationScene, SimulationPersona

from modules.simulation.schemas.grading_schemas import SceneGradingResult, OverallGradingResult

settings = get_settings()


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
    """LangChain-based grading agent using structured output for reliable score extraction"""

    def __init__(self):
        self.llm = langchain_manager.llm

        # Create structured output LLMs for grading
        # These return Pydantic models directly - no parsing needed
        self.scene_grader = self.llm.with_structured_output(SceneGradingResult)
        self.overall_grader = self.llm.with_structured_output(OverallGradingResult)

    def _get_scene_grading_system_prompt(self) -> str:
        """Generate system prompt for scene grading"""
        return """You are an expert grading agent for business simulation education with expertise in business case analysis and strategic thinking.

Your role is to evaluate student responses and provide structured grading output.

CONTEXT-AWARE GRADING APPROACH:
- Recognize when students demonstrate high-quality business thinking, even if it doesn't perfectly align with the specific scene goal
- Consider the broader business context and learning objectives
- Reward students who reference uploaded materials and show sophisticated understanding
- Be flexible in evaluation while maintaining academic standards
- Focus on demonstrated business acumen and strategic thinking

RUBRIC-BASED GRADING APPROACH:
- Use the provided rubric criteria and performance levels for evaluation
- Each criterion has specific point values for Outstanding, Excellent, Good, Fair, and Poor performance
- Score based on the rubric's point structure
- Consider the educational context and learning objectives

GRADING PRINCIPLES:
- Award points based on rubric performance levels (Outstanding, Excellent, Good, Fair, Poor)
- Be generous when students show sophisticated business thinking
- Recognize references to uploaded materials and research
- Focus on demonstrated understanding and application

SCORING GUIDELINES:
- 85-100: Outstanding/Excellent - Demonstrates sophisticated business thinking, strategic analysis, and exceeds expectations
- 70-84: Good - Shows solid understanding and meets most objectives
- 55-69: Fair - Demonstrates basic understanding but lacks depth
- 40-54: Poor - Shows minimal engagement or understanding
- 0-39: Very Poor - Little to no meaningful response or completely off-topic

Provide your evaluation as a structured response with all required fields."""

    def _get_overall_grading_system_prompt(self) -> str:
        """Generate system prompt for overall grading"""
        return """You are an expert grading agent evaluating overall performance across a business simulation.

Your role is to synthesize performance across multiple scenes and provide a comprehensive assessment.

EVALUATION CRITERIA:
- Overall Strategic Thinking: How well did the student demonstrate strategic business perspective?
- Problem-Solving Approach: Quality of problem identification and solution development across scenes
- Communication & Presentation: Professional communication skills and clarity
- Critical Analysis: Depth of analysis and consideration of alternatives
- Practical Application: Real-world relevance and implementation feasibility
- Learning Integration: How well concepts were applied across different scenarios

SCORING GUIDELINES:
- 85-100: Outstanding/Excellent - Consistently demonstrated sophisticated business thinking across all scenes
- 70-84: Good - Generally solid performance with strong understanding
- 55-69: Fair - Mixed performance, some areas need improvement
- 40-54: Poor - Struggled with most aspects of the simulation
- 0-39: Very Poor - Minimal meaningful engagement

Provide your evaluation as a structured response with all required fields."""

    def _format_scene_feedback(self, result: SceneGradingResult) -> str:
        """Format structured result into readable feedback string"""
        feedback_parts = []

        # Criteria breakdown
        if result.criteria_breakdown:
            feedback_parts.append("**SCORE BREAKDOWN:**")
            for criterion in result.criteria_breakdown:
                feedback_parts.append(
                    f"- **{criterion.criterion_name}**: {criterion.score}/{criterion.max_points} points "
                    f"({criterion.performance_level}) - {criterion.reasoning}"
                )
            feedback_parts.append("")

        # Overall assessment
        feedback_parts.append("**OVERALL ASSESSMENT:**")
        feedback_parts.append(f"**Brief summary of business thinking quality:** {result.business_thinking_quality}")
        feedback_parts.append(f"**Key strengths demonstrated:** {result.key_strengths}")
        feedback_parts.append(f"**Main areas for improvement:** {result.areas_for_improvement}")
        feedback_parts.append("")

        # Feedback
        feedback_parts.append("**FEEDBACK:**")
        feedback_parts.append(f"**Specific actionable recommendations:** {result.actionable_recommendations}")

        return "\n".join(feedback_parts)

    def _format_overall_feedback(self, result: OverallGradingResult) -> str:
        """Format structured overall result into readable feedback string"""
        feedback_parts = []

        feedback_parts.append("**OVERALL ASSESSMENT:**")
        feedback_parts.append(f"**Summary of performance across the simulation:** {result.performance_summary}")
        feedback_parts.append(f"**Key strengths demonstrated:** {result.key_strengths}")
        feedback_parts.append(f"**Main areas for improvement:** {result.areas_for_improvement}")
        feedback_parts.append("")

        feedback_parts.append("**FEEDBACK:**")
        feedback_parts.append(f"**Specific actionable recommendations:** {result.actionable_recommendations}")
        feedback_parts.append(f"**Business acumen development insights:** {result.business_acumen_insights}")

        return "\n".join(feedback_parts)

    def _format_scene_persona_context(
        self,
        scene_personas_with_involvement: List[Tuple[SimulationPersona, str]],
        persona_instructions: Optional[Dict[str, Any]] = None
    ) -> str:
        """Format persona data into a structured block for the grading prompt."""
        if not scene_personas_with_involvement:
            return ""

        lines = ["PERSONAS IN THIS SCENE:"]
        for persona, involvement_level in scene_personas_with_involvement:
            lines.append(f"\n  {persona.name} ({persona.role}) [Involvement: {involvement_level}]")

            if persona.correlation:
                lines.append(f"    Relationship to student: {persona.correlation}")

            if persona.primary_goals:
                goals = persona.primary_goals[:3]  # Top 3
                lines.append(f"    Goals: {', '.join(goals)}")

            # Communication style is a top-level field on SimulationPersona
            if getattr(persona, "communication_style", None):
                lines.append(f"    Communication style: {persona.communication_style}")

            # Big Five traits are stored directly in personality_traits
            # Keys: openness, conscientiousness, extraversion, agreeableness, neuroticism (1-10)
            traits = persona.personality_traits
            if isinstance(traits, dict) and traits:
                trait_parts = []
                for k, v in traits.items():
                    if isinstance(v, (int, float)):
                        trait_parts.append(f"{k}: {v}/10")
                    else:
                        trait_parts.append(f"{k}: {v}")
                if trait_parts:
                    lines.append(f"    Personality (Big Five): {', '.join(trait_parts)}")

        if persona_instructions:
            lines.append(f"\n  Scene-specific persona directives: {persona_instructions}")

        return "\n".join(lines)

    def _format_student_metadata(self, student_metadata: Dict[str, Any]) -> str:
        """Format student engagement metrics for the grading prompt.

        Header explicitly instructs the LLM not to penalize based on these metrics.
        Only includes non-zero values.
        """
        if not student_metadata:
            return ""

        lines = [
            "STUDENT ENGAGEMENT CONTEXT (informational only — do not penalize based on these metrics):"
        ]

        total_attempts = student_metadata.get("total_attempts", 0)
        if total_attempts:
            lines.append(f"  Total attempts across simulation: {total_attempts}")

        hints_used = student_metadata.get("hints_used", 0)
        if hints_used:
            lines.append(f"  Hints used: {hints_used}")

        forced = student_metadata.get("forced_progressions", 0)
        if forced:
            lines.append(f"  Times auto-progressed: {forced}")

        time_spent = student_metadata.get("total_time_spent")
        if time_spent:
            minutes = round(time_spent / 60)
            lines.append(f"  Total time spent: {minutes} minutes")

        sessions = student_metadata.get("session_count", 0)
        if sessions:
            lines.append(f"  Number of sessions: {sessions}")

        # Only return content if we have at least one metric
        if len(lines) <= 1:
            return ""

        return "\n".join(lines)

    def _format_scene_extended_context(self, scene: SimulationScene) -> str:
        """Format additional scene context fields (scene_context, goal_criteria)."""
        parts = []

        if scene.scene_context:
            parts.append(f"Scene Context: {scene.scene_context}")

        if scene.goal_criteria:
            if isinstance(scene.goal_criteria, dict):
                criteria_text = json.dumps(scene.goal_criteria, indent=2)
            else:
                criteria_text = str(scene.goal_criteria)
            parts.append(f"Detailed Goal Criteria:\n{criteria_text}")

        return "\n".join(parts)

    async def grade_scene(
        self,
        scene: SimulationScene,
        formatted_conversation: str,
        grading_context: Dict[str, Any],
        user_progress_id: int,
        scene_persona_context: Optional[Dict[str, Any]] = None,
        student_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Grade a single scene with full conversation context using structured output.

        Args:
            scene: The scene being graded
            formatted_conversation: Full dialogue thread (student + AI persona messages)
            grading_context: Dict containing simulation_title, simulation_description,
                           student_role, learning_objectives, rubric_* fields, grading_prompt
            user_progress_id: The user progress ID for tracking
            scene_persona_context: Optional dict with scene_personas, scene_context, goal_criteria, persona_instructions
            student_metadata: Optional dict with engagement metrics (total_attempts, hints_used, etc.)
        """

        # Create callback handler
        callback_handler = GradingCallbackHandler(user_progress_id, scene.id)

        # Extract context fields
        simulation_title = grading_context.get("simulation_title", "Unknown Simulation")
        simulation_description = grading_context.get("simulation_description", "")
        simulation_challenge = grading_context.get("simulation_challenge", "")
        simulation_industry = grading_context.get("simulation_industry", "")
        student_role = grading_context.get("student_role", "Student")
        learning_objectives = grading_context.get("learning_objectives", [])
        rubric_title = grading_context.get("rubric_title")
        rubric_criteria = grading_context.get("rubric_criteria")
        rubric_performance_levels = grading_context.get("rubric_performance_levels")
        grading_prompt = grading_context.get("grading_prompt")

        # Build simulation context section
        simulation_context = f"""SIMULATION CONTEXT:
Title: {simulation_title}
Description: {simulation_description}
Student Role: {student_role}"""

        if simulation_industry:
            simulation_context += f"\nIndustry: {simulation_industry}"

        if simulation_challenge:
            simulation_context += f"\n\nCORE CHALLENGE:\n{simulation_challenge}"

        if learning_objectives:
            objectives_text = "\n".join(f"  - {obj}" for obj in learning_objectives)
            simulation_context += f"\n\nLearning Objectives:\n{objectives_text}"

        # Build persona context section
        persona_section = ""
        if scene_persona_context:
            persona_section = self._format_scene_persona_context(
                scene_persona_context.get("scene_personas", []),
                scene_persona_context.get("persona_instructions")
            )

        # Build extended scene context
        extended_scene_context = self._format_scene_extended_context(scene)

        # Build student metadata section
        student_section = ""
        if student_metadata:
            student_section = self._format_student_metadata(student_metadata)

        # Prepare rubric information
        rubric_info = ""
        if rubric_criteria and rubric_title and rubric_performance_levels:
            max_points = max([level.get('points', 0) for level in rubric_performance_levels]) if rubric_performance_levels else 0

            rubric_info = f"""
RUBRIC INFORMATION:
Rubric Title: {rubric_title}

Performance Levels:"""
            for level in rubric_performance_levels:
                rubric_info += f"\n- {level.get('name', 'Unnamed Level')}: {level.get('points', 0)} points"

            rubric_info += "\n\nRubric Criteria:"
            for i, criterion in enumerate(rubric_criteria, 1):
                rubric_info += f"\n{i}. {criterion.get('description', 'No description provided')} (Max: {max_points} points)"
                descriptions = criterion.get('descriptions', {})
                for level in rubric_performance_levels:
                    level_name = level.get('name', 'Unnamed Level')
                    description = descriptions.get(level_name, 'No description provided')
                    rubric_info += f"\n   {level_name} ({level.get('points', 0)} pts): {description}"

        # Build professor grading instructions if provided
        professor_instructions = ""
        if grading_prompt:
            professor_instructions = f"""
PROFESSOR'S GRADING INSTRUCTIONS:
{grading_prompt}"""

        # Build the grading prompt
        grading_prompt_text = f"""Grade this business simulation scene: {scene.title}

{simulation_context}

{persona_section}

SCENE DETAILS:
Scene Title: {scene.title}
Scene Description: {scene.description}
Scene Goal: {scene.user_goal}
Success Metric: {scene.success_metric or scene.user_goal}
{extended_scene_context}
{rubric_info}
{professor_instructions}

{student_section}

FULL CONVERSATION THREAD:
(This includes both student messages and AI persona responses to provide full context)
{formatted_conversation}

GRADING INSTRUCTIONS:
Evaluate the student's performance and provide:
1. An overall score (0-100) reflecting the quality of engagement
2. Scores for each rubric criterion if provided
3. Assessment of business thinking quality
4. Key strengths (or "None identified" if none)
5. Areas for improvement
6. Actionable recommendations
7. Consider persona dynamics — if a persona is intentionally challenging, don't penalize the student for encountering resistance

Be generous with sophisticated business thinking. Score should reflect actual engagement quality."""

        # Build messages for the LLM
        messages = [
            SystemMessage(content=self._get_scene_grading_system_prompt()),
            HumanMessage(content=grading_prompt_text)
        ]

        try:
            # Get structured response - NO PARSING NEEDED
            result: SceneGradingResult = await self.scene_grader.ainvoke(
                messages,
                config={"callbacks": [callback_handler]}
            )

            # Log for debugging
            print(f"[GRADING DEBUG] Scene {scene.id}: Structured output score={result.overall_score}")

            return {
                "score": result.overall_score,  # Direct access, type-safe
                "feedback": self._format_scene_feedback(result),
                "scene_id": scene.id,
                "scene_title": scene.title,
                "user_progress_id": user_progress_id,
                "grading_metadata": callback_handler.grading_metadata,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                # Include structured data for potential future use
                "criteria_breakdown": [
                    {
                        "criterion_name": c.criterion_name,
                        "score": c.score,
                        "max_points": c.max_points,
                        "performance_level": c.performance_level,
                        "reasoning": c.reasoning
                    }
                    for c in result.criteria_breakdown
                ],
                "business_thinking_quality": result.business_thinking_quality,
                "key_strengths": result.key_strengths,
                "areas_for_improvement": result.areas_for_improvement,
                "actionable_recommendations": result.actionable_recommendations
            }

        except Exception as e:
            print(f"Error in scene grading: {e}")
            return {
                "score": 0,
                "feedback": f"Grading error: {str(e)}",
                "scene_id": scene.id,
                "error": True
            }

    async def grade_overall_simulation(
        self,
        simulation_id: int,
        scene_grades: List[Dict[str, Any]],
        learning_objectives: List[str],
        user_progress_id: int,
        grading_context: Optional[Dict[str, Any]] = None,
        rubric_total_points: Optional[int] = None,
        student_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Grade the overall simulation using structured output.

        Args:
            simulation_id: The simulation ID
            scene_grades: List of scene grade results
            learning_objectives: List of learning objectives
            user_progress_id: The user progress ID
            grading_context: Optional dict with simulation context and rubric info
            rubric_total_points: Optional total rubric points (default 100)
            student_metadata: Optional dict with engagement metrics
        """

        # Create callback handler
        callback_handler = GradingCallbackHandler(user_progress_id, 0)

        # Use rubric_total_points if provided, otherwise default to 100
        if rubric_total_points is None:
            rubric_total_points = 100

        # Extract context if provided
        grading_context = grading_context or {}
        simulation_title = grading_context.get("simulation_title", "Unknown Simulation")
        simulation_description = grading_context.get("simulation_description", "")
        simulation_challenge = grading_context.get("simulation_challenge", "")
        simulation_industry = grading_context.get("simulation_industry", "")
        student_role = grading_context.get("student_role", "Student")
        rubric_title = grading_context.get("rubric_title")
        rubric_criteria = grading_context.get("rubric_criteria")
        rubric_performance_levels = grading_context.get("rubric_performance_levels")
        grading_prompt = grading_context.get("grading_prompt")

        # Prepare scene grades summary
        scene_summary = "\n".join([
            f"Scene {i+1}: {grade.get('scene_title', 'Unknown')} - Score: {grade.get('score', 0)}/{rubric_total_points}"
            for i, grade in enumerate(scene_grades)
        ])

        # Calculate overall score based on rubric_total_points
        scores = [grade.get('score', 0) for grade in scene_grades if isinstance(grade.get('score'), (int, float))]
        if scores:
            avg_scene_score = sum(scores) / len(scores)
            if rubric_total_points != 100:
                calculated_score = (avg_scene_score / 100) * rubric_total_points
            else:
                calculated_score = avg_scene_score
        else:
            calculated_score = 0

        # Build simulation context section
        simulation_context = f"""SIMULATION CONTEXT:
Title: {simulation_title}
Description: {simulation_description}
Student Role: {student_role}"""

        if simulation_industry:
            simulation_context += f"\nIndustry: {simulation_industry}"

        if simulation_challenge:
            simulation_context += f"\n\nCORE CHALLENGE:\n{simulation_challenge}"

        # Build student metadata section
        student_section = ""
        if student_metadata:
            student_section = self._format_student_metadata(student_metadata)

        # Build rubric information if available
        rubric_info = ""
        if rubric_criteria and rubric_title and rubric_performance_levels:
            max_points = max([level.get('points', 0) for level in rubric_performance_levels]) if rubric_performance_levels else 0

            rubric_info = f"""
RUBRIC INFORMATION:
Rubric Title: {rubric_title}

Performance Levels:"""
            for level in rubric_performance_levels:
                rubric_info += f"\n- {level.get('name', 'Unnamed Level')}: {level.get('points', 0)} points"

            rubric_info += "\n\nRubric Criteria:"
            for i, criterion in enumerate(rubric_criteria, 1):
                rubric_info += f"\n{i}. {criterion.get('description', 'No description provided')} (Max: {max_points} points)"

        # Build professor grading instructions if provided
        professor_instructions = ""
        if grading_prompt:
            professor_instructions = f"""
PROFESSOR'S GRADING INSTRUCTIONS:
{grading_prompt}"""

        # Build the grading prompt
        grading_prompt_text = f"""Grade the overall business simulation performance:

{simulation_context}

LEARNING OBJECTIVES:
{chr(10).join(f"• {obj}" for obj in learning_objectives)}
{rubric_info}
{professor_instructions}

{student_section}

SCENE PERFORMANCE SUMMARY:
{scene_summary}

CALCULATED AVERAGE SCORE: {calculated_score:.1f}/{rubric_total_points} points

GRADING INSTRUCTIONS:
Provide a comprehensive evaluation considering:
1. Overall strategic thinking and business perspective demonstrated
2. Problem-solving approach across scenes
3. Communication and presentation skills
4. Critical thinking and analysis
5. Practical application and real-world relevance
6. Learning integration across scenarios

Your overall_score should be 0-100 (it will be scaled to rubric points if needed).
Be generous when students show sophisticated business understanding."""

        # Build messages for the LLM
        messages = [
            SystemMessage(content=self._get_overall_grading_system_prompt()),
            HumanMessage(content=grading_prompt_text)
        ]

        try:
            # Get structured response - NO PARSING NEEDED
            result: OverallGradingResult = await self.overall_grader.ainvoke(
                messages,
                config={"callbacks": [callback_handler]}
            )

            # Use the LLM's score, scaled to rubric_total_points if needed
            final_score = result.overall_score
            if rubric_total_points != 100:
                final_score = (result.overall_score / 100) * rubric_total_points

            print(f"[GRADING DEBUG] Overall simulation {simulation_id}: Structured output score={result.overall_score}, final={final_score}")

            return {
                "overall_score": round(final_score, 1),
                "feedback": self._format_overall_feedback(result),
                "simulation_id": simulation_id,
                "user_progress_id": user_progress_id,
                "scene_count": len(scene_grades),
                "grading_metadata": callback_handler.grading_metadata,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "rubric_total_points": rubric_total_points,
                # Include structured data
                "performance_summary": result.performance_summary,
                "key_strengths": result.key_strengths,
                "areas_for_improvement": result.areas_for_improvement,
                "actionable_recommendations": result.actionable_recommendations,
                "business_acumen_insights": result.business_acumen_insights
            }

        except Exception as e:
            print(f"Error in overall grading: {e}")
            return {
                "overall_score": round(calculated_score, 1),
                "feedback": f"Overall grading error: {str(e)}",
                "simulation_id": simulation_id,
                "error": True,
                "rubric_total_points": rubric_total_points
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

        # Use simple LLM call for goal validation
        messages = [
            SystemMessage(content="""You are evaluating whether a user has achieved a business simulation scene goal.

Be moderately lenient: If the user's response shows good-faith business analysis and addresses the core challenge, mark the goal as achieved.

Respond with a JSON object containing:
- goal_achieved: boolean
- confidence_score: float (0.0-1.0)
- reasoning: string (brief explanation)
- next_action: "continue" | "progress" | "hint" | "force_progress"
- hint_message: string or null (if action is "hint", provide business-focused guidance)"""),
            HumanMessage(content=f"""Evaluate if the user has achieved the business simulation scene goal:

SCENE GOAL: {scene_goal}
SCENE DESCRIPTION: {scene_description}
CURRENT ATTEMPTS: {current_attempts}/{max_attempts}

CONVERSATION HISTORY:
{conversation_history}

EVALUATION CRITERIA:
- Goal Achievement: Has the user demonstrated understanding and addressed the core business challenge?
- Strategic Thinking: Shows evidence of strategic business perspective and analysis
- Practical Application: Demonstrates real-world business application
- Communication Quality: Professional communication appropriate for business context""")
        ]

        try:
            response = await self.llm.ainvoke(messages)
            return self._parse_goal_validation_response(response.content)

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
            import re
            import json

            # Try to extract JSON
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
