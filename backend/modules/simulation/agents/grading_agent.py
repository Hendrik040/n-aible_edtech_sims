"""
Grading Agent for AI Agent Education Platform
Handles LLM-driven grading and feedback with LangChain structured output
"""

import json
import re
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
        return """You are a rigorous grading agent for business simulation education with expertise in business case analysis and strategic thinking.

Your role is to evaluate student responses against explicit evidence standards and provide structured grading output.

GRADING APPROACH:
- Award points only when the student's response contains explicit evidence that justifies that level
- Use the provided rubric criteria and performance levels as the authoritative standard
- Consider the full conversation thread: assess the quality of the student's reasoning, not just their conclusion
- References to uploaded materials are expected at higher score bands, not a bonus

SCORING STANDARDS (apply strictly):
- 90-100: Reserved for responses demonstrating original insight, correct application of multiple business frameworks, specific evidence or data, and explicit acknowledgement of tradeoffs. Fewer than 15% of responses should reach this band.
- 75-89: Solid understanding with at least one framework applied with precision, claims that are supported rather than merely asserted, and meaningful engagement with the scene's nuances.
- 60-74: Basic understanding present but relies on generic business language, lacks specificity, or makes unsupported assertions. The core question is addressed but shallowly.
- 45-59: Partial engagement — the student identifies the problem but does not analyse it, or provides a response applicable to any business situation without case-specific reasoning.
- 0-44: Minimal, off-topic, purely generic, or superficial. The student has not demonstrated meaningful engagement with the scene's challenge.

ANTI-INFLATION RULES (enforce without exception):
1. A response that merely restates the problem without analysis cannot exceed 55.
2. A response using only generic business terms (e.g. "improve efficiency", "focus on the customer") without specific reasoning cannot exceed 60.
3. A response that does not address at least one rubric criterion explicitly cannot exceed 65.
4. The overall score must not exceed the average criterion score by more than 5 points.
5. Good faith effort and apparent enthusiasm do not raise scores — only demonstrated analytical quality does.

Provide your evaluation as a structured response with all required fields."""

    def _get_overall_grading_system_prompt(self) -> str:
        """Generate system prompt for overall grading"""
        return """You are a rigorous grading agent evaluating overall performance across a business simulation.

Your role is to synthesise demonstrated analytical quality across multiple scenes into a final assessment.

EVALUATION CRITERIA:
- Overall Strategic Thinking: Did the student demonstrate a strategic business perspective backed by reasoning?
- Problem-Solving Approach: Quality of problem identification and solution development across scenes
- Communication & Presentation: Professional communication with clear, specific arguments
- Critical Analysis: Depth of analysis and explicit consideration of tradeoffs and alternatives
- Practical Application: Real-world relevance grounded in evidence, not generic advice
- Learning Integration: Consistent application of concepts — not just in one scene

SCORING STANDARDS (apply strictly):
- 90-100: Consistently demonstrated original insight, framework application, and evidence-backed reasoning across all scenes. Fewer than 15% of students should reach this band.
- 75-89: Generally solid performance with supported arguments. Some scenes may be stronger than others but overall quality is clear.
- 60-74: Basic understanding shown across scenes but relies on generic language, lacks specificity, or reasoning is frequently unsupported.
- 45-59: Inconsistent engagement — meaningful in some scenes, superficial in others.
- 0-44: Minimal or generic engagement across the simulation.

ANTI-INFLATION RULES:
- The overall score must reflect aggregate analytical quality across scenes, not an optimistic interpretation of potential.
- Do not adjust the overall score upward from what the scene evidence supports.
- Effort, word count, and good intentions do not raise scores.

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

    def _run_automated_checks(
        self,
        formatted_conversation: str,
        automated_checks: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run Layer 1 deterministic checks on code submissions.

        Scans the conversation for code_submission entries and checks whether
        the code ran successfully and the output contains expected structures.
        """
        results: Dict[str, Any] = {
            "code_ran": False,
            "columns_found": [],
            "missing_columns": [],
            "rows_sufficient": None,
            "output_keywords_found": [],
            "output_keywords_missing": [],
        }

        # Extract the last successful code output from conversation.
        # code_ran is only True when we find an actual execution output block —
        # a bare code_submission or ```python fence means pasted/typed code, not
        # necessarily executed code, so we don't count that as "ran".
        output_text = ""
        code_ran = False

        # Only an "Output:" block proves the code was actually executed
        output_blocks = re.findall(
            r"Output:\s*```\s*(.*?)```", formatted_conversation, re.DOTALL
        )
        if output_blocks:
            output_text = output_blocks[-1].strip()
            code_ran = True

        results["code_ran"] = code_ran

        must_run = automated_checks.get("must_run", False)
        if must_run and not code_ran:
            results["code_ran"] = False

        # Check expected columns
        expected_columns = automated_checks.get("expected_columns", [])
        if expected_columns and output_text:
            for col in expected_columns:
                if col.lower() in output_text.lower():
                    results["columns_found"].append(col)
                else:
                    results["missing_columns"].append(col)

        # Check minimum row count
        expected_rows_min = automated_checks.get("expected_rows_min")
        if expected_rows_min is not None and output_text:
            # Count non-empty lines in output as a rough row proxy
            data_lines = [
                line for line in output_text.split("\n")
                if line.strip() and not line.strip().startswith(("#", "//", "---"))
            ]
            results["rows_sufficient"] = len(data_lines) >= expected_rows_min

        # Check output_must_contain keywords
        must_contain = automated_checks.get("output_must_contain", [])
        if must_contain and output_text:
            for keyword in must_contain:
                if keyword.lower() in output_text.lower():
                    results["output_keywords_found"].append(keyword)
                else:
                    results["output_keywords_missing"].append(keyword)

        return results

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
        student_metadata: Optional[Dict[str, Any]] = None,
        rag_context: Optional[str] = None,
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
            rag_context: Optional pre-retrieved grading material chunks from the vector store
        """

        # Create callback handler
        callback_handler = GradingCallbackHandler(user_progress_id, scene.id)

        # --- Code challenge three-layer grading ---
        scene_type = getattr(scene, "scene_type", None) or "conversation"
        if scene_type == "code_challenge":
            return await self._grade_code_challenge_scene(
                scene, formatted_conversation, grading_context,
                user_progress_id, callback_handler, rag_context=rag_context,
            )

        # --- Standard conversation scene grading (existing logic below) ---

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

        # Build RAG grading materials section if available
        rag_section = ""
        if rag_context:
            rag_section = f"""
PROFESSOR'S UPLOADED GRADING MATERIALS:
(Use these materials as the authoritative reference for evaluation standards and expectations)
{rag_context}"""

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
{rag_section}

{student_section}

FULL CONVERSATION THREAD:
(This includes both student messages and AI persona responses to provide full context)
{formatted_conversation}

GRADING INSTRUCTIONS:
Evaluate the student's performance and provide:
1. An overall score (0-100) — apply the SCORING STANDARDS and ANTI-INFLATION RULES from the system prompt
2. Scores for each rubric criterion, citing specific evidence from the conversation for each
3. Assessment of business thinking quality — distinguish between generic statements and genuine analysis
4. Key strengths (or "None identified" if none)
5. Areas for improvement — be specific, not generic
6. Actionable recommendations — name exactly what the student should have done differently
7. Consider persona dynamics — if a persona is intentionally challenging, do not penalise the student for encountering resistance

Score each criterion against its rubric description. A score in the top band requires explicit evidence in the student's response, not inference about intent."""

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

    async def _grade_code_challenge_scene(
        self,
        scene: SimulationScene,
        formatted_conversation: str,
        grading_context: Dict[str, Any],
        user_progress_id: int,
        callback_handler: GradingCallbackHandler,
        rag_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Three-layer grading for code challenge scenes.

        Layer 1: Automated deterministic checks (pass/fail gates)
        Layer 2: AI evaluation of code quality, analytical rigor, business insight
        Layer 3: Communication grade (handled by existing conversation evaluation)
        """
        criteria = getattr(scene, "code_grading_criteria", None) or {}
        automated = criteria.get("automated_checks", {})
        weights = criteria.get("grading_weights", {
            "code_quality": 25, "analytical_rigor": 25,
            "business_insight": 25, "communication": 25,
        })
        rubric_prompt = criteria.get(
            "rubric_prompt",
            "Evaluate the student's analytical approach and code quality.",
        )

        # Layer 1: Run automated checks
        auto_results = self._run_automated_checks(formatted_conversation, automated)

        simulation_title = grading_context.get("simulation_title", "Unknown Simulation")
        simulation_description = grading_context.get("simulation_description", "")
        student_role = grading_context.get("student_role", "Student")

        # Build RAG grading materials section if available
        rag_section = ""
        if rag_context:
            rag_section = f"""
PROFESSOR'S UPLOADED GRADING MATERIALS:
(Use these materials as the authoritative reference for evaluation standards and expectations)
{rag_context}"""

        # Layer 2 + 3: AI evaluation (code + conversation combined)
        grading_prompt_text = f"""Grade this CODE CHALLENGE scene in a business simulation.

SIMULATION CONTEXT:
Title: {simulation_title}
Description: {simulation_description}
Student Role: {student_role}

SCENE DETAILS:
Scene Title: {scene.title}
Scene Description: {scene.description}
Scene Goal: {scene.user_goal}
Success Metric: {scene.success_metric or scene.user_goal}

PROFESSOR'S RUBRIC:
{rubric_prompt}
{rag_section}

AUTOMATED CHECK RESULTS (pre-computed):
{json.dumps(auto_results, indent=2)}

GRADING WEIGHTS:
- Code Quality: {weights.get("code_quality", 25)}%
- Analytical Rigor: {weights.get("analytical_rigor", 25)}%
- Business Insight: {weights.get("business_insight", 25)}%
- Communication: {weights.get("communication", 25)}%

FULL CONVERSATION AND CODE SUBMISSIONS:
{formatted_conversation}

GRADING INSTRUCTIONS:
1. Evaluate the student's CODE and OUTPUT for correctness, analytical rigor, and business insight.
2. Evaluate their COMMUNICATION with personas — did they defend their analysis, incorporate feedback?
3. If automated checks failed (code didn't run, missing columns), factor that into Code Quality.
4. Score overall 0-100 using the weights above. Apply the SCORING STANDARDS and ANTI-INFLATION RULES from the system prompt.
5. Credit creative analytical approaches only when the student demonstrates why their approach is valid and acknowledges its limitations. Novelty alone does not earn points."""

        messages = [
            SystemMessage(content=self._get_scene_grading_system_prompt()),
            HumanMessage(content=grading_prompt_text),
        ]

        try:
            result: SceneGradingResult = await self.scene_grader.ainvoke(
                messages, config={"callbacks": [callback_handler]}
            )

            print(f"[GRADING DEBUG] Code scene {scene.id}: score={result.overall_score}")

            return {
                "score": result.overall_score,
                "feedback": self._format_scene_feedback(result),
                "scene_id": scene.id,
                "scene_title": scene.title,
                "user_progress_id": user_progress_id,
                "grading_metadata": callback_handler.grading_metadata,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "criteria_breakdown": [
                    {
                        "criterion_name": c.criterion_name,
                        "score": c.score,
                        "max_points": c.max_points,
                        "performance_level": c.performance_level,
                        "reasoning": c.reasoning,
                    }
                    for c in result.criteria_breakdown
                ],
                "business_thinking_quality": result.business_thinking_quality,
                "key_strengths": result.key_strengths,
                "areas_for_improvement": result.areas_for_improvement,
                "actionable_recommendations": result.actionable_recommendations,
                "automated_check_results": auto_results,
                "scene_type": "code_challenge",
            }

        except Exception as e:
            print(f"Error in code challenge grading: {e}")
            return {
                "score": 0,
                "feedback": f"Grading error: {str(e)}",
                "scene_id": scene.id,
                "error": True,
                "automated_check_results": auto_results,
                "scene_type": "code_challenge",
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
Apply the same scoring standards as scene grading. The overall score must reflect demonstrated performance across scenes, not an upward-adjusted interpretation of it."""

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
            SystemMessage(content="""You are evaluating whether a student has met the specific goal of a business simulation scene.

A goal is ACHIEVED only when ALL of the following are true:
1. The student's response directly addresses the stated scene goal — not just the general topic
2. The student provides reasoning, not just a conclusion or opinion
3. The response demonstrates understanding specific to this scenario, not generic business advice that could apply anywhere
4. The response consists of at least two substantive sentences that advance the analysis

A goal is NOT achieved when:
- The student provides generic advice applicable to any business situation
- The student acknowledges the problem but does not engage with it analytically
- The student only asks questions without making any substantive contribution
- The response restates the scene description without adding analysis
- The response is vague, aspirational, or lacks any supporting reasoning

When in doubt, set goal_achieved to false. Provide a hint_message that tells the student exactly what analytical step they need to take next — not generic encouragement.

Respond with a JSON object containing:
- goal_achieved: boolean
- confidence_score: float (0.0-1.0) — must be 0.65 or above to set goal_achieved true
- reasoning: string (cite specific phrases from the student's last message as evidence)
- next_action: "continue" | "progress" | "hint" | "force_progress"
- hint_message: string (required when goal_achieved is false; give a specific actionable prompt, not "try harder")"""),
            HumanMessage(content=f"""Evaluate if the student has achieved the business simulation scene goal:

SCENE GOAL: {scene_goal}
SCENE DESCRIPTION: {scene_description}
CURRENT ATTEMPTS: {current_attempts}/{max_attempts}

CONVERSATION HISTORY:
{conversation_history}

EVALUATION CRITERIA:
- Specificity: Does the student make claims specific to this scenario, or could this response apply to any business situation?
- Reasoning quality: Does the student explain WHY, not just WHAT?
- Goal alignment: Does the response directly address the stated scene goal?
- Analytical depth: Is there evidence of structured thinking, or is it surface-level observation?""")
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
                parsed = {
                    "goal_achieved": result.get("goal_achieved", False),
                    "confidence_score": result.get("confidence_score", 0.0),
                    "reasoning": result.get("reasoning", ""),
                    "next_action": result.get("next_action", "continue"),
                    "hint_message": result.get("hint_message"),
                }
                # Hard gate: confidence must reach threshold for goal to be marked achieved
                if parsed["goal_achieved"] and parsed["confidence_score"] < 0.65:
                    parsed["goal_achieved"] = False
                    parsed["next_action"] = "hint"
                    if not parsed["hint_message"]:
                        parsed["hint_message"] = (
                            "Your response is on the right track but needs more specific analysis "
                            "to meet this scene's goal. Explain your reasoning in more detail."
                        )
                return parsed

            # Fallback: JSON parse failed — default to not achieved to avoid false positives
            return {
                "goal_achieved": False,
                "confidence_score": 0.0,
                "reasoning": "Could not parse evaluation response.",
                "next_action": "continue",
                "hint_message": None,
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
