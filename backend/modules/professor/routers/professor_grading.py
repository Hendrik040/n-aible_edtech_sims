"""
Professor grading router - Endpoints for professor grading operations
"""
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload, joinedload
from datetime import datetime, timezone

from common.db.core import get_db
from common.db.models import User, StudentSimulationInstance, GradeHistory, UserProgress, ConversationLog
from app.dependencies import require_professor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/professor/grading", tags=["Professor Grading"])


@router.get("/instances/{instance_id}/submission", response_model=Dict[str, Any])
async def get_submission_details(
    instance_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get submission details for a student simulation instance."""
    try:
        # Get the instance with relationships
        instance = db.query(StudentSimulationInstance).options(
            selectinload(StudentSimulationInstance.student),
            selectinload(StudentSimulationInstance.cohort_assignment).joinedload("cohort")
        ).filter(
            StudentSimulationInstance.id == instance_id
        ).first()
        
        if not instance:
            raise HTTPException(status_code=404, detail="Simulation instance not found")
        
        # Verify the professor has access to this instance (through cohort assignment)
        # Enforce authorization unconditionally - missing cohort linkage results in denied access
        if not instance.cohort_assignment:
            raise HTTPException(status_code=403, detail="Access denied")
        
        cohort = instance.cohort_assignment.cohort
        if cohort is None or cohort.created_by != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get user progress and conversation logs
        conversation_history = []
        current_scene_data = None
        all_scenes_data = []
        simulation_data = None
        
        if instance.user_progress_id:
            user_progress = db.query(UserProgress).filter(
                UserProgress.id == instance.user_progress_id
            ).first()
            
            if user_progress:
                # Get simulation
                from modules.simulation.repository import SimulationRepository
                from common.db.models import Simulation, SimulationScene, SimulationPersona
                repo = SimulationRepository(db)
                
                simulation = repo.get_simulation_by_id(user_progress.simulation_id)
                if simulation:
                    # Build simulation data
                    learning_objectives = simulation.learning_objectives
                    if isinstance(learning_objectives, str):
                        learning_objectives = [learning_objectives]
                    elif learning_objectives is None:
                        learning_objectives = []
                    
                    simulation_data = {
                        "id": simulation.id,
                        "title": simulation.title,
                        "description": simulation.description,
                        "challenge": simulation.challenge,
                        "industry": getattr(simulation, 'industry', None),
                        "learning_objectives": learning_objectives,
                        "student_role": simulation.student_role,
                        "total_scenes": 0,
                        "case_study_url": getattr(simulation, 'case_study_url', None)
                    }
                    
                    # Get all scenes with personas
                    all_scenes = repo.get_scenes_by_simulation_id(user_progress.simulation_id)
                    simulation_data["total_scenes"] = len(all_scenes)
                    
                    # Bulk load all personas for all scenes to avoid N+1 queries
                    scene_ids = [scene.id for scene in all_scenes]
                    personas_by_scene = repo.get_personas_for_scenes(scene_ids) if scene_ids else {}
                    
                    for scene in all_scenes:
                        # Get personas for this scene from bulk-loaded dict
                        scene_personas = personas_by_scene.get(scene.id, [])
                        personas_data = [
                            {
                                "id": p.id,
                                "simulation_id": p.simulation_id,
                                "name": p.name,
                                "role": p.role,
                                "background": getattr(p, 'background', None),
                                "correlation": getattr(p, 'correlation', None),
                                "primary_goals": (
                                    [p.primary_goals] if isinstance(getattr(p, 'primary_goals', None), str) and getattr(p, 'primary_goals', None) else
                                    getattr(p, 'primary_goals', []) if isinstance(getattr(p, 'primary_goals', None), list) else []
                                ),
                                "personality_traits": getattr(p, 'personality_traits', None) or {},
                                "image_url": getattr(p, 'image_url', None)
                            }
                            for p in scene_personas
                        ]
                        
                        scene_data = {
                            "id": scene.id,
                            "simulation_id": scene.simulation_id,
                            "title": scene.title,
                            "description": scene.description,
                            "user_goal": scene.user_goal,
                            "scene_order": scene.scene_order,
                            "estimated_duration": getattr(scene, 'estimated_duration', None),
                            "image_url": scene.image_url,
                            "image_prompt": getattr(scene, 'image_prompt', None),
                            "timeout_turns": scene.timeout_turns,
                            "success_metric": scene.success_metric,
                            "personas": personas_data
                        }
                        
                        all_scenes_data.append(scene_data)
                        
                        # Set current scene if it matches user_progress.current_scene_id
                        if user_progress.current_scene_id and scene.id == user_progress.current_scene_id:
                            current_scene_data = scene_data
                    
                    # If no current scene set, use first scene
                    if not current_scene_data and all_scenes_data:
                        current_scene_data = all_scenes_data[0]
                
                # Get conversation logs
                conversation_logs = db.query(ConversationLog).filter(
                    ConversationLog.user_progress_id == user_progress.id
                ).order_by(ConversationLog.message_order).all()
                
                conversation_history = [
                    {
                        "id": log.id,
                        "message_content": log.message_content,
                        "sender_name": log.sender_name,
                        "message_type": log.message_type,
                        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                        "scene_id": log.scene_id,
                        "persona_id": log.persona_id,
                        "message_order": log.message_order
                    }
                    for log in conversation_logs
                ]
        
        # Build response
        return {
            "instance_id": instance.id,
            "unique_id": instance.unique_id,
            "student_id": instance.student_id,
            "student_name": instance.student.full_name if instance.student else "Unknown",
            "student_email": instance.student.email if instance.student else "unknown@example.com",
            "status": instance.status,
            "completion_percentage": instance.completion_percentage,
            "total_time_spent": instance.total_time_spent,
            "started_at": instance.started_at.isoformat() if instance.started_at else None,
            "completed_at": instance.completed_at.isoformat() if instance.completed_at else None,
            "submitted_at": instance.submitted_at.isoformat() if instance.submitted_at else None,
            "ai_grade": instance.ai_grade,
            "ai_feedback": instance.ai_feedback,
            "ai_graded_at": instance.ai_graded_at.isoformat() if instance.ai_graded_at else None,
            "professor_grade": instance.grade,
            "professor_feedback": instance.feedback,
            "graded_by": instance.graded_by,
            "graded_at": instance.graded_at.isoformat() if instance.graded_at else None,
            "grade_status": instance.grade_status,
            "conversation_history": conversation_history,
            "user_progress_id": instance.user_progress_id,
            "current_scene": current_scene_data,
            "all_scenes": all_scenes_data,
            "simulation": simulation_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_submission_details: {e!r}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get submission details: {e!s}") from e


@router.get("/instances/{instance_id}/history", response_model=List[Dict[str, Any]])
async def get_grade_history(
    instance_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get grade history for a student simulation instance."""
    try:
        # Verify instance exists and professor has access
        instance = db.query(StudentSimulationInstance).options(
            selectinload(StudentSimulationInstance.cohort_assignment).joinedload("cohort")
        ).filter(
            StudentSimulationInstance.id == instance_id
        ).first()
        
        if not instance:
            raise HTTPException(status_code=404, detail="Simulation instance not found")
        
        # Verify the professor has access to this instance
        # Enforce authorization unconditionally - missing cohort linkage results in denied access
        cohort = instance.cohort_assignment.cohort if instance.cohort_assignment else None
        if cohort is None or cohort.created_by != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get grade history
        history_records = db.query(GradeHistory).filter(
            GradeHistory.instance_id == instance_id
        ).order_by(GradeHistory.created_at.desc()).all()
        
        # Bulk load all graders to avoid N+1 queries
        graded_by_ids = {record.graded_by for record in history_records if record.graded_by}
        graders_map = {}
        if graded_by_ids:
            graders = db.query(User).filter(User.id.in_(graded_by_ids)).all()
            graders_map = {grader.id: grader for grader in graders}
        
        # Format history records
        history = []
        for record in history_records:
            grader = None
            if record.graded_by:
                grader_user = graders_map.get(record.graded_by)
                if grader_user:
                    grader = {
                        "id": grader_user.id,
                        "name": grader_user.full_name or grader_user.email.split('@')[0],
                        "email": grader_user.email
                    }
            
            history.append({
                "id": record.id,
                "grade_type": record.grade_type,
                "grade_value": record.grade_value,
                "feedback": record.feedback,
                "graded_by": grader,
                "previous_status": record.previous_status,
                "new_status": record.new_status,
                "created_at": record.created_at.isoformat() if record.created_at else None
            })
        
        return history
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_grade_history: {e!r}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get grade history: {e!s}") from e


@router.post("/instances/{instance_id}/review", response_model=Dict[str, Any])
async def submit_professor_review(
    instance_id: int,
    review_data: Dict[str, Any],
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Submit professor review/grade for a student simulation instance."""
    try:
        # Get the instance
        instance = db.query(StudentSimulationInstance).options(
            selectinload(StudentSimulationInstance.cohort_assignment).joinedload("cohort")
        ).filter(
            StudentSimulationInstance.id == instance_id
        ).first()
        
        if not instance:
            raise HTTPException(status_code=404, detail="Simulation instance not found")
        
        # Verify the professor has access
        # Enforce authorization unconditionally - missing cohort linkage results in denied access
        if (not instance.cohort_assignment or 
            not instance.cohort_assignment.cohort or 
            instance.cohort_assignment.cohort.created_by != current_user.id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Extract review data
        grade = review_data.get("grade")
        feedback = review_data.get("feedback", "")
        
        if grade is None:
            raise HTTPException(status_code=400, detail="Grade is required")
        
        try:
            grade = float(grade)
            if grade < 0 or grade > 100:
                raise HTTPException(status_code=400, detail="Grade must be between 0 and 100")
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid grade value")
        
        # Store previous values for history
        previous_grade = instance.grade
        previous_feedback = instance.feedback
        previous_status = instance.grade_status
        
        # Update instance
        instance.grade = grade
        instance.feedback = feedback
        instance.graded_by = current_user.id
        instance.graded_at = datetime.now(timezone.utc)
        instance.grade_status = "professor_graded"
        
        # Update status if needed
        if instance.status in ["completed", "submitted"]:
            instance.status = "graded"
        
        # Create grade history record
        history_record = GradeHistory(
            instance_id=instance.id,
            grade_type="professor",
            grade_value=grade,
            feedback=feedback,
            graded_by=current_user.id,
            previous_status=previous_status,
            new_status="professor_graded"
        )
        db.add(history_record)
        
        db.commit()
        db.refresh(instance)
        
        return {
            "instance_id": instance.id,
            "grade": instance.grade,
            "feedback": instance.feedback,
            "graded_by": instance.graded_by,
            "graded_at": instance.graded_at.isoformat() if instance.graded_at else None,
            "grade_status": instance.grade_status,
            "status": instance.status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in submit_professor_review: {e!r}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to submit review: {e!s}") from e


@router.post("/instances/{instance_id}/review/revert", response_model=Dict[str, Any])
async def revert_to_ai_grade(
    instance_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Revert to AI grade (remove professor override)."""
    try:
        # Get the instance
        instance = db.query(StudentSimulationInstance).options(
            selectinload(StudentSimulationInstance.cohort_assignment).joinedload("cohort")
        ).filter(
            StudentSimulationInstance.id == instance_id
        ).first()
        
        if not instance:
            raise HTTPException(status_code=404, detail="Simulation instance not found")
        
        # Verify the professor has access
        # Enforce authorization unconditionally - missing cohort linkage results in denied access
        if (not instance.cohort_assignment or 
            not instance.cohort_assignment.cohort or 
            instance.cohort_assignment.cohort.created_by != current_user.id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        if instance.ai_grade is None:
            raise HTTPException(status_code=400, detail="No AI grade available to revert to")
        
        # Store previous status for history
        previous_status = instance.grade_status
        
        # Revert to AI grade
        instance.grade = None
        instance.feedback = None
        instance.graded_by = None
        instance.graded_at = None
        instance.grade_status = "ai_graded" if instance.ai_grade is not None else "not_graded"
        
        # Create grade history record
        history_record = GradeHistory(
            instance_id=instance.id,
            grade_type="ai",
            grade_value=instance.ai_grade,
            feedback=instance.ai_feedback,
            graded_by=None,
            previous_status=previous_status,
            new_status="ai_graded"
        )
        db.add(history_record)
        
        db.commit()
        db.refresh(instance)
        
        return {
            "instance_id": instance.id,
            "grade": instance.grade,
            "ai_grade": instance.ai_grade,
            "ai_feedback": instance.ai_feedback,
            "grade_status": instance.grade_status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in revert_to_ai_grade: {e!r}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to revert to AI grade: {e!s}") from e
