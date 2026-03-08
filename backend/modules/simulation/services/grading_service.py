"""
Grading Service.

Handles simulation grading operations using the grading agent.
"""

import secrets
from typing import Dict, Any
import logging
from sqlalchemy.orm import Session
from datetime import datetime

from modules.simulation.repository import SimulationRepository
from common.db.models import StudentSimulationInstance
from common.exceptions import NotFoundError, ForbiddenError
from common.services.cache_service import redis_manager


logger = logging.getLogger(__name__)

# TTL for grading cache: 7 days (604800 seconds)
# Grading results should persist for a reasonable time but not forever
GRADING_CACHE_TTL = 604800


class GradingService:
    """Service for simulation grading operations."""

    def __init__(self, db: Session, repository: SimulationRepository):
        self.db = db
        self.repository = repository

    def _extract_grading_context(self, simulation) -> Dict[str, Any]:
        """Extract grading context from simulation (no new DB queries needed).

        Returns a dict with:
        - simulation_title: Title of the simulation
        - simulation_description: Description/background
        - student_role: Student's role in the simulation
        - learning_objectives: List of learning objectives
        - rubric_title: Title from grading_config
        - rubric_criteria: Criteria from grading_config
        - rubric_performance_levels: Performance levels from grading_config
        - grading_prompt: Custom professor grading instructions
        """
        grading_config = simulation.grading_config or {}

        learning_objectives_raw = simulation.learning_objectives
        if isinstance(learning_objectives_raw, str):
            normalized_learning_objectives = [
                item.strip()
                for item in learning_objectives_raw.splitlines()
                if item.strip()
            ]
            if not normalized_learning_objectives:
                normalized_learning_objectives = (
                    [learning_objectives_raw.strip()]
                    if learning_objectives_raw.strip()
                    else []
                )
        elif isinstance(learning_objectives_raw, list):
            normalized_learning_objectives = learning_objectives_raw
        else:
            normalized_learning_objectives = []

        return {
            "simulation_title": simulation.title,
            "simulation_description": simulation.description or "",
            "simulation_challenge": simulation.challenge or "",
            "simulation_industry": simulation.industry or "",
            "student_role": simulation.student_role,
            "learning_objectives": normalized_learning_objectives,
            "rubric_title": grading_config.get("title"),
            "rubric_criteria": grading_config.get("criteria"),
            "rubric_performance_levels": grading_config.get("performance_levels"),
            "grading_prompt": simulation.grading_prompt,
        }

    def _format_conversation_thread(
        self,
        conversation_logs,
        personas_by_id: Dict[int, Any]
    ) -> str:
        """Format conversation logs into a readable dialogue thread.

        Args:
            conversation_logs: List of ConversationLog objects
            personas_by_id: Dict mapping persona_id to SimulationPersona objects

        Returns:
            Formatted string like:
            [1] System: Welcome to the simulation...
            [2] Student: Hello, how can we solve this?
            [3] Mingyang Wu (AI Persona): Let's start by identifying issues...
        """
        if not conversation_logs:
            return ""

        lines = []
        for log in conversation_logs:
            order = log.message_order
            message = log.message_content

            # Determine speaker name
            if log.message_type == "user":
                speaker = "Student"
            elif log.message_type == "ai_persona" and log.persona_id:
                persona = personas_by_id.get(log.persona_id)
                if persona:
                    speaker = f"{persona.name} (AI Persona)"
                else:
                    speaker = log.sender_name or "AI Persona"
            elif log.message_type == "system":
                speaker = "System"
            elif log.message_type == "orchestrator":
                speaker = "Orchestrator"
            else:
                speaker = log.sender_name or log.message_type

            lines.append(f"[{order}] {speaker}: {message}")

        return "\n".join(lines)

    async def get_simulation_grading(
        self,
        user_progress_id: int,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Get simulation grading.
        
        Returns AI-generated grades and feedback for the simulation.
        """
        user_progress = self.repository.get_user_progress_by_id(user_progress_id)
        if not user_progress:
            raise NotFoundError("User progress not found")
        
        if user_progress.user_id != user_id:
            raise ForbiddenError("Access denied: You can only access your own simulation grades")
        
        # Check Redis cache first for full grading payload (includes scene breakdown)
        cache_key = f"grading:{user_progress_id}"
        cached_grading = redis_manager.get(cache_key)
        if cached_grading:
            logger.info(f"Returning cached grading from Redis for user_progress_id={user_progress_id}")
            return cached_grading
        
        # Check if grading already exists in DB (fallback if Redis cache miss)
        instance = self.repository.get_student_simulation_instance(user_progress_id)
        
        # If grading exists in DB but not in Redis, return basic data and log warning
        if instance and instance.ai_grade is not None and instance.ai_feedback:
            logger.warning(
                f"Grading exists in DB but not in Redis cache for user_progress_id={user_progress_id}. "
                f"Returning basic data without scene breakdown. Consider regenerating to populate cache."
            )
            # Return basic cached data (no scene breakdown available from DB-only storage)
            return {
                "overall_score": instance.ai_grade,
                "overall_feedback": instance.ai_feedback,
                "scenes": [],  # Scene breakdown not available from DB-only storage
                "rubric_total_points": 100
            }
        
        # Import grading agent (lazy import to avoid circular dependencies)
        try:
            from modules.simulation.agents.grading_agent import grading_agent
        except Exception as e:
            # Fallback if grading agent not available (catches ImportError and initialization errors)
            logger.exception("Error importing grading agent")
            return {
                "overall_score": 0,
                "overall_feedback": "Grading agent not available. Please try again later.",
                "scenes": [],
                "rubric_total_points": 100
            }
        
        # Get simulation and scenes
        simulation = self.repository.get_simulation_by_id(user_progress.simulation_id)
        if not simulation:
            raise NotFoundError("Simulation not found")
        
        scenes = self.repository.get_scenes_by_simulation_id(user_progress.simulation_id)
        if not scenes:
            raise NotFoundError("No scenes found for this simulation")
        
        # Get learning objectives
        learning_objectives = simulation.learning_objectives or []
        if isinstance(learning_objectives, str):
            learning_objectives = [learning_objectives]

        # Extract grading context from simulation
        grading_context = self._extract_grading_context(simulation)

        # Build personas lookup for conversation formatting
        all_personas = self.repository.get_personas_by_simulation_id(simulation.id)
        personas_by_id = {p.id: p for p in all_personas}

        # Batch-fetch personas with involvement levels for all scenes (1 query)
        scene_ids = [scene.id for scene in scenes]
        scene_personas_map = self.repository.get_personas_with_involvement_for_scenes(scene_ids)

        # Build student metadata from user_progress (already loaded, no extra queries)
        student_metadata = {
            "total_attempts": getattr(user_progress, "total_attempts", 0) or 0,
            "hints_used": getattr(user_progress, "hints_used", 0) or 0,
            "forced_progressions": getattr(user_progress, "forced_progressions", 0) or 0,
            "total_time_spent": getattr(user_progress, "total_time_spent", None),
            "session_count": getattr(user_progress, "session_count", 0) or 0,
            "completion_percentage": getattr(user_progress, "completion_percentage", 0.0) or 0.0,
        }

        # Grade each scene
        scene_grades = []
        for scene in scenes:
            # Get ALL conversation logs for this scene (not just user messages)
            conversation_logs = self.repository.get_conversation_logs(
                user_progress_id=user_progress_id,
                scene_id=scene.id
            )

            # Check if there are any user messages (excluding commands)
            command_words = {"begin", "help"}
            has_user_responses = any(
                log.message_type == "user"
                and not (log.message_content.lower().strip() in command_words and len(log.message_content.split()) == 1)
                for log in conversation_logs
            )

            # Skip scenes with no user responses
            if not has_user_responses:
                continue

            # Format full conversation thread (includes AI persona responses)
            formatted_conversation = self._format_conversation_thread(
                conversation_logs, personas_by_id
            )

            # Build per-scene context for richer grading
            per_scene_context = {
                "scene_personas": scene_personas_map.get(scene.id, []),
                "scene_context": scene.scene_context,
                "goal_criteria": scene.goal_criteria,
                "persona_instructions": scene.persona_instructions,
            }

            # Grade the scene with full context
            try:
                scene_grade = await grading_agent.grade_scene(
                    scene=scene,
                    formatted_conversation=formatted_conversation,
                    grading_context=grading_context,
                    user_progress_id=user_progress_id,
                    scene_persona_context=per_scene_context,
                    student_metadata=student_metadata
                )
                scene_grades.append(scene_grade)
            except Exception as e:
                logger.exception("Error grading scene", extra={"scene_id": scene.id, "user_progress_id": user_progress_id})
                # Add error entry for this scene
                scene_grades.append({
                    "scene_id": scene.id,
                    "scene_title": scene.title,
                    "score": 0,
                    "feedback": "Error grading scene. Please try again later.",
                    "error": True
                })
        
        # If no scenes were graded, return empty result
        if not scene_grades:
            return {
                "overall_score": 0,
                "overall_feedback": "No user responses found to grade.",
                "scenes": [],
                "rubric_total_points": 100
            }
        
        # Grade overall simulation with full context
        try:
            overall_grade = await grading_agent.grade_overall_simulation(
                simulation_id=simulation.id,
                scene_grades=scene_grades,
                learning_objectives=learning_objectives,
                user_progress_id=user_progress_id,
                grading_context=grading_context,
                rubric_total_points=100,  # Default to 100, can be made configurable
                student_metadata=student_metadata
            )
        except Exception as e:
            logger.exception("Error grading overall simulation", extra={"simulation_id": simulation.id, "user_progress_id": user_progress_id})
            # Fallback: calculate average score from scene grades
            scores = [g.get('score', 0) for g in scene_grades if not g.get('error')]
            overall_score = sum(scores) / len(scores) if scores else 0
            overall_grade = {
                "overall_score": round(overall_score, 1),
                "overall_feedback": "Error during overall grading. Please try again later.",
                "scenes": scene_grades,
                "rubric_total_points": 100,
                "error": True
            }
        
        # Extract feedback - the grading agent returns it as "feedback"
        # The full markdown-formatted feedback text is in the "feedback" field
        overall_feedback_text = overall_grade.get("feedback", "")
        
        # Build full grading payload with scene breakdown
        grading_payload = {
            "overall_score": overall_grade.get("overall_score", 0),
            "overall_feedback": overall_feedback_text,  # Use the full feedback text
            "scenes": scene_grades,
            "rubric_total_points": overall_grade.get("rubric_total_points", 100)
        }
        
        # Store grading results in both Redis cache and database
        # Redis cache stores the full payload (including scene breakdown)
        # Database stores only overall_score and overall_feedback (due to schema limitations)
        cache_key = f"grading:{user_progress_id}"
        redis_manager.set(cache_key, grading_payload, ttl=GRADING_CACHE_TTL)
        logger.info(f"Cached full grading payload in Redis for user_progress_id={user_progress_id} with TTL={GRADING_CACHE_TTL}s")
        
        # Store grading results in StudentSimulationInstance using dedicated fields
        # (instance_data field is not available in the model)
        from common.db.models import User
        
        # Check if this is a test simulation (professor playground)
        # Test simulations should not save data to database since they're just for testing
        user = self.db.query(User).filter(User.id == user_progress.user_id).first()
        is_test_simulation = user and user.role in ['professor', 'admin'] if user else False
        
        # Only save to database if it's NOT a test simulation
        # Test simulations (professor playground) should not persist data
        if not is_test_simulation:
            if not instance:
                # Generate unique_id for the instance
                unique_id = f"SSI-{secrets.token_urlsafe(8).upper()}"
                
                # Create instance if it doesn't exist
                # Note: cohort_assignment_id is None for test simulations (professor/test-simulations)
                # student_id comes from user_progress.user_id
                instance = StudentSimulationInstance(
                    unique_id=unique_id,
                    student_id=user_progress.user_id,  # Get student_id from user_progress
                    user_progress_id=user_progress_id,
                    cohort_assignment_id=getattr(user_progress, "cohort_assignment_id", None),
                    ai_grade=overall_grade.get("overall_score", 0),
                    ai_feedback=overall_feedback_text,
                    ai_graded_at=datetime.utcnow()
                )
                self.db.add(instance)
            else:
                # Update existing instance with dedicated fields
                instance.ai_grade = overall_grade.get("overall_score", 0)
                instance.ai_feedback = overall_feedback_text
                instance.ai_graded_at = datetime.utcnow()
            
            self.db.commit()
            logger.info(f"Persisted grading to database for user_progress_id={user_progress_id}")
        
        # Return full grading payload (includes scene breakdown)
        return grading_payload

