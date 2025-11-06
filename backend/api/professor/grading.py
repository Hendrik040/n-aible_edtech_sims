"""
Professor Grading API endpoints
Handles professor review and manual grading of student submissions
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timezone
import json
import logging

from database.connection import get_db
from database.models import (
    User, StudentSimulationInstance, CohortSimulation, Cohort, 
    UserProgress, ConversationLog, ScenarioScene, ScenarioPersona, GradeHistory
)
from middleware.role_auth import require_professor

router = APIRouter(prefix="/professor/grading", tags=["Professor Grading"])
logger = logging.getLogger(__name__)


class ProfessorGradeReview(BaseModel):
    """Schema for professor grade review submission"""
    grade: float
    feedback: str


class SubmissionDetailsResponse(BaseModel):
    """Response schema for submission details"""
    instance_id: int
    student_name: str
    student_email: str
    simulation_title: str
    status: str
    completion_percentage: float
    total_time_spent: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    submitted_at: Optional[datetime]
    
    # AI Grading
    ai_grade: Optional[float]
    ai_feedback: Optional[Dict[str, Any]]
    ai_graded_at: Optional[datetime]
    
    # Professor Grading
    professor_grade: Optional[float]
    professor_feedback: Optional[str]
    graded_by_name: Optional[str]
    graded_at: Optional[datetime]
    
    # Final Grade (professor override or AI)
    final_grade: Optional[float]
    final_feedback: Optional[str]
    grade_status: str
    
    # Student work
    student_responses: List[Dict[str, Any]]
    scene_details: List[Dict[str, Any]]
    conversation_history: List[Dict[str, Any]]  # Full conversation history for chat display
    
    # Full simulation data for display
    scenario: Optional[Dict[str, Any]]  # Full scenario data
    current_scene: Optional[Dict[str, Any]]  # Current scene with personas and image
    all_scenes: Optional[List[Dict[str, Any]]]  # All scenes for persona lookup


@router.get("/instances/{instance_id}/submission", response_model=SubmissionDetailsResponse)
async def get_submission_details(
    instance_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """
    Get detailed submission information for professor review
    Includes student work, AI grades, and current professor grades
    """
    # Get the instance
    instance = db.query(StudentSimulationInstance).filter(
        StudentSimulationInstance.id == instance_id
    ).first()
    
    if not instance:
        raise HTTPException(status_code=404, detail="Simulation instance not found")
    
    # Verify professor has access to this instance's cohort
    cohort_assignment = db.query(CohortSimulation).filter(
        CohortSimulation.id == instance.cohort_assignment_id
    ).first()
    
    if not cohort_assignment:
        raise HTTPException(status_code=404, detail="Cohort assignment not found")
    
    cohort = db.query(Cohort).filter(
        Cohort.id == cohort_assignment.cohort_id,
        Cohort.created_by == current_user.id
    ).first()
    
    if not cohort:
        raise HTTPException(status_code=403, detail="Not authorized to access this submission")
    
    # Get student info
    student = db.query(User).filter(User.id == instance.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    # Get simulation info
    simulation = cohort_assignment.simulation
    if not simulation:
        raise HTTPException(status_code=404, detail="Simulation not found")
    
    # Get user progress and student responses
    user_progress = instance.user_progress
    student_responses = []
    scene_details = []
    conversation_history = []  # Full conversation history for chat display
    
    if user_progress:
        # Get ALL conversation messages (both user and AI) for full chat history
        from collections import defaultdict
        
        all_messages = db.query(ConversationLog).filter(
            ConversationLog.user_progress_id == user_progress.id
        ).order_by(ConversationLog.message_order, ConversationLog.timestamp).all()
        
        # Pre-fetch personas for persona info
        persona_map = {}
        persona_ids = [msg.persona_id for msg in all_messages if msg.persona_id]
        if persona_ids:
            personas = db.query(ScenarioPersona).filter(ScenarioPersona.id.in_(persona_ids)).all()
            persona_map = {p.id: p for p in personas}
        
        # Build full conversation history
        for msg in all_messages:
            msg_content_lower = (msg.message_content or "").strip().lower()
            # Skip system messages like "begin" and "Submit for Grading"
            if msg_content_lower in ["begin", "submit for grading"]:
                continue
                
            persona_name = None
            persona_role = None
            if msg.persona_id and msg.persona_id in persona_map:
                persona = persona_map[msg.persona_id]
                persona_name = persona.name
                persona_role = persona.role
            elif msg.message_type == "ai_persona" and msg.sender_name:
                persona_name = msg.sender_name
            
            conversation_history.append({
                "id": msg.id,
                "type": msg.message_type,
                "sender": msg.sender_name or ("User" if msg.message_type == "user" else "System"),
                "content": msg.message_content,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                "scene_id": msg.scene_id,
                "persona_id": msg.persona_id,
                "persona_name": persona_name,
                "persona_role": persona_role,
                "message_order": msg.message_order
            })
        
        # Get all user messages grouped by scene (for backward compatibility)
        user_messages = [msg for msg in all_messages if msg.message_type == "user"]
        messages_by_scene = defaultdict(list)
        for msg in user_messages:
            msg_content_lower = (msg.message_content or "").strip().lower()
            if msg_content_lower not in ["begin", "submit for grading"]:
                messages_by_scene[msg.scene_id].append({
                    "id": msg.id,
                    "content": msg.message_content,
                    "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                    "order": msg.message_order
                })
        
        # Get scene details
        scenes = db.query(ScenarioScene).filter(
            ScenarioScene.scenario_id == simulation.id
        ).order_by(ScenarioScene.scene_order).all()
        
        for scene in scenes:
            scene_responses = messages_by_scene.get(scene.id, [])
            scene_details.append({
                "scene_id": scene.id,
                "title": scene.title,
                "description": scene.description,
                "user_goal": scene.user_goal,
                "success_metric": scene.success_metric,
                "responses": scene_responses
            })
            student_responses.extend(scene_responses)
    
    # Parse AI feedback if it's JSON
    ai_feedback_parsed = None
    if instance.ai_feedback:
        try:
            ai_feedback_parsed = json.loads(instance.ai_feedback)
        except (json.JSONDecodeError, TypeError):
            ai_feedback_parsed = {"text": instance.ai_feedback}
    
    # Get grader name if professor graded
    grader_name = None
    if instance.graded_by:
        grader = db.query(User).filter(User.id == instance.graded_by).first()
        if grader:
            grader_name = grader.full_name or grader.email
    
    # Determine final grade (professor override takes precedence)
    final_grade = instance.grade  # This is already set to professor grade if exists, otherwise AI grade
    final_feedback = instance.feedback  # Same logic
    
    # Get full simulation data for display (scenario, scenes, personas)
    scenario_data = None
    current_scene_data = None
    all_scenes_data = None
    
    if user_progress:
        from database.models import scene_personas
        
        # Get all scenes first for total count
        all_scenes_list = db.query(ScenarioScene).filter(
            ScenarioScene.scenario_id == simulation.id
        ).order_by(ScenarioScene.scene_order).all()
        
        # Get scenario data
        scenario_data = {
            "id": simulation.id,
            "title": simulation.title,
            "description": simulation.description,
            "challenge": simulation.challenge,
            "industry": getattr(simulation, 'industry', None),
            "learning_objectives": simulation.learning_objectives or [],
            "student_role": simulation.student_role,
            "total_scenes": len(all_scenes_list)
        }
        
        # Get current scene with full details
        if user_progress.current_scene_id:
            current_scene = db.query(ScenarioScene).filter(
                ScenarioScene.id == user_progress.current_scene_id
            ).first()
            
            if current_scene:
                # Get personas for current scene
                scene_personas_list = db.query(ScenarioPersona).join(
                    scene_personas, ScenarioPersona.id == scene_personas.c.persona_id
                ).filter(
                    scene_personas.c.scene_id == current_scene.id,
                    ScenarioPersona.deleted_at.is_(None)
                ).all()
                
                # Filter out main character (student role)
                def is_main_character(persona_name, student_role):
                    if not student_role:
                        return False
                    student_name = student_role.split('(')[0].strip().lower()
                    persona_name_clean = persona_name.strip().lower()
                    return persona_name_clean == student_name
                
                filtered_personas = [
                    p for p in scene_personas_list
                    if not is_main_character(p.name, simulation.student_role)
                ]
                
                current_scene_data = {
                    "id": current_scene.id,
                    "title": current_scene.title,
                    "description": current_scene.description,
                    "user_goal": current_scene.user_goal,
                    "scene_order": current_scene.scene_order,
                    "estimated_duration": current_scene.estimated_duration,
                    "image_url": current_scene.image_url,
                    "timeout_turns": current_scene.timeout_turns if current_scene.timeout_turns is not None else 15,
                    "personas": [
                        {
                            "id": p.id,
                            "name": p.name,
                            "role": p.role,
                            "background": p.background,
                            "correlation": p.correlation,
                            "primary_goals": p.primary_goals,
                            "personality_traits": p.personality_traits,
                            "image_url": p.image_url if p.image_url else None
                        }
                        for p in filtered_personas
                    ]
                }
        
        # Get all scenes with personas for lookup (reuse all_scenes_list from above)
        all_scenes_data = []
        for scene in all_scenes_list:
            scene_personas_list = db.query(ScenarioPersona).join(
                scene_personas, ScenarioPersona.id == scene_personas.c.persona_id
            ).filter(
                scene_personas.c.scene_id == scene.id,
                ScenarioPersona.deleted_at.is_(None)
            ).all()
            
            def is_main_character_all(persona_name, student_role):
                if not student_role:
                    return False
                student_name = student_role.split('(')[0].strip().lower()
                persona_name_clean = persona_name.strip().lower()
                return persona_name_clean == student_name
            
            filtered_personas_all = [
                p for p in scene_personas_list
                if not is_main_character_all(p.name, simulation.student_role)
            ]
            
            all_scenes_data.append({
                "id": scene.id,
                "title": scene.title,
                "description": scene.description,
                "user_goal": scene.user_goal,
                "image_url": scene.image_url,
                "scene_order": scene.scene_order,
                "personas": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "role": p.role,
                        "background": p.background,
                        "correlation": p.correlation,
                        "primary_goals": p.primary_goals,
                        "personality_traits": p.personality_traits,
                        "image_url": p.image_url if p.image_url else None
                    }
                    for p in filtered_personas_all
                ]
            })
    
    return SubmissionDetailsResponse(
        instance_id=instance.id,
        student_name=student.full_name or student.email,
        student_email=student.email,
        simulation_title=simulation.title,
        status=instance.status,
        completion_percentage=instance.completion_percentage or 0.0,
        total_time_spent=instance.total_time_spent or 0,
        started_at=instance.started_at,
        completed_at=instance.completed_at,
        submitted_at=instance.submitted_at,
        ai_grade=instance.ai_grade,
        ai_feedback=ai_feedback_parsed,
        ai_graded_at=instance.ai_graded_at,
        professor_grade=instance.grade if instance.graded_by else None,
        professor_feedback=instance.feedback if instance.graded_by else None,
        graded_by_name=grader_name,
        graded_at=instance.graded_at,
        final_grade=final_grade,
        final_feedback=final_feedback,
        grade_status=instance.grade_status or "not_graded",
        student_responses=student_responses,
        scene_details=scene_details,
        conversation_history=conversation_history,
        scenario=scenario_data,
        current_scene=current_scene_data,
        all_scenes=all_scenes_data
    )


@router.post("/instances/{instance_id}/review", response_model=Dict[str, Any])
async def submit_professor_review(
    instance_id: int,
    review: ProfessorGradeReview,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """
    Submit professor review/override of AI grading
    Updates the final grade and creates a grade history entry
    """
    # Validate grade range
    if review.grade < 0 or review.grade > 100:
        raise HTTPException(
            status_code=400, 
            detail="Grade must be between 0 and 100"
        )
    
    # Get the instance
    instance = db.query(StudentSimulationInstance).filter(
        StudentSimulationInstance.id == instance_id
    ).first()
    
    if not instance:
        raise HTTPException(status_code=404, detail="Simulation instance not found")
    
    # Verify professor has access
    cohort_assignment = db.query(CohortSimulation).filter(
        CohortSimulation.id == instance.cohort_assignment_id
    ).first()
    
    if not cohort_assignment:
        raise HTTPException(status_code=404, detail="Cohort assignment not found")
    
    cohort = db.query(Cohort).filter(
        Cohort.id == cohort_assignment.cohort_id,
        Cohort.created_by == current_user.id
    ).first()
    
    if not cohort:
        raise HTTPException(status_code=403, detail="Not authorized to grade this submission")
    
    # Save previous status for history
    previous_status = instance.grade_status or "not_graded"
    previous_grade = instance.grade
    previous_feedback = instance.feedback
    
    # Update instance with professor grade
    instance.grade = review.grade
    instance.feedback = review.feedback
    instance.graded_by = current_user.id
    instance.graded_at = datetime.now(timezone.utc)
    instance.grade_status = "professor_reviewed"
    
    # Update status to 'graded' if not already
    if instance.status != "graded":
        instance.status = "graded"
    
    # Create grade history entry
    grade_history = GradeHistory(
        instance_id=instance.id,
        grade_type="professor",
        grade_value=review.grade,
        feedback=review.feedback,
        graded_by=current_user.id,
        previous_status=previous_status,
        new_status="professor_reviewed"
    )
    db.add(grade_history)
    
    db.commit()
    db.refresh(instance)
    
    logger.info(f"Professor {current_user.id} reviewed instance {instance_id}: grade={review.grade}")
    
    return {
        "message": "Review submitted successfully",
        "instance_id": instance.id,
        "grade": instance.grade,
        "grade_status": instance.grade_status,
        "graded_at": instance.graded_at.isoformat() if instance.graded_at else None
    }


@router.get("/instances/{instance_id}/history", response_model=List[Dict[str, Any]])
async def get_grade_history(
    instance_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """
    Get grade history for a submission (audit trail)
    """
    # Get the instance
    instance = db.query(StudentSimulationInstance).filter(
        StudentSimulationInstance.id == instance_id
    ).first()
    
    if not instance:
        raise HTTPException(status_code=404, detail="Simulation instance not found")
    
    # Verify professor has access
    cohort_assignment = db.query(CohortSimulation).filter(
        CohortSimulation.id == instance.cohort_assignment_id
    ).first()
    
    if not cohort_assignment:
        raise HTTPException(status_code=404, detail="Cohort assignment not found")
    
    cohort = db.query(Cohort).filter(
        Cohort.id == cohort_assignment.cohort_id,
        Cohort.created_by == current_user.id
    ).first()
    
    if not cohort:
        raise HTTPException(status_code=403, detail="Not authorized to access this submission")
    
    # Get grade history
    history_records = db.query(GradeHistory).filter(
        GradeHistory.instance_id == instance_id
    ).order_by(GradeHistory.created_at.desc()).all()
    
    # Format response
    history = []
    for record in history_records:
        grader_name = None
        if record.graded_by:
            grader = db.query(User).filter(User.id == record.graded_by).first()
            if grader:
                grader_name = grader.full_name or grader.email
        
        history.append({
            "id": record.id,
            "grade_type": record.grade_type,
            "grade_value": record.grade_value,
            "feedback": record.feedback,
            "graded_by": grader_name,
            "previous_status": record.previous_status,
            "new_status": record.new_status,
            "created_at": record.created_at.isoformat() if record.created_at else None
        })
    
    return history


@router.delete("/instances/{instance_id}/review/revert")
async def revert_to_ai_grade(
    instance_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """
    Revert professor review and use AI grade as final grade
    """
    # Get the instance
    instance = db.query(StudentSimulationInstance).filter(
        StudentSimulationInstance.id == instance_id
    ).first()
    
    if not instance:
        raise HTTPException(status_code=404, detail="Simulation instance not found")
    
    # Verify professor has access
    cohort_assignment = db.query(CohortSimulation).filter(
        CohortSimulation.id == instance.cohort_assignment_id
    ).first()
    
    if not cohort_assignment:
        raise HTTPException(status_code=404, detail="Cohort assignment not found")
    
    cohort = db.query(Cohort).filter(
        Cohort.id == cohort_assignment.cohort_id,
        Cohort.created_by == current_user.id
    ).first()
    
    if not cohort:
        raise HTTPException(status_code=403, detail="Not authorized to modify this submission")
    
    # Check if AI grade exists
    if instance.ai_grade is None:
        raise HTTPException(
            status_code=400, 
            detail="Cannot revert: No AI grade exists for this submission"
        )
    
    # Save previous status
    previous_status = instance.grade_status or "not_graded"
    
    # Revert to AI grade
    instance.grade = instance.ai_grade
    instance.feedback = instance.ai_feedback
    instance.graded_by = None  # Clear professor grading
    instance.graded_at = instance.ai_graded_at
    instance.grade_status = "ai_graded"
    
    # Create grade history entry
    grade_history = GradeHistory(
        instance_id=instance.id,
        grade_type="ai",
        grade_value=instance.ai_grade,
        feedback=instance.ai_feedback,
        graded_by=current_user.id,
        previous_status=previous_status,
        new_status="ai_graded"
    )
    db.add(grade_history)
    
    db.commit()
    db.refresh(instance)
    
    logger.info(f"Professor {current_user.id} reverted instance {instance_id} to AI grade")
    
    return {
        "message": "Reverted to AI grade successfully",
        "instance_id": instance.id,
        "grade": instance.grade,
        "grade_status": instance.grade_status
    }

