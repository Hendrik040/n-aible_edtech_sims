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
        
        # Grade each scene
        scene_grades = []
        for scene in scenes:
            # Get user responses (messages) for this scene
            conversation_logs = self.repository.get_conversation_logs(
                user_progress_id=user_progress_id,
                scene_id=scene.id
            )
            
            # Filter for user messages only, excluding one-word command words (begin, help)
            # Commands are only valid as single words - "begin now" is a regular message
            command_words = {"begin", "help"}
            user_responses = [
                {
                    "content": log.message_content,
                    "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                    "order": log.message_order
                }
                for log in conversation_logs
                if log.message_type == "user"
                and not (log.message_content.lower().strip() in command_words and len(log.message_content.split()) == 1)
            ]
            
            # Skip scenes with no user responses
            if not user_responses:
                continue
            
            # Grade the scene
            try:
                scene_grade = await grading_agent.grade_scene(
                    scene=scene,
                    user_responses=user_responses,
                    user_progress_id=user_progress_id
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
        
        # Grade overall simulation
        try:
            overall_grade = await grading_agent.grade_overall_simulation(
                simulation_id=simulation.id,
                scene_grades=scene_grades,
                learning_objectives=learning_objectives,
                user_progress_id=user_progress_id,
                rubric_total_points=100  # Default to 100, can be made configurable
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

