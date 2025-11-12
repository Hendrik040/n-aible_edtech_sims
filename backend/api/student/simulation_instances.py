# """
# Student simulation instance management API endpoints
# """
# from fastapi import APIRouter, HTTPException, Depends, status, Query
# from sqlalchemy.orm import Session
# from typing import List, Optional, Dict, Any
# import logging
# from datetime import datetime, timezone

# from database.connection import get_db
# from database.models import (
#     User, StudentSimulationInstance, CohortSimulation, Cohort, Scenario, UserProgress,
#     ScenarioScene, ScenarioPersona, SceneProgress, ConversationLog, scene_personas
# )
# from database.schemas import StudentSimulationInstanceResponse, StudentSimulationInstanceCreate, StudentSimulationInstanceUpdate
# from utilities.auth import require_student
# from utilities.debug_logging import debug_log
# from middleware.role_auth import require_professor
# import os

# router = APIRouter(prefix="/student-simulation-instances", tags=["Student Simulation Instances"])
# logger = logging.getLogger(__name__)
# is_production = os.getenv("ENVIRONMENT", "development") == "production"


# def _get_published_instance_query(
#     db: Session, 
#     student_id: int, 
#     instance_id: Optional[int] = None
# ):
#     """
#     Helper function to build the base query for published simulation instances.
    
#     Joins StudentSimulationInstance -> UserProgress -> Scenario and filters by:
#     - student_id
#     - Scenario.is_draft == False (only published simulations)
#     - instance_id (optional)
    
#     Returns:
#         SQLAlchemy Query object that can be further filtered before calling first() or all()
#     """
#     query = db.query(StudentSimulationInstance).join(
#         UserProgress, StudentSimulationInstance.user_progress_id == UserProgress.id
#     ).join(
#         Scenario, UserProgress.scenario_id == Scenario.id
#     ).filter(
#         StudentSimulationInstance.student_id == student_id,
#         Scenario.is_draft == False,  # Only published simulations
#         Scenario.status == "active"   # Ensure status is active (not draft or archived)
#     )
    
#     if instance_id is not None:
#         query = query.filter(StudentSimulationInstance.id == instance_id)
    
#     return query

# @router.get("/", response_model=List[Dict[str, Any]])
# async def get_student_simulation_instances(
#     current_user: User = Depends(require_student),
#     db: Session = Depends(get_db),
#     status_filter: Optional[str] = Query(None),
#     cohort_id: Optional[int] = Query(None)
# ):
#     """Get simulation instances for the current student (only for published simulations)"""
#     try:
#         if not is_production:
#             logger.info(f"GET student simulations: student_id={current_user.id}, cohort_id={cohort_id}, status_filter={status_filter}")
        
#         from database.models import CohortStudent
        
#         # Get all cohorts the student is enrolled in
#         student_cohorts = db.query(CohortStudent).filter(
#             CohortStudent.student_id == current_user.id,
#             CohortStudent.status == "approved"
#         ).all()
        
#         cohort_ids = [sc.cohort_id for sc in student_cohorts]
#         if not is_production:
#             logger.info(f"Student {current_user.id} is enrolled in cohorts: {cohort_ids}")
        
#         if not cohort_ids:
#             logger.warning(f"Student {current_user.id} is not enrolled in any cohorts")
#             return []
        
#         # Get all published simulations assigned to these cohorts
#         from sqlalchemy.orm import joinedload
        
#         cohort_simulations_query = db.query(CohortSimulation).join(
#             Scenario, CohortSimulation.simulation_id == Scenario.id
#         ).join(
#             Cohort, CohortSimulation.cohort_id == Cohort.id
#         ).options(
#             joinedload(CohortSimulation.simulation),
#             joinedload(CohortSimulation.cohort).joinedload(Cohort.creator)
#         ).filter(
#             CohortSimulation.cohort_id.in_(cohort_ids),
#             Scenario.is_draft == False,  # Only published simulations
#             Scenario.status == "active"   # Ensure status is active (not draft or archived)
#         )
        
#         if cohort_id:
#             cohort_simulations_query = cohort_simulations_query.filter(CohortSimulation.cohort_id == cohort_id)
        
#         cohort_simulations = cohort_simulations_query.all()
#         if not is_production:
#             logger.info(f"Found {len(cohort_simulations)} published simulations assigned to student's cohorts")
        
#         # OPTIMIZATION: Batch load all instances upfront to avoid N+1 queries
#         cohort_assignment_ids = [cs.id for cs in cohort_simulations]
#         all_instances = db.query(StudentSimulationInstance).filter(
#             StudentSimulationInstance.cohort_assignment_id.in_(cohort_assignment_ids),
#             StudentSimulationInstance.student_id == current_user.id
#         ).all()
        
#         # Create a map for quick lookup: cohort_assignment_id -> instance
#         instance_map = {inst.cohort_assignment_id: inst for inst in all_instances}
        
#         # OPTIMIZATION: Batch load all user_progress records
#         user_progress_ids = [inst.user_progress_id for inst in all_instances if inst.user_progress_id]
#         user_progress_map = {}
#         if user_progress_ids:
#             user_progresses = db.query(UserProgress).filter(
#                 UserProgress.id.in_(user_progress_ids)
#             ).all()
#             user_progress_map = {up.id: up for up in user_progresses}
        
#         # OPTIMIZATION: Batch load all scenarios
#         scenario_ids = [up.scenario_id for up in user_progress_map.values() if up.scenario_id]
#         scenario_map = {}
#         if scenario_ids:
#             scenarios = db.query(Scenario).filter(Scenario.id.in_(scenario_ids)).all()
#             scenario_map = {s.id: s for s in scenarios}
        
#         # OPTIMIZATION: Batch load scene counts for all scenarios
#         scene_count_map = {}
#         if scenario_ids:
#             from sqlalchemy import func
#             scene_counts = db.query(
#                 ScenarioScene.scenario_id,
#                 func.count(ScenarioScene.id).label('count')
#             ).filter(
#                 ScenarioScene.scenario_id.in_(scenario_ids)
#             ).group_by(ScenarioScene.scenario_id).all()
#             scene_count_map = {scenario_id: count for scenario_id, count in scene_counts}
        
#         # OPTIMIZATION: Batch load completed scene progress counts
#         completed_scene_count_map = {}
#         if user_progress_ids:
#             completed_counts = db.query(
#                 SceneProgress.user_progress_id,
#                 func.count(SceneProgress.id).label('count')
#             ).filter(
#                 SceneProgress.user_progress_id.in_(user_progress_ids),
#                 SceneProgress.status == "completed"
#             ).group_by(SceneProgress.user_progress_id).all()
#             completed_scene_count_map = {up_id: count for up_id, count in completed_counts}
        
#         # Format response - create instance if it doesn't exist
#         result = []
#         for cohort_simulation in cohort_simulations:
#             try:
#                 # Check if student has an instance for this assignment (from preloaded map)
#                 instance = instance_map.get(cohort_simulation.id)
                
#                 # If no instance exists, create one automatically
#                 if not instance:
#                     try:
#                         # Import the unique ID generator
#                         from utilities.id_generator import generate_unique_simulation_instance_id
                        
#                         # Create UserProgress record first
#                         user_progress = UserProgress(
#                             user_id=current_user.id,
#                             scenario_id=cohort_simulation.simulation_id,
#                             simulation_status="not_started"
#                         )
#                         db.add(user_progress)
#                         db.flush()
                        
#                         # Create the instance with unique ID
#                         instance = StudentSimulationInstance(
#                             unique_id=generate_unique_simulation_instance_id(db),
#                             cohort_assignment_id=cohort_simulation.id,
#                             student_id=current_user.id,
#                             user_progress_id=user_progress.id
#                         )
#                         db.add(instance)
#                         db.commit()
#                         db.refresh(instance)
#                         if not is_production:
#                             logger.info(f"Auto-created simulation instance {instance.unique_id} for student {current_user.id}, cohort_simulation {cohort_simulation.id}")
#                     except Exception as e:
#                         logger.error(f"Failed to auto-create instance: {str(e)}")
#                         db.rollback()
#                         continue
                
#                 # Apply status filter if provided
#                 if status_filter and instance.status != status_filter:
#                     continue
                
#                 # Calculate real-time progress if user_progress exists
#                 completion_percentage = instance.completion_percentage or 0.0
#                 total_time_spent = instance.total_time_spent or 0
                
#                 try:
#                     if instance.user_progress_id:
#                         # Use preloaded user_progress from map (no query needed)
#                         user_progress = user_progress_map.get(instance.user_progress_id)
                        
#                         if user_progress:
#                             # If simulation is completed or graded, force 100% completion
#                             if (user_progress.simulation_status in ["completed", "graded"] or 
#                                 instance.status in ["completed", "graded", "submitted"]):
#                                 completion_percentage = 100.0
#                                 if instance.completion_percentage != 100.0:
#                                     instance.completion_percentage = 100.0
#                                     db.commit()
#                             else:
#                                 # Calculate completion percentage from preloaded data (no queries needed)
#                                 scenario = scenario_map.get(user_progress.scenario_id) if user_progress.scenario_id else None
                                
#                                 if scenario:
#                                     # Use preloaded scene count (no query needed)
#                                     total_scenes = scene_count_map.get(scenario.id, 0)
                                    
#                                     # Use preloaded completed scene count (no query needed)
#                                     completed_scenes = completed_scene_count_map.get(user_progress.id, 0)
                                    
#                                     if total_scenes > 0:
#                                         completion_percentage = (completed_scenes / total_scenes) * 100
#                                         # Update instance if changed
#                                         if abs(completion_percentage - (instance.completion_percentage or 0)) > 0.01:
#                                             instance.completion_percentage = completion_percentage
#                                             db.commit()
                            
#                             # Calculate time spent preferring started_at -> completed_at
#                             try:
#                                 from datetime import datetime, timezone
#                                 start_dt = instance.started_at or user_progress.created_at
#                                 end_dt = instance.completed_at or user_progress.last_activity or user_progress.updated_at or datetime.now(timezone.utc)
#                                 if start_dt:
#                                     if start_dt.tzinfo is None:
#                                         start_dt = start_dt.replace(tzinfo=timezone.utc)
#                                     if end_dt and end_dt.tzinfo is None:
#                                         end_dt = end_dt.replace(tzinfo=timezone.utc)
#                                     if end_dt:
#                                         time_delta = end_dt - start_dt
#                                         total_time_spent = max(0, int(time_delta.total_seconds()))
#                                         if abs(total_time_spent - (instance.total_time_spent or 0)) > 1:
#                                             instance.total_time_spent = total_time_spent
#                                             db.commit()
#                             except Exception as e:
#                                 logger.warning(f"Could not calculate time spent for instance {instance.id}: {e}")
#                 except Exception as e:
#                     # Don't let one instance error break the whole request
#                     logger.error(f"Error calculating progress for instance {instance.id}: {e}")
#                     # Use existing values if calculation fails
#                     completion_percentage = instance.completion_percentage or 0.0
#                     total_time_spent = instance.total_time_spent or 0
                
#                 # Get simulation and cohort with safe access
#                 simulation = cohort_simulation.simulation
#                 cohort = cohort_simulation.cohort
                
#                 # Build professor info safely (cohort.creator is the professor who created the cohort)
#                 professor_name = "Unknown"
#                 if cohort and hasattr(cohort, 'creator') and cohort.creator:
#                     professor_name = cohort.creator.name if hasattr(cohort.creator, 'name') else "Unknown"
                
#                 result.append({
#                     "id": instance.id,
#                     "unique_id": instance.unique_id,
#                     "cohort_assignment_id": instance.cohort_assignment_id,
#                     "student_id": instance.student_id,
#                     "user_progress_id": instance.user_progress_id,
#                     "status": instance.status,
#                     "started_at": instance.started_at,
#                     "completed_at": instance.completed_at,
#                     "submitted_at": instance.submitted_at,
#                     "grade": instance.grade,
#                     "feedback": instance.feedback,
#                     "graded_by": instance.graded_by,
#                     "graded_at": instance.graded_at,
#                     "completion_percentage": completion_percentage,
#                     "total_time_spent": total_time_spent,
#                     "attempts_count": instance.attempts_count,
#                     "hints_used": instance.hints_used,
#                     "is_overdue": instance.is_overdue,
#                     "days_late": instance.days_late,
#                     "created_at": instance.created_at,
#                     "updated_at": instance.updated_at,
#                     # Nested relationship data
#                     "cohort_assignment": {
#                         "id": cohort_simulation.id,
#                         "simulation_id": cohort_simulation.simulation_id,
#                         "cohort_id": cohort_simulation.cohort_id,
#                         "due_date": cohort_simulation.due_date,
#                         "is_required": cohort_simulation.is_required,
#                         "simulation": {
#                             "id": simulation.id if simulation else None,
#                             "title": simulation.title if simulation else "Unknown Simulation",
#                             "description": simulation.description if simulation else "No description available",
#                             "is_draft": simulation.is_draft if simulation else True,
#                             "status": simulation.status if simulation else "draft",
#                         } if simulation else None,
#                         "cohort": {
#                             "id": cohort.id if cohort else None,
#                             "title": cohort.title if cohort else "Unknown Cohort",
#                             "professor": {
#                                 "name": professor_name
#                             }
#                         } if cohort else None
#                     }
#                 })
#             except Exception as e:
#                 logger.error(f"Error processing cohort simulation {cohort_simulation.id}: {str(e)}")
#                 continue
        
#         if not is_production:
#             logger.info(f"Returning {len(result)} simulation instances for student {current_user.id}")
#         return result
        
#     except Exception as e:
#         logger.error(f"Error in get_student_simulation_instances: {str(e)}", exc_info=True)
#         raise HTTPException(status_code=500, detail=f"Failed to fetch simulation instances: {str(e)}")

# @router.post("", response_model=StudentSimulationInstanceResponse)
# @router.post("/", response_model=StudentSimulationInstanceResponse)
# async def create_student_simulation_instance(
#     instance_data: StudentSimulationInstanceCreate,
#     current_user: User = Depends(require_student),
#     db: Session = Depends(get_db)
# ):
#     """Create a new student simulation instance"""
    
#     # Verify the student is enrolled in the cohort
#     cohort_assignment = db.query(CohortSimulation).filter(
#         CohortSimulation.id == instance_data.cohort_assignment_id
#     ).first()
    
#     if not cohort_assignment:
#         raise HTTPException(status_code=404, detail="Cohort assignment not found")
    
#     # Check if student is enrolled in the cohort
#     from database.models import CohortStudent
#     enrollment = db.query(CohortStudent).filter(
#         CohortStudent.cohort_id == cohort_assignment.cohort_id,
#         CohortStudent.student_id == current_user.id,
#         CohortStudent.status == "approved"
#     ).first()
    
#     if not enrollment:
#         raise HTTPException(status_code=403, detail="Student not enrolled in this cohort")
    
#     # Check if instance already exists
#     existing_instance = db.query(StudentSimulationInstance).filter(
#         StudentSimulationInstance.cohort_assignment_id == instance_data.cohort_assignment_id,
#         StudentSimulationInstance.student_id == current_user.id
#     ).first()
    
#     if existing_instance:
#         raise HTTPException(status_code=400, detail="Simulation instance already exists")
    
#     # Get the cohort assignment to get the simulation_id
#     cohort_assignment = db.query(CohortSimulation).filter(
#         CohortSimulation.id == instance_data.cohort_assignment_id
#     ).first()
    
#     # Create UserProgress record first
#     user_progress = UserProgress(
#         user_id=current_user.id,
#         scenario_id=cohort_assignment.simulation_id,
#         simulation_status="not_started"
#     )
#     db.add(user_progress)
#     db.flush()  # Flush to get the ID
    
#     # Import the unique ID generator
#     from utilities.id_generator import generate_unique_simulation_instance_id
    
#     # Create the instance with user_progress_id
#     instance = StudentSimulationInstance(
#         unique_id=generate_unique_simulation_instance_id(db),
#         cohort_assignment_id=instance_data.cohort_assignment_id,
#         student_id=current_user.id,
#         user_progress_id=user_progress.id
#     )
    
#     db.add(instance)
#     db.commit()
#     db.refresh(instance)
    
#     if not is_production:
#         logger.info(f"Created simulation instance {instance.id} for student {current_user.id}")
#     return instance

# @router.get("/{instance_id}", response_model=StudentSimulationInstanceResponse)
# async def get_student_simulation_instance(
#     instance_id: str,  # Accept both int and unique_id string
#     current_user: User = Depends(require_student),
#     db: Session = Depends(get_db)
# ):
#     """Get a specific simulation instance (only if simulation is published)"""
    
#     # Try to parse as integer first, otherwise treat as unique_id
#     instance = None
#     try:
#         int_id = int(instance_id)
#         instance = _get_published_instance_query(db, current_user.id, int_id).first()
#     except ValueError:
#         # It's a unique_id string
#         instance = db.query(StudentSimulationInstance).join(
#             UserProgress, StudentSimulationInstance.user_progress_id == UserProgress.id
#         ).join(
#             Scenario, UserProgress.scenario_id == Scenario.id
#         ).filter(
#             StudentSimulationInstance.unique_id == instance_id,
#             StudentSimulationInstance.student_id == current_user.id,
#             Scenario.is_draft == False,
#             Scenario.status == "active"
#         ).first()
    
#     if not instance:
#         raise HTTPException(
#             status_code=404, 
#             detail="Simulation instance not found or simulation is not published"
#         )
    
#     return instance

# @router.put("/{instance_id}", response_model=StudentSimulationInstanceResponse)
# async def update_student_simulation_instance(
#     instance_id: str,  # Changed to str to accept both integer IDs and unique_ids
#     update_data: StudentSimulationInstanceUpdate,
#     current_user: User = Depends(require_student),
#     db: Session = Depends(get_db)
# ):
#     """Update a simulation instance (accepts both integer ID and unique_id)"""
    
#     # Try to get instance by integer ID or unique_id
#     instance = None
#     try:
#         int_id = int(instance_id)
#         instance = _get_published_instance_query(db, current_user.id, int_id).first()
#     except ValueError:
#         # It's a unique_id string - query by unique_id
#         instance = db.query(StudentSimulationInstance).filter(
#             StudentSimulationInstance.unique_id == instance_id,
#             StudentSimulationInstance.student_id == current_user.id
#         ).first()
    
#     if not instance:
#         raise HTTPException(
#             status_code=404, 
#             detail="Simulation instance not found or simulation is not published"
#         )
    
#     # Update fields
#     for field, value in update_data.dict(exclude_unset=True).items():
#         setattr(instance, field, value)
    
#     # Sync completion data from UserProgress if it exists
#     if instance.user_progress_id:
#         user_progress = db.query(UserProgress).filter(
#             UserProgress.id == instance.user_progress_id
#         ).first()
        
#         if user_progress:
#             # Sync completion percentage and time spent from UserProgress
#             if user_progress.completion_percentage is not None:
#                 instance.completion_percentage = user_progress.completion_percentage
#             if user_progress.total_time_spent is not None:
#                 instance.total_time_spent = user_progress.total_time_spent
#             if user_progress.hints_used is not None:
#                 instance.hints_used = user_progress.hints_used
    
#     db.commit()
#     db.refresh(instance)
    
#     if not is_production:
#         logger.info(f"Updated simulation instance {instance_id} for student {current_user.id}")
#     return instance

# @router.post("/{instance_id}/start", response_model=StudentSimulationInstanceResponse)
# async def start_simulation_instance(
#     instance_id: int,
#     current_user: User = Depends(require_student),
#     db: Session = Depends(get_db)
# ):
#     """Start a simulation instance (only if simulation is published)"""
    
#     # Get base query for published instance
#     instance = _get_published_instance_query(db, current_user.id, instance_id).first()
    
#     if not instance:
#         raise HTTPException(
#             status_code=404, 
#             detail="Simulation instance not found or simulation is not published"
#         )
    
#     if instance.status != "not_started":
#         raise HTTPException(status_code=400, detail="Simulation instance already started")
    
#     # Update status and start time
#     instance.status = "in_progress"
#     instance.started_at = datetime.now(timezone.utc)
    
#     db.commit()
#     db.refresh(instance)
    
#     if not is_production:
#         logger.info(f"Started simulation instance {instance_id} for student {current_user.id}")
#     return instance

# @router.post("/{instance_id}/start-simulation")
# async def start_simulation_for_instance(
#     instance_id: str,  # Changed to str to accept both integer IDs and unique_ids
#     current_user: User = Depends(require_student),
#     db: Session = Depends(get_db)
# ):
#     """
#     Start the actual simulation for a student instance.
#     This properly initializes UserProgress and returns simulation data for the chat interface.
#     Accepts both integer ID and unique_id (SSI-XXXXXXXX format).
#     """
    
#     # Determine if instance_id is an integer or unique_id
#     instance = None
#     try:
#         # Try to parse as integer first
#         int_id = int(instance_id)
#         # Get the instance by integer ID (check if published when user_progress exists)
#         instance = db.query(StudentSimulationInstance).filter(
#             StudentSimulationInstance.id == int_id,
#             StudentSimulationInstance.student_id == current_user.id
#         ).first()
        
#         # If instance has user_progress, verify it's published
#         if instance and instance.user_progress_id:
#             user_progress = db.query(UserProgress).filter(
#                 UserProgress.id == instance.user_progress_id
#             ).first()
#             if user_progress:
#                 scenario = db.query(Scenario).filter(Scenario.id == user_progress.scenario_id).first()
#                 if scenario and scenario.is_draft:
#                     instance = None  # Don't allow draft simulations
#     except ValueError:
#         # It's a unique_id string
#         instance = db.query(StudentSimulationInstance).filter(
#             StudentSimulationInstance.unique_id == instance_id,
#             StudentSimulationInstance.student_id == current_user.id
#         ).first()
        
#         # If instance has user_progress, verify it's published
#         if instance and instance.user_progress_id:
#             user_progress = db.query(UserProgress).filter(
#                 UserProgress.id == instance.user_progress_id
#             ).first()
#             if user_progress:
#                 scenario = db.query(Scenario).filter(Scenario.id == user_progress.scenario_id).first()
#                 if scenario and scenario.is_draft:
#                     instance = None  # Don't allow draft simulations
    
#     if not instance:
#         raise HTTPException(
#             status_code=404,
#             detail="Simulation instance not found or simulation is not published"
#         )
    
#     # Get the cohort assignment to get the scenario
#     cohort_assignment = db.query(CohortSimulation).filter(
#         CohortSimulation.id == instance.cohort_assignment_id
#     ).first()
    
#     if not cohort_assignment:
#         raise HTTPException(status_code=404, detail="Cohort assignment not found")
    
#     scenario_id = cohort_assignment.simulation_id
    
#     # Get scenario
#     scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
#     if not scenario:
#         raise HTTPException(status_code=404, detail="Scenario not found")
    
#     # Log scenario status for debugging
#     if not is_production:
#         logger.info(f"[SCENE_COUNT] Loading scenario {scenario_id}: title='{scenario.title}', is_draft={scenario.is_draft}, status='{scenario.status}'")
    
#     # Check if UserProgress already exists and handle accordingly
#     user_progress = None
#     if instance.user_progress_id:
#         user_progress = db.query(UserProgress).filter(
#             UserProgress.id == instance.user_progress_id
#         ).first()
        
#         if user_progress:
#             # If already in progress, waiting to begin, or completed, return existing data (resume)
#             if user_progress.simulation_status in ["waiting_for_begin", "in_progress", "completed"]:
#                 if not is_production:
#                     logger.info(f"Resuming existing simulation for instance {instance_id} with status {user_progress.simulation_status}")
#                 # Will return existing simulation data below
#             else:
#                 # Reset progress if abandoned - reuse the same UserProgress record
#                 if not is_production:
#                     logger.info(f"Resetting abandoned simulation for instance {instance_id}")
                
#                 # Clean up related data
#                 db.query(SceneProgress).filter(
#                     SceneProgress.user_progress_id == user_progress.id
#                 ).delete()
#                 db.query(ConversationLog).filter(
#                     ConversationLog.user_progress_id == user_progress.id
#                 ).delete()
                
#                 # Reset the UserProgress (don't delete, just reset fields)
#                 # We'll update it below when creating "new" progress
#                 user_progress = None  # Mark for recreation
    
#     # Create new UserProgress if needed
#     if not user_progress:
#         # Get first scene
#         first_scene = db.query(ScenarioScene).filter(
#             ScenarioScene.scenario_id == scenario_id
#         ).order_by(ScenarioScene.scene_order).first()
        
#         if not first_scene:
#             raise HTTPException(status_code=400, detail="Scenario has no scenes")
        
#         # Get all scenes and personas
#         all_scenes = db.query(ScenarioScene).filter(
#             ScenarioScene.scenario_id == scenario_id
#         ).order_by(ScenarioScene.scene_order).all()
        
#         all_personas = db.query(ScenarioPersona).filter(
#             ScenarioPersona.scenario_id == scenario_id
#         ).all()
        
#         # Helper function to check if persona is the main character (student role)
#         def is_main_character_create(persona_name, student_role):
#             if not student_role:
#                 return False
            
#             import re
            
#             # Extract just the name part from student role (before any parentheses or additional info)
#             student_name = student_role.split('(')[0].strip()
            
#             # Remove common title prefixes (Mr., Mrs., Ms., Dr., Prof., etc.) and normalize
#             def normalize_name(name):
#                 normalized = name.strip()
#                 # Remove title prefixes
#                 normalized = re.sub(r'^(Mr\.|Mrs\.|Ms\.|Miss|Dr\.|Prof\.|Professor)\s+', '', normalized, flags=re.IGNORECASE)
#                 # Remove all non-alphabetic characters
#                 normalized = re.sub(r'[^a-zA-Z]', '', normalized).lower()
#                 return normalized
            
#             return normalize_name(persona_name) == normalize_name(student_name)
        
#         # Get personas involved in each scene from the junction table
#         scene_personas_map = {}
#         for scene in all_scenes:
#             involved_personas = db.query(ScenarioPersona).join(
#                 scene_personas, ScenarioPersona.id == scene_personas.c.persona_id
#             ).filter(
#                 scene_personas.c.scene_id == scene.id
#             ).all()
#             # Filter out student role from scene personas map
#             scene_personas_map[scene.id] = [
#                 p.name for p in involved_personas 
#                 if not is_main_character_create(p.name, scenario.student_role)
#             ]
        
#         # Build orchestrator data
#         scenario_data = {
#             "id": scenario.id,
#             "title": scenario.title,
#             "description": scenario.description,
#             "challenge": scenario.challenge,
#             "student_role": scenario.student_role,  # Add student role to orchestrator data
#             "scenes": [
#                 {
#                     "id": scene.id,
#                     "title": scene.title,
#                     "description": scene.description,
#                     "objectives": [scene.user_goal] if scene.user_goal else ["Complete the scene interaction"],
#                     "image_url": scene.image_url,
#                     "agent_ids": [
#                         p.name.lower().replace(" ", "_") for p in all_personas
#                         if not is_main_character_create(p.name, scenario.student_role)
#                     ],
#                     "personas_involved": scene_personas_map.get(scene.id, []),
#                     "max_turns": scene.timeout_turns if scene.timeout_turns is not None else 15,
#                     "success_criteria": f"User achieves: {scene.user_goal or 'scene completion'}"
#                 }
#                 for scene in all_scenes
#             ],
#             "personas": [
#                 {
#                     "id": persona.name.lower().replace(" ", "_"),
#                     "db_id": persona.id,
#                     "identity": {
#                         "name": persona.name,
#                         "role": persona.role,
#                         "bio": persona.background or "Professional team member"
#                     },
#                     "personality": {
#                         "goals": persona.primary_goals or ["Support team objectives"],
#                         "traits": persona.personality_traits or "Professional and collaborative"
#                     },
#                     "system_prompt": persona.system_prompt,
#                     "image_url": persona.image_url
#                 }
#                 for persona in all_personas
#                 if not is_main_character_create(persona.name, scenario.student_role)
#             ]
#         }
        
#         # Create UserProgress
#         user_progress = UserProgress(
#             user_id=current_user.id,
#             scenario_id=scenario_id,
#             current_scene_id=first_scene.id,
#             simulation_status="waiting_for_begin",
#             session_count=1,
#             scenes_completed=[],
#             orchestrator_data=scenario_data,
#             started_at=datetime.now(timezone.utc),
#             last_activity=datetime.now(timezone.utc)
#         )
#         db.add(user_progress)
#         db.flush()
        
#         # Create scene progress for first scene
#         scene_progress = SceneProgress(
#             user_progress_id=user_progress.id,
#             scene_id=first_scene.id,
#             status="in_progress",
#             started_at=datetime.now(timezone.utc)
#         )
#         db.add(scene_progress)
        
#         # Save initial welcome message to conversation history so it persists on reload
#         welcome_text = f"""🎯 **{scenario.title}**

# {scenario.description}

# **Your Role:** {scenario.student_role}

# **Current Scene:** {first_scene.title}

# **Instructions:**
# • Type **"begin"** to start the simulation
# • Type **"help"** for available commands
# • Use natural conversation to interact with personas"""
        
#         welcome_log = ConversationLog(
#             user_progress_id=user_progress.id,
#             scene_id=first_scene.id,
#             message_type="system",
#             sender_name="System",
#             message_content=welcome_text,
#             message_order=1,
#             timestamp=datetime.now(timezone.utc)
#         )
#         db.add(welcome_log)
#         if not is_production:
#             logger.info(f"[START_SIMULATION] Saved initial welcome message for user_progress {user_progress.id}")
        
#         # Link UserProgress to instance
#         instance.user_progress_id = user_progress.id
    
#     # Update instance status (but don't modify completed/graded instances)
#     if instance.status == "not_started":
#         instance.status = "in_progress"
#         instance.started_at = datetime.now(timezone.utc)
#         instance.attempts_count += 1
#         db.commit()
#         db.refresh(instance)
#         db.refresh(user_progress)
#         if not is_production:
#             logger.info(f"[START] Started instance {instance.id} for student {current_user.id}")
#     elif instance.status in ["completed", "graded", "submitted"]:
#         # Don't modify completed simulations - just return data for review
#         if not is_production:
#             logger.info(f"[REVIEW] Loading completed instance {instance.id} with status {instance.status}")
#         # No commit needed - just loading data
#     else:
#         # Instance is in_progress - just load it
#         if not is_production:
#             logger.info(f"[RESUME] Resuming in-progress instance {instance.id}")
#         # If started_at is missing for some reason, set it now to avoid inflated time_spent
#         if not instance.started_at:
#             instance.started_at = datetime.now(timezone.utc)
#         db.commit()
#         db.refresh(instance)
#         db.refresh(user_progress)
    
#     # Get current scene
#     current_scene = db.query(ScenarioScene).filter(
#         ScenarioScene.id == user_progress.current_scene_id
#     ).first()
    
#     if not current_scene:
#         raise HTTPException(status_code=404, detail="Current scene not found")
    
#     # Get personas involved in current scene
#     involved_personas = db.query(ScenarioPersona).join(
#         scene_personas, ScenarioPersona.id == scene_personas.c.persona_id
#     ).filter(
#         scene_personas.c.scene_id == current_scene.id,
#         ScenarioPersona.deleted_at.is_(None)  # Exclude soft-deleted personas
#     ).all()
    
#     # Helper function to check if persona is the main character (student role)
#     def is_main_character(persona_name, student_role):
#         if not student_role:
#             return False
        
#         import re
        
#         # Extract just the name part from student role (before any parentheses or additional info)
#         student_name = student_role.split('(')[0].strip()
        
#         # Remove common title prefixes (Mr., Mrs., Ms., Dr., Prof., etc.) and normalize
#         def normalize_name(name):
#             normalized = name.strip()
#             # Remove title prefixes
#             normalized = re.sub(r'^(Mr\.|Mrs\.|Ms\.|Miss|Dr\.|Prof\.|Professor)\s+', '', normalized, flags=re.IGNORECASE)
#             # Remove all non-alphabetic characters
#             normalized = re.sub(r'[^a-zA-Z]', '', normalized).lower()
#             return normalized
        
#         return normalize_name(persona_name) == normalize_name(student_name)
    
#     # Build response
#     learning_objectives = scenario.learning_objectives
#     if isinstance(learning_objectives, str):
#         learning_objectives = [learning_objectives]
#     elif learning_objectives is None:
#         learning_objectives = []
    
#     # Get total scenes count
#     total_scenes = db.query(ScenarioScene).filter(
#         ScenarioScene.scenario_id == scenario_id
#     ).count()
#     if not is_production:
#         logger.info(f"[SCENE_COUNT] Scenario {scenario_id} has {total_scenes} total scenes")
    
#     # Get conversation history for resuming
#     conversation_logs = db.query(ConversationLog).filter(
#         ConversationLog.user_progress_id == user_progress.id
#     ).order_by(ConversationLog.message_order, ConversationLog.timestamp).all()
    
#     # Format conversation logs for frontend
#     messages_history = []
#     # Pre-fetch all personas to avoid N+1 queries
#     persona_map = {}
#     if conversation_logs:
#         persona_ids = [log.persona_id for log in conversation_logs if log.persona_id]
#         if persona_ids:
#             personas = db.query(ScenarioPersona).filter(ScenarioPersona.id.in_(persona_ids)).all()
#             persona_map = {p.id: p for p in personas}
    
#     for log in conversation_logs:
#         # Transform "User" to "You" for frontend display
#         sender_name = log.sender_name or ("User" if log.message_type == "user" else "System")
#         if sender_name == "User":
#             sender_name = "You"
        
#         # Get persona info if available
#         persona_name = None
#         persona_role = None
#         if log.persona_id and log.persona_id in persona_map:
#             persona = persona_map[log.persona_id]
#             persona_name = persona.name
#             persona_role = persona.role
#         elif log.message_type == "ai_persona" and log.sender_name:
#             # Fallback: use sender_name if persona lookup failed
#             persona_name = log.sender_name
        
#         message_dict = {
#             "id": log.id,
#             "sender": sender_name,
#             "text": log.message_content,
#             "timestamp": log.timestamp.isoformat() if log.timestamp else None,
#             "type": log.message_type,
#             "persona_id": log.persona_id,
#             "scene_id": log.scene_id,  # Include scene_id to track which scenes have messages
#             "persona_name": persona_name,
#             "persona_role": persona_role
#         }
#         messages_history.append(message_dict)
    
#     # Get current turn count from orchestrator state
#     turn_count = 0
#     if user_progress.orchestrator_data and 'state' in user_progress.orchestrator_data:
#         turn_count = user_progress.orchestrator_data['state'].get('turn_count', 0)
    
#     # Get completed scenes
#     completed_scene_ids = []
#     scene_progresses = db.query(SceneProgress).filter(
#         SceneProgress.user_progress_id == user_progress.id,
#         SceneProgress.status == "completed"
#     ).all()
#     completed_scene_ids = [sp.scene_id for sp in scene_progresses]
    
#     # Get all scenes with personas for persona lookup across scenes
#     all_scenes = db.query(ScenarioScene).filter(
#         ScenarioScene.scenario_id == scenario_id
#     ).order_by(ScenarioScene.scene_order).all()
#     if not is_production:
#         logger.info(f"[SCENE_COUNT] Retrieved {len(all_scenes)} scenes for scenario {scenario_id}: {[s.id for s in all_scenes]}")
    
#     # Verify scene count consistency
#     if len(all_scenes) != total_scenes:
#         logger.warning(f"[SCENE_COUNT] MISMATCH: total_scenes={total_scenes} but all_scenes array has {len(all_scenes)} scenes for scenario {scenario_id}")
#     if len(all_scenes) == 0:
#         logger.error(f"[SCENE_COUNT] ERROR: No scenes found for scenario {scenario_id} - this should not happen!")
    
#     # Get all personas for the scenario
#     all_personas = db.query(ScenarioPersona).filter(
#         ScenarioPersona.scenario_id == scenario_id,
#         ScenarioPersona.deleted_at.is_(None)
#     ).all()
    
#     # Build scenes with personas for frontend lookup
#     scenes_with_personas = []
#     for scene in all_scenes:
#         scene_personas_list = db.query(ScenarioPersona).join(
#             scene_personas, ScenarioPersona.id == scene_personas.c.persona_id
#         ).filter(
#             scene_personas.c.scene_id == scene.id,
#             ScenarioPersona.deleted_at.is_(None)
#         ).all()
        
#         scenes_with_personas.append({
#             "id": scene.id,
#             "title": scene.title,
#             "scene_order": scene.scene_order,
#             "personas": [
#                 {
#                     "id": p.id,
#                     "name": p.name,
#                     "role": p.role,
#                     "background": p.background,
#                     "correlation": p.correlation,
#                     "primary_goals": p.primary_goals,
#                     "personality_traits": p.personality_traits,
#                     "image_url": p.image_url  # Always include image_url, even if None/empty
#                 }
#                 for p in scene_personas_list
#                 if not is_main_character(p.name, scenario.student_role)
#             ]
#         })
    
#     # Get case study PDF URL from Scenario.case_study_url (safely handle if column doesn't exist)
#     case_study_url = getattr(scenario, 'case_study_url', None)
#     if case_study_url:
#         debug_log(f"[SIMULATION_INSTANCE] Found case study PDF: {case_study_url}")
    
#     response_data = {
#         "user_progress_id": user_progress.id,
#         "scenario": {
#             "id": scenario.id,
#             "title": scenario.title,
#             "description": scenario.description,
#             "challenge": scenario.challenge,
#             "industry": scenario.industry,
#             "learning_objectives": learning_objectives,
#             "student_role": scenario.student_role,
#             "total_scenes": total_scenes,
#             "case_study_url": case_study_url
#         },
#         "current_scene": {
#             "id": current_scene.id,
#             "title": current_scene.title,
#             "description": current_scene.description,
#             "user_goal": current_scene.user_goal,
#             "scene_order": current_scene.scene_order,
#             "estimated_duration": current_scene.estimated_duration,
#             "image_url": current_scene.image_url,
#             "timeout_turns": current_scene.timeout_turns if current_scene.timeout_turns is not None else 15,
#             "personas": [
#                 {
#                     "id": p.id,
#                     "name": p.name,
#                     "role": p.role,
#                     "background": p.background,
#                     "correlation": p.correlation,
#                     "primary_goals": p.primary_goals,
#                     "personality_traits": p.personality_traits,
#                     "image_url": p.image_url  # Always include image_url, even if None/empty
#                 }
#                 for p in involved_personas
#                 if not is_main_character(p.name, scenario.student_role)
#             ]
#         },
#         "all_scenes": scenes_with_personas,  # Add all scenes with personas for lookup
#         "simulation_status": instance.status if instance.status in ["completed", "graded", "submitted"] else user_progress.simulation_status,
#         "instance_status": instance.status,  # Add instance status for debugging
#         "user_progress_status": user_progress.simulation_status,  # Add for debugging
#         "instance_id": instance.id,
#         "conversation_history": messages_history,  # Add conversation history
#         "is_resuming": len(messages_history) > 0,  # Flag to indicate if this is a resume
#         "turn_count": turn_count,  # Current turn count
#         "completed_scene_ids": completed_scene_ids  # List of completed scene IDs
#     }
    
#     return response_data

# @router.post("/{instance_id}/complete", response_model=StudentSimulationInstanceResponse)
# async def complete_simulation_instance(
#     instance_id: int,
#     current_user: User = Depends(require_student),
#     db: Session = Depends(get_db)
# ):
#     """Complete a simulation instance (only if simulation is published)"""
    
#     # Get base query for published instance
#     instance = _get_published_instance_query(db, current_user.id, instance_id).first()
    
#     if not instance:
#         raise HTTPException(
#             status_code=404, 
#             detail="Simulation instance not found or simulation is not published"
#         )
    
#     if instance.status != "in_progress":
#         raise HTTPException(status_code=400, detail="Simulation instance not in progress")
    
#     # Update status and completion time (server-of-record update)
#     from datetime import datetime, timezone
#     now = datetime.now(timezone.utc)
#     instance.status = "completed"
#     instance.completed_at = now
#     instance.completion_percentage = 100.0

#     # Also update linked UserProgress so professor views reflect completion immediately
#     if instance.user_progress_id:
#         user_progress = db.query(UserProgress).filter(UserProgress.id == instance.user_progress_id).first()
#         if user_progress:
#             user_progress.simulation_status = "completed"
#             user_progress.last_activity = now
#             # Best-effort: mark current scene as completed if not already
#             try:
#                 sp = db.query(SceneProgress).filter(
#                     SceneProgress.user_progress_id == user_progress.id,
#                     SceneProgress.scene_id == user_progress.current_scene_id
#                 ).first()
#                 if sp and sp.status != "completed":
#                     sp.status = "completed"
#                     sp.completed_at = now
#             except Exception:
#                 pass
    
#     db.commit()
#     db.refresh(instance)
    
#     if not is_production:
#         logger.info(f"Completed simulation instance {instance_id} for student {current_user.id}")
#     return instance

# @router.get("/assignment/{assignment_id}/instances")
# async def get_simulation_assignment_instances(
#     assignment_id: int,
#     current_user: User = Depends(require_professor),
#     db: Session = Depends(get_db)
# ):
#     """Get all student instances for a specific simulation assignment (professor view)"""
#     try:
#         if not is_production:
#             logger.info(f"GET request: assignment_id={assignment_id}, user_id={current_user.id}")
        
#         # Get the assignment and verify professor has access
#         assignment = db.query(CohortSimulation).filter(
#             CohortSimulation.id == assignment_id
#         ).first()
        
#         if not assignment:
#             logger.warning(f"Assignment {assignment_id} not found")
#             raise HTTPException(status_code=404, detail="Simulation assignment not found")
        
#         # Verify professor has access to this cohort
#         cohort = db.query(Cohort).filter(
#             Cohort.id == assignment.cohort_id,
#             Cohort.created_by == current_user.id
#         ).first()
        
#         if not cohort:
#             logger.warning(f"User {current_user.id} not authorized for cohort {assignment.cohort_id}")
#             raise HTTPException(status_code=403, detail="Not authorized to view this data")
    
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error in get_simulation_assignment_instances (initial checks): {str(e)}", exc_info=True)
#         raise HTTPException(status_code=500, detail=f"Failed to fetch student instances: {str(e)}")
    
#     try:
#         # Get all approved students in the cohort
#         from database.models import CohortStudent
#         cohort_students = db.query(CohortStudent, User).join(
#             User, CohortStudent.student_id == User.id
#         ).filter(
#             CohortStudent.cohort_id == assignment.cohort_id,
#             CohortStudent.status == "approved"
#         ).all()
        
#         if not is_production:
#             logger.info(f"Found {len(cohort_students)} approved students in cohort {assignment.cohort_id}")
        
#         # Get all existing instances for this assignment
#         existing_instances = db.query(StudentSimulationInstance).filter(
#             StudentSimulationInstance.cohort_assignment_id == assignment_id
#         ).all()
        
#         # Create a map of student_id -> instance for quick lookup
#         instance_map = {instance.student_id: instance for instance in existing_instances}
        
#         if not is_production:
#             logger.info(f"Found {len(existing_instances)} existing instances for assignment {assignment_id}")
        
#         result = []
#         for cohort_student, student in cohort_students:
#             # Check if student has an instance
#             instance = instance_map.get(student.id)
            
#             # If no instance exists, create a default entry
#             if not instance:
#                 if not is_production:
#                     logger.info(f"Creating default entry for student {student.id} who doesn't have an instance yet")
#                 # Return default values for students without instances
#                 result.append({
#                     "id": None,  # No instance ID yet
#                     "cohort_assignment_id": assignment_id,
#                     "student_id": student.id,
#                     "student_name": student.full_name,
#                     "student_email": student.email,
#                     "user_progress_id": None,
#                     "status": "not_started",
#                     "started_at": None,
#                     "completed_at": None,
#                     "submitted_at": None,
#                     "grade": None,
#                     "feedback": None,
#                     "graded_by": None,
#                     "graded_at": None,
#                     "completion_percentage": 0.0,
#                     "total_time_spent": 0,
#                     "attempts_count": 0,
#                     "hints_used": 0,
#                     "is_overdue": False,
#                     "days_late": 0,
#                     "created_at": None,
#                     "updated_at": None
#                 })
#                 continue
            
#             # Student has an instance - process it normally
#             # Calculate real-time progress if user_progress exists
#             completion_percentage = instance.completion_percentage or 0.0
#             total_time_spent = instance.total_time_spent or 0
#             user_progress = None

#             try:
#                 if instance.user_progress_id:
#                     user_progress = db.query(UserProgress).filter(
#                         UserProgress.id == instance.user_progress_id
#                     ).first()
                
#                 if user_progress:
#                     # If simulation is completed or graded, force 100% completion
#                     if (user_progress.simulation_status in ["completed", "graded"] or 
#                         instance.status in ["completed", "graded", "submitted"]):
#                         completion_percentage = 100.0
#                         if instance.completion_percentage != 100.0:
#                             instance.completion_percentage = 100.0
#                             db.commit()
#                             if not is_production:
#                                 logger.info(f"Forced completion_percentage to 100% for completed instance {instance.id}")
#                     else:
#                         # Calculate completion percentage from scene progress
#                         scenario = db.query(Scenario).filter(
#                             Scenario.id == user_progress.scenario_id
#                         ).first()
                        
#                         if scenario:
#                             total_scenes = db.query(ScenarioScene).filter(
#                                 ScenarioScene.scenario_id == scenario.id
#                             ).count()
                            
#                             completed_scenes = db.query(SceneProgress).filter(
#                                 SceneProgress.user_progress_id == user_progress.id,
#                                 SceneProgress.status == "completed"
#                             ).count()
                            
#                             if total_scenes > 0:
#                                 completion_percentage = (completed_scenes / total_scenes) * 100
#                                 # Update instance if changed
#                                 if abs(completion_percentage - (instance.completion_percentage or 0)) > 0.01:
#                                     instance.completion_percentage = completion_percentage
#                                     db.commit()
                    
#                     # Calculate time spent preferring started_at -> completed_at
#                     try:
#                         start_dt = instance.started_at or user_progress.created_at
#                         end_dt = instance.completed_at or user_progress.last_activity or user_progress.updated_at or datetime.now(timezone.utc)
#                         if start_dt:
#                             if start_dt.tzinfo is None:
#                                 start_dt = start_dt.replace(tzinfo=timezone.utc)
#                             if end_dt and end_dt.tzinfo is None:
#                                 end_dt = end_dt.replace(tzinfo=timezone.utc)
#                             if end_dt:
#                                 time_delta = end_dt - start_dt
#                                 total_time_spent = max(0, int(time_delta.total_seconds()))
#                                 if abs(total_time_spent - (instance.total_time_spent or 0)) > 1:
#                                     instance.total_time_spent = total_time_spent
#                                     db.commit()
#                     except Exception as e:
#                         logger.warning(f"Could not calculate time spent for instance {instance.id}: {e}")
#             except Exception as e:
#                 # Don't let one instance error break the whole request
#                 logger.error(f"Error processing instance {instance.id}: {e}")
#                 # Use existing values if calculation fails
#                 completion_percentage = instance.completion_percentage or 0.0
#                 total_time_spent = instance.total_time_spent or 0
            
#             # Append result for this instance (INSIDE the loop)
#             result.append({
#                 "id": instance.id,
#                 "cohort_assignment_id": instance.cohort_assignment_id,
#                 "student_id": instance.student_id,
#                 "student_name": student.full_name,
#                 "student_email": student.email,
#                 "user_progress_id": instance.user_progress_id,
#                 "status": instance.status,
#                 "started_at": instance.started_at,
#                 "completed_at": instance.completed_at,
#                 "submitted_at": instance.submitted_at,
#                 "grade": instance.grade,
#                 "feedback": instance.feedback,
#                 "graded_by": instance.graded_by,
#                 "graded_at": instance.graded_at,
#                 "completion_percentage": completion_percentage,
#                 "total_time_spent": total_time_spent,
#                 "attempts_count": instance.attempts_count,
#                 "hints_used": instance.hints_used,
#                 "is_overdue": instance.is_overdue,
#                 "days_late": instance.days_late,
#                 "created_at": instance.created_at,
#                 "updated_at": instance.updated_at
#             })
        
#         if not is_production:
#             logger.info(f"Successfully retrieved {len(result)} student instances for assignment {assignment_id}")
#         return result
        
#     except Exception as e:
#         logger.error(f"Error fetching student instances for assignment {assignment_id}: {str(e)}", exc_info=True)
#         raise HTTPException(status_code=500, detail=f"Failed to fetch student instances: {str(e)}")

# @router.get("/cohort/{cohort_id}/instances", response_model=List[StudentSimulationInstanceResponse])
# async def get_cohort_simulation_instances(
#     cohort_id: int,
#     current_user: User = Depends(require_professor),
#     db: Session = Depends(get_db)
# ):
#     """Get all simulation instances for a cohort (professor view)"""
    
#     # Verify professor has access to the cohort
#     cohort = db.query(Cohort).filter(
#         Cohort.id == cohort_id,
#         Cohort.created_by == current_user.id
#     ).first()
    
#     if not cohort:
#         raise HTTPException(status_code=404, detail="Cohort not found")
    
#     # Get all instances for this cohort
#     instances = db.query(StudentSimulationInstance).join(
#         CohortSimulation,
#         StudentSimulationInstance.cohort_assignment_id == CohortSimulation.id
#     ).filter(
#         CohortSimulation.cohort_id == cohort_id
#     ).all()
    
#     return instances

# @router.post("/{instance_id}/grade", response_model=StudentSimulationInstanceResponse)
# async def grade_simulation_instance(
#     instance_id: int,
#     grade_data: dict,  # {"grade": float, "feedback": str}
#     current_user: User = Depends(require_professor),
#     db: Session = Depends(get_db)
# ):
#     """Grade a student simulation instance (professor only)"""
#     from datetime import datetime, timezone
    
#     instance = db.query(StudentSimulationInstance).filter(
#         StudentSimulationInstance.id == instance_id
#     ).first()
    
#     if not instance:
#         raise HTTPException(status_code=404, detail="Simulation instance not found")
    
#     # Verify professor has access to this instance's cohort
#     cohort_assignment = db.query(CohortSimulation).filter(
#         CohortSimulation.id == instance.cohort_assignment_id
#     ).first()
    
#     if not cohort_assignment:
#         raise HTTPException(status_code=404, detail="Cohort assignment not found")
    
#     cohort = db.query(Cohort).filter(
#         Cohort.id == cohort_assignment.cohort_id,
#         Cohort.created_by == current_user.id
#     ).first()
    
#     if not cohort:
#         raise HTTPException(status_code=403, detail="Not authorized to grade this simulation")
    
#     # Update the instance with grade
#     instance.grade = grade_data.get("grade")
#     instance.feedback = grade_data.get("feedback")
#     instance.graded_by = current_user.id
#     instance.graded_at = datetime.now(timezone.utc)
#     instance.status = "graded"
    
#     db.commit()
#     db.refresh(instance)
    
#     if not is_production:
#         logger.info(f"Graded simulation instance {instance_id} with grade {instance.grade}")
#     return instance

# @router.get("/cohort/{cohort_id}/grading-summary")
# async def get_cohort_grading_summary(
#     cohort_id: int,
#     current_user: User = Depends(require_professor),
#     db: Session = Depends(get_db)
# ):
#     """Get grading summary for a cohort"""
    
#     # Verify professor has access to the cohort
#     cohort = db.query(Cohort).filter(
#         Cohort.id == cohort_id,
#         Cohort.created_by == current_user.id
#     ).first()
    
#     if not cohort:
#         raise HTTPException(status_code=404, detail="Cohort not found")
    
#     # Get grading statistics
#     instances = db.query(StudentSimulationInstance).join(
#         CohortSimulation
#     ).filter(
#         CohortSimulation.cohort_id == cohort_id
#     ).all()
    
#     total_instances = len(instances)
#     graded_instances = len([i for i in instances if i.grade is not None])
#     pending_instances = total_instances - graded_instances
    
#     # Calculate average grade
#     graded_grades = [i.grade for i in instances if i.grade is not None]
#     average_grade = sum(graded_grades) / len(graded_grades) if graded_grades else 0
    
#     return {
#         "total_instances": total_instances,
#         "graded_instances": graded_instances,
#         "pending_instances": pending_instances,
#         "average_grade": round(average_grade, 2),
#         "completion_rate": round((graded_instances / total_instances * 100) if total_instances > 0 else 0, 2)
#     }

"""
Student simulation instance management API endpoints
OPTIMIZED: N+1 query fixes with batch loading
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime, timezone
from sqlalchemy import func

from database.connection import get_db
from database.models import (
    User, StudentSimulationInstance, CohortSimulation, Cohort, Scenario, UserProgress,
    ScenarioScene, ScenarioPersona, SceneProgress, ConversationLog, scene_personas
)
from database.schemas import StudentSimulationInstanceResponse, StudentSimulationInstanceCreate, StudentSimulationInstanceUpdate
from utilities.auth import require_student
from utilities.debug_logging import debug_log
from middleware.role_auth import require_professor
import os

router = APIRouter(prefix="/student-simulation-instances", tags=["Student Simulation Instances"])
logger = logging.getLogger(__name__)
is_production = os.getenv("ENVIRONMENT", "development") == "production"


def _get_published_instance_query(
    db: Session, 
    student_id: int, 
    instance_id: Optional[int] = None
):
    """
    Helper function to build the base query for published simulation instances.
    """
    query = db.query(StudentSimulationInstance).join(
        UserProgress, StudentSimulationInstance.user_progress_id == UserProgress.id
    ).join(
        Scenario, UserProgress.scenario_id == Scenario.id
    ).filter(
        StudentSimulationInstance.student_id == student_id,
        Scenario.is_draft == False,
        Scenario.status == "active"
    )
    
    if instance_id is not None:
        query = query.filter(StudentSimulationInstance.id == instance_id)
    
    return query


def _batch_load_scene_personas(db: Session, scene_ids: List[int]) -> Dict[int, List[ScenarioPersona]]:
    """
    OPTIMIZATION: Batch load all personas for multiple scenes in one query.
    Returns: {scene_id: [personas]}
    """
    if not scene_ids:
        return {}
    
    persona_data = db.query(
        scene_personas.c.scene_id,
        ScenarioPersona
    ).join(
        ScenarioPersona, ScenarioPersona.id == scene_personas.c.persona_id
    ).filter(
        scene_personas.c.scene_id.in_(scene_ids),
        ScenarioPersona.deleted_at.is_(None)
    ).all()
    
    scene_personas_map = {}
    for scene_id, persona in persona_data:
        if scene_id not in scene_personas_map:
            scene_personas_map[scene_id] = []
        scene_personas_map[scene_id].append(persona)
    
    return scene_personas_map


@router.get("/", response_model=List[Dict[str, Any]])
async def get_student_simulation_instances(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db),
    status_filter: Optional[str] = Query(None),
    cohort_id: Optional[int] = Query(None)
):
    """Get simulation instances for the current student (only for published simulations)"""
    try:
        if not is_production:
            logger.info(f"GET student simulations: student_id={current_user.id}, cohort_id={cohort_id}, status_filter={status_filter}")
        
        from database.models import CohortStudent
        
        # Get all cohorts the student is enrolled in
        student_cohorts = db.query(CohortStudent).filter(
            CohortStudent.student_id == current_user.id,
            CohortStudent.status == "approved"
        ).all()
        
        cohort_ids = [sc.cohort_id for sc in student_cohorts]
        if not is_production:
            logger.info(f"Student {current_user.id} is enrolled in cohorts: {cohort_ids}")
        
        if not cohort_ids:
            logger.warning(f"Student {current_user.id} is not enrolled in any cohorts")
            return []
        
        # Get all published simulations assigned to these cohorts
        from sqlalchemy.orm import joinedload
        
        cohort_simulations_query = db.query(CohortSimulation).join(
            Scenario, CohortSimulation.simulation_id == Scenario.id
        ).join(
            Cohort, CohortSimulation.cohort_id == Cohort.id
        ).options(
            joinedload(CohortSimulation.simulation),
            joinedload(CohortSimulation.cohort).joinedload(Cohort.creator)
        ).filter(
            CohortSimulation.cohort_id.in_(cohort_ids),
            Scenario.is_draft == False,
            Scenario.status == "active"
        )
        
        if cohort_id:
            cohort_simulations_query = cohort_simulations_query.filter(CohortSimulation.cohort_id == cohort_id)
        
        cohort_simulations = cohort_simulations_query.all()
        if not is_production:
            logger.info(f"Found {len(cohort_simulations)} published simulations assigned to student's cohorts")
        
        # OPTIMIZATION: Batch load all instances upfront
        cohort_assignment_ids = [cs.id for cs in cohort_simulations]
        all_instances = db.query(StudentSimulationInstance).filter(
            StudentSimulationInstance.cohort_assignment_id.in_(cohort_assignment_ids),
            StudentSimulationInstance.student_id == current_user.id
        ).all()
        
        instance_map = {inst.cohort_assignment_id: inst for inst in all_instances}
        
        # OPTIMIZATION: Batch load all user_progress records
        user_progress_ids = [inst.user_progress_id for inst in all_instances if inst.user_progress_id]
        user_progress_map = {}
        if user_progress_ids:
            user_progresses = db.query(UserProgress).filter(
                UserProgress.id.in_(user_progress_ids)
            ).all()
            user_progress_map = {up.id: up for up in user_progresses}
        
        # OPTIMIZATION: Batch load all scenarios
        scenario_ids = [up.scenario_id for up in user_progress_map.values() if up.scenario_id]
        scenario_map = {}
        if scenario_ids:
            scenarios = db.query(Scenario).filter(Scenario.id.in_(scenario_ids)).all()
            scenario_map = {s.id: s for s in scenarios}
        
        # OPTIMIZATION: Batch load scene counts for all scenarios
        scene_count_map = {}
        if scenario_ids:
            scene_counts = db.query(
                ScenarioScene.scenario_id,
                func.count(ScenarioScene.id).label('count')
            ).filter(
                ScenarioScene.scenario_id.in_(scenario_ids)
            ).group_by(ScenarioScene.scenario_id).all()
            scene_count_map = {scenario_id: count for scenario_id, count in scene_counts}
        
        # OPTIMIZATION: Batch load completed scene progress counts
        completed_scene_count_map = {}
        if user_progress_ids:
            completed_counts = db.query(
                SceneProgress.user_progress_id,
                func.count(SceneProgress.id).label('count')
            ).filter(
                SceneProgress.user_progress_id.in_(user_progress_ids),
                SceneProgress.status == "completed"
            ).group_by(SceneProgress.user_progress_id).all()
            completed_scene_count_map = {up_id: count for up_id, count in completed_counts}
        
        # Format response
        result = []
        for cohort_simulation in cohort_simulations:
            try:
                instance = instance_map.get(cohort_simulation.id)
                
                if not instance:
                    try:
                        from utilities.id_generator import generate_unique_simulation_instance_id
                        
                        user_progress = UserProgress(
                            user_id=current_user.id,
                            scenario_id=cohort_simulation.simulation_id,
                            simulation_status="not_started"
                        )
                        db.add(user_progress)
                        db.flush()
                        
                        instance = StudentSimulationInstance(
                            unique_id=generate_unique_simulation_instance_id(db),
                            cohort_assignment_id=cohort_simulation.id,
                            student_id=current_user.id,
                            user_progress_id=user_progress.id
                        )
                        db.add(instance)
                        db.commit()
                        db.refresh(instance)
                        if not is_production:
                            logger.info(f"Auto-created simulation instance {instance.unique_id} for student {current_user.id}")
                    except Exception as e:
                        logger.error(f"Failed to auto-create instance: {str(e)}")
                        db.rollback()
                        continue
                
                if status_filter and instance.status != status_filter:
                    continue
                
                completion_percentage = instance.completion_percentage or 0.0
                total_time_spent = instance.total_time_spent or 0
                
                try:
                    if instance.user_progress_id:
                        user_progress = user_progress_map.get(instance.user_progress_id)
                        
                        if user_progress:
                            if (user_progress.simulation_status in ["completed", "graded"] or 
                                instance.status in ["completed", "graded", "submitted"]):
                                completion_percentage = 100.0
                                if instance.completion_percentage != 100.0:
                                    instance.completion_percentage = 100.0
                                    db.commit()
                            else:
                                scenario = scenario_map.get(user_progress.scenario_id) if user_progress.scenario_id else None
                                
                                if scenario:
                                    total_scenes = scene_count_map.get(scenario.id, 0)
                                    completed_scenes = completed_scene_count_map.get(user_progress.id, 0)
                                    
                                    if total_scenes > 0:
                                        completion_percentage = (completed_scenes / total_scenes) * 100
                                        if abs(completion_percentage - (instance.completion_percentage or 0)) > 0.01:
                                            instance.completion_percentage = completion_percentage
                                            db.commit()
                            
                            try:
                                start_dt = instance.started_at or user_progress.created_at
                                end_dt = instance.completed_at or user_progress.last_activity or user_progress.updated_at or datetime.now(timezone.utc)
                                if start_dt:
                                    if start_dt.tzinfo is None:
                                        start_dt = start_dt.replace(tzinfo=timezone.utc)
                                    if end_dt and end_dt.tzinfo is None:
                                        end_dt = end_dt.replace(tzinfo=timezone.utc)
                                    if end_dt:
                                        time_delta = end_dt - start_dt
                                        total_time_spent = max(0, int(time_delta.total_seconds()))
                                        if abs(total_time_spent - (instance.total_time_spent or 0)) > 1:
                                            instance.total_time_spent = total_time_spent
                                            db.commit()
                            except Exception as e:
                                logger.warning(f"Could not calculate time spent for instance {instance.id}: {e}")
                except Exception as e:
                    logger.error(f"Error calculating progress for instance {instance.id}: {e}")
                    completion_percentage = instance.completion_percentage or 0.0
                    total_time_spent = instance.total_time_spent or 0
                
                simulation = cohort_simulation.simulation
                cohort = cohort_simulation.cohort
                
                professor_name = "Unknown"
                if cohort and hasattr(cohort, 'creator') and cohort.creator:
                    professor_name = cohort.creator.name if hasattr(cohort.creator, 'name') else "Unknown"
                
                result.append({
                    "id": instance.id,
                    "unique_id": instance.unique_id,
                    "cohort_assignment_id": instance.cohort_assignment_id,
                    "student_id": instance.student_id,
                    "user_progress_id": instance.user_progress_id,
                    "status": instance.status,
                    "started_at": instance.started_at,
                    "completed_at": instance.completed_at,
                    "submitted_at": instance.submitted_at,
                    "grade": instance.grade,
                    "feedback": instance.feedback,
                    "graded_by": instance.graded_by,
                    "graded_at": instance.graded_at,
                    "completion_percentage": completion_percentage,
                    "total_time_spent": total_time_spent,
                    "attempts_count": instance.attempts_count,
                    "hints_used": instance.hints_used,
                    "is_overdue": instance.is_overdue,
                    "days_late": instance.days_late,
                    "created_at": instance.created_at,
                    "updated_at": instance.updated_at,
                    "cohort_assignment": {
                        "id": cohort_simulation.id,
                        "simulation_id": cohort_simulation.simulation_id,
                        "cohort_id": cohort_simulation.cohort_id,
                        "due_date": cohort_simulation.due_date,
                        "is_required": cohort_simulation.is_required,
                        "simulation": {
                            "id": simulation.id if simulation else None,
                            "title": simulation.title if simulation else "Unknown Simulation",
                            "description": simulation.description if simulation else "No description available",
                            "is_draft": simulation.is_draft if simulation else True,
                            "status": simulation.status if simulation else "draft",
                        } if simulation else None,
                        "cohort": {
                            "id": cohort.id if cohort else None,
                            "title": cohort.title if cohort else "Unknown Cohort",
                            "professor": {
                                "name": professor_name
                            }
                        } if cohort else None
                    }
                })
            except Exception as e:
                logger.error(f"Error processing cohort simulation {cohort_simulation.id}: {str(e)}")
                continue
        
        if not is_production:
            logger.info(f"Returning {len(result)} simulation instances for student {current_user.id}")
        return result
        
    except Exception as e:
        logger.error(f"Error in get_student_simulation_instances: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch simulation instances: {str(e)}")


@router.post("", response_model=StudentSimulationInstanceResponse)
@router.post("/", response_model=StudentSimulationInstanceResponse)
async def create_student_simulation_instance(
    instance_data: StudentSimulationInstanceCreate,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Create a new student simulation instance"""
    
    cohort_assignment = db.query(CohortSimulation).filter(
        CohortSimulation.id == instance_data.cohort_assignment_id
    ).first()
    
    if not cohort_assignment:
        raise HTTPException(status_code=404, detail="Cohort assignment not found")
    
    from database.models import CohortStudent
    enrollment = db.query(CohortStudent).filter(
        CohortStudent.cohort_id == cohort_assignment.cohort_id,
        CohortStudent.student_id == current_user.id,
        CohortStudent.status == "approved"
    ).first()
    
    if not enrollment:
        raise HTTPException(status_code=403, detail="Student not enrolled in this cohort")
    
    existing_instance = db.query(StudentSimulationInstance).filter(
        StudentSimulationInstance.cohort_assignment_id == instance_data.cohort_assignment_id,
        StudentSimulationInstance.student_id == current_user.id
    ).first()
    
    if existing_instance:
        raise HTTPException(status_code=400, detail="Simulation instance already exists")
    
    cohort_assignment = db.query(CohortSimulation).filter(
        CohortSimulation.id == instance_data.cohort_assignment_id
    ).first()
    
    user_progress = UserProgress(
        user_id=current_user.id,
        scenario_id=cohort_assignment.simulation_id,
        simulation_status="not_started"
    )
    db.add(user_progress)
    db.flush()
    
    from utilities.id_generator import generate_unique_simulation_instance_id
    
    instance = StudentSimulationInstance(
        unique_id=generate_unique_simulation_instance_id(db),
        cohort_assignment_id=instance_data.cohort_assignment_id,
        student_id=current_user.id,
        user_progress_id=user_progress.id
    )
    
    db.add(instance)
    db.commit()
    db.refresh(instance)
    
    if not is_production:
        logger.info(f"Created simulation instance {instance.id} for student {current_user.id}")
    return instance


@router.get("/{instance_id}", response_model=StudentSimulationInstanceResponse)
async def get_student_simulation_instance(
    instance_id: str,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Get a specific simulation instance"""
    
    instance = None
    try:
        int_id = int(instance_id)
        instance = _get_published_instance_query(db, current_user.id, int_id).first()
    except ValueError:
        instance = db.query(StudentSimulationInstance).join(
            UserProgress, StudentSimulationInstance.user_progress_id == UserProgress.id
        ).join(
            Scenario, UserProgress.scenario_id == Scenario.id
        ).filter(
            StudentSimulationInstance.unique_id == instance_id,
            StudentSimulationInstance.student_id == current_user.id,
            Scenario.is_draft == False,
            Scenario.status == "active"
        ).first()
    
    if not instance:
        raise HTTPException(
            status_code=404, 
            detail="Simulation instance not found or simulation is not published"
        )
    
    return instance


@router.put("/{instance_id}", response_model=StudentSimulationInstanceResponse)
async def update_student_simulation_instance(
    instance_id: str,
    update_data: StudentSimulationInstanceUpdate,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Update a simulation instance"""
    
    instance = None
    try:
        int_id = int(instance_id)
        instance = _get_published_instance_query(db, current_user.id, int_id).first()
    except ValueError:
        instance = db.query(StudentSimulationInstance).filter(
            StudentSimulationInstance.unique_id == instance_id,
            StudentSimulationInstance.student_id == current_user.id
        ).first()
    
    if not instance:
        raise HTTPException(
            status_code=404, 
            detail="Simulation instance not found or simulation is not published"
        )
    
    for field, value in update_data.dict(exclude_unset=True).items():
        setattr(instance, field, value)
    
    if instance.user_progress_id:
        user_progress = db.query(UserProgress).filter(
            UserProgress.id == instance.user_progress_id
        ).first()
        
        if user_progress:
            if user_progress.completion_percentage is not None:
                instance.completion_percentage = user_progress.completion_percentage
            if user_progress.total_time_spent is not None:
                instance.total_time_spent = user_progress.total_time_spent
            if user_progress.hints_used is not None:
                instance.hints_used = user_progress.hints_used
    
    db.commit()
    db.refresh(instance)
    
    if not is_production:
        logger.info(f"Updated simulation instance {instance_id} for student {current_user.id}")
    return instance


@router.post("/{instance_id}/start", response_model=StudentSimulationInstanceResponse)
async def start_simulation_instance(
    instance_id: int,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Start a simulation instance"""
    
    instance = _get_published_instance_query(db, current_user.id, instance_id).first()
    
    if not instance:
        raise HTTPException(
            status_code=404, 
            detail="Simulation instance not found or simulation is not published"
        )
    
    if instance.status != "not_started":
        raise HTTPException(status_code=400, detail="Simulation instance already started")
    
    instance.status = "in_progress"
    instance.started_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(instance)
    
    if not is_production:
        logger.info(f"Started simulation instance {instance_id} for student {current_user.id}")
    return instance


@router.post("/{instance_id}/start-simulation")
async def start_simulation_for_instance(
    instance_id: str,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """
    Start the actual simulation for a student instance.
    OPTIMIZED: Batch load all scene/persona relationships upfront.
    """
    
    instance = None
    try:
        int_id = int(instance_id)
        instance = db.query(StudentSimulationInstance).filter(
            StudentSimulationInstance.id == int_id,
            StudentSimulationInstance.student_id == current_user.id
        ).first()
        
        if instance and instance.user_progress_id:
            user_progress = db.query(UserProgress).filter(
                UserProgress.id == instance.user_progress_id
            ).first()
            if user_progress:
                scenario = db.query(Scenario).filter(Scenario.id == user_progress.scenario_id).first()
                if scenario and scenario.is_draft:
                    instance = None
    except ValueError:
        instance = db.query(StudentSimulationInstance).filter(
            StudentSimulationInstance.unique_id == instance_id,
            StudentSimulationInstance.student_id == current_user.id
        ).first()
        
        if instance and instance.user_progress_id:
            user_progress = db.query(UserProgress).filter(
                UserProgress.id == instance.user_progress_id
            ).first()
            if user_progress:
                scenario = db.query(Scenario).filter(Scenario.id == user_progress.scenario_id).first()
                if scenario and scenario.is_draft:
                    instance = None
    
    if not instance:
        raise HTTPException(
            status_code=404,
            detail="Simulation instance not found or simulation is not published"
        )
    
    cohort_assignment = db.query(CohortSimulation).filter(
        CohortSimulation.id == instance.cohort_assignment_id
    ).first()
    
    if not cohort_assignment:
        raise HTTPException(status_code=404, detail="Cohort assignment not found")
    
    scenario_id = cohort_assignment.simulation_id
    
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    
    if not is_production:
        logger.info(f"[SCENE_COUNT] Loading scenario {scenario_id}: title='{scenario.title}', is_draft={scenario.is_draft}, status='{scenario.status}'")
    
    user_progress = None
    if instance.user_progress_id:
        user_progress = db.query(UserProgress).filter(
            UserProgress.id == instance.user_progress_id
        ).first()
        
        if user_progress:
            if user_progress.simulation_status in ["waiting_for_begin", "in_progress", "completed"]:
                if not is_production:
                    logger.info(f"Resuming existing simulation for instance {instance_id} with status {user_progress.simulation_status}")
            else:
                if not is_production:
                    logger.info(f"Resetting abandoned simulation for instance {instance_id}")
                
                db.query(SceneProgress).filter(
                    SceneProgress.user_progress_id == user_progress.id
                ).delete()
                db.query(ConversationLog).filter(
                    ConversationLog.user_progress_id == user_progress.id
                ).delete()
                
                user_progress = None
    
    def is_main_character(persona_name, student_role):
        """Check if persona is the main character (student role)"""
        if not student_role:
            return False
        
        import re
        
        student_name = student_role.split('(')[0].strip()
        
        def normalize_name(name):
            normalized = name.strip()
            normalized = re.sub(r'^(Mr\.|Mrs\.|Ms\.|Miss|Dr\.|Prof\.|Professor)\s+', '', normalized, flags=re.IGNORECASE)
            normalized = re.sub(r'[^a-zA-Z]', '', normalized).lower()
            return normalized
        
        return normalize_name(persona_name) == normalize_name(student_name)
    
    if not user_progress:
        first_scene = db.query(ScenarioScene).filter(
            ScenarioScene.scenario_id == scenario_id
        ).order_by(ScenarioScene.scene_order).first()
        
        if not first_scene:
            raise HTTPException(status_code=400, detail="Scenario has no scenes")
        
        # OPTIMIZATION: Batch load all scenes and personas upfront
        all_scenes = db.query(ScenarioScene).filter(
            ScenarioScene.scenario_id == scenario_id
        ).order_by(ScenarioScene.scene_order).all()
        
        all_personas = db.query(ScenarioPersona).filter(
            ScenarioPersona.scenario_id == scenario_id,
            ScenarioPersona.deleted_at.is_(None)
        ).all()
        
        # OPTIMIZATION: Batch load scene_personas relationships ONCE
        scene_ids = [s.id for s in all_scenes]
        scene_personas_map = _batch_load_scene_personas(db, scene_ids)
        
        # Build orchestrator data using preloaded data
        scenario_data = {
            "id": scenario.id,
            "title": scenario.title,
            "description": scenario.description,
            "challenge": scenario.challenge,
            "student_role": scenario.student_role,
            "scenes": [
                {
                    "id": scene.id,
                    "title": scene.title,
                    "description": scene.description,
                    "objectives": [scene.user_goal] if scene.user_goal else ["Complete the scene interaction"],
                    "image_url": scene.image_url,
                    "agent_ids": [
                        p.name.lower().replace(" ", "_") for p in all_personas
                        if not is_main_character(p.name, scenario.student_role)
                    ],
                    "personas_involved": [p.name for p in scene_personas_map.get(scene.id, [])],
                    "max_turns": scene.timeout_turns if scene.timeout_turns is not None else 15,
                    "success_criteria": f"User achieves: {scene.user_goal or 'scene completion'}"
                }
                for scene in all_scenes
            ],
            "personas": [
                {
                    "id": persona.name.lower().replace(" ", "_"),
                    "db_id": persona.id,
                    "identity": {
                        "name": persona.name,
                        "role": persona.role,
                        "bio": persona.background or "Professional team member"
                    },
                    "personality": {
                        "goals": persona.primary_goals or ["Support team objectives"],
                        "traits": persona.personality_traits or "Professional and collaborative"
                    },
                    "system_prompt": persona.system_prompt,
                    "image_url": persona.image_url
                }
                for persona in all_personas
                if not is_main_character(persona.name, scenario.student_role)
            ]
        }
        
        user_progress = UserProgress(
            user_id=current_user.id,
            scenario_id=scenario_id,
            current_scene_id=first_scene.id,
            simulation_status="waiting_for_begin",
            session_count=1,
            scenes_completed=[],
            orchestrator_data=scenario_data,
            started_at=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc)
        )
        db.add(user_progress)
        db.flush()
        
        scene_progress = SceneProgress(
            user_progress_id=user_progress.id,
            scene_id=first_scene.id,
            status="in_progress",
            started_at=datetime.now(timezone.utc)
        )
        db.add(scene_progress)
        
        welcome_text = f"""🎯 **{scenario.title}**

{scenario.description}

**Your Role:** {scenario.student_role}

**Current Scene:** {first_scene.title}

**Instructions:**
• Type **"begin"** to start the simulation
• Type **"help"** for available commands
• Use natural conversation to interact with personas"""
        
        welcome_log = ConversationLog(
            user_progress_id=user_progress.id,
            scene_id=first_scene.id,
            message_type="system",
            sender_name="System",
            message_content=welcome_text,
            message_order=1,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(welcome_log)
        if not is_production:
            logger.info(f"[START_SIMULATION] Saved initial welcome message for user_progress {user_progress.id}")
        
        instance.user_progress_id = user_progress.id
    
    if instance.status == "not_started":
        instance.status = "in_progress"
        instance.started_at = datetime.now(timezone.utc)
        instance.attempts_count += 1
        db.commit()
        db.refresh(instance)
        db.refresh(user_progress)
        if not is_production:
            logger.info(f"[START] Started instance {instance.id} for student {current_user.id}")
    elif instance.status in ["completed", "graded", "submitted"]:
        if not is_production:
            logger.info(f"[REVIEW] Loading completed instance {instance.id} with status {instance.status}")
    else:
        if not is_production:
            logger.info(f"[RESUME] Resuming in-progress instance {instance.id}")
        if not instance.started_at:
            instance.started_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(instance)
        db.refresh(user_progress)
    
    current_scene = db.query(ScenarioScene).filter(
        ScenarioScene.id == user_progress.current_scene_id
    ).first()
    
    if not current_scene:
        raise HTTPException(status_code=404, detail="Current scene not found")
    
    # OPTIMIZATION: Batch load all scenes and personas upfront (single query)
    all_scenes = db.query(ScenarioScene).filter(
        ScenarioScene.scenario_id == scenario_id
    ).order_by(ScenarioScene.scene_order).all()
    
    all_personas = db.query(ScenarioPersona).filter(
        ScenarioPersona.scenario_id == scenario_id,
        ScenarioPersona.deleted_at.is_(None)
    ).all()
    
    # OPTIMIZATION: Batch load scene_personas relationships ONCE instead of per scene
    scene_ids = [s.id for s in all_scenes]
    scene_personas_map = _batch_load_scene_personas(db, scene_ids)
    
    # Get total scenes count
    total_scenes = len(all_scenes)
    if not is_production:
        logger.info(f"[SCENE_COUNT] Scenario {scenario_id} has {total_scenes} total scenes")
    
    # Get conversation history
    conversation_logs = db.query(ConversationLog).filter(
        ConversationLog.user_progress_id == user_progress.id
    ).order_by(ConversationLog.message_order, ConversationLog.timestamp).all()
    
    # OPTIMIZATION: Batch load all personas used in conversation logs
    messages_history = []
    persona_ids = [log.persona_id for log in conversation_logs if log.persona_id]
    persona_map = {}
    if persona_ids:
        personas = db.query(ScenarioPersona).filter(ScenarioPersona.id.in_(persona_ids)).all()
        persona_map = {p.id: p for p in personas}
    
    for log in conversation_logs:
        sender_name = log.sender_name or ("User" if log.message_type == "user" else "System")
        if sender_name == "User":
            sender_name = "You"
        
        persona_name = None
        persona_role = None
        if log.persona_id and log.persona_id in persona_map:
            persona = persona_map[log.persona_id]
            persona_name = persona.name
            persona_role = persona.role
        elif log.message_type == "ai_persona" and log.sender_name:
            persona_name = log.sender_name
        
        message_dict = {
            "id": log.id,
            "sender": sender_name,
            "text": log.message_content,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            "type": log.message_type,
            "persona_id": log.persona_id,
            "scene_id": log.scene_id,
            "persona_name": persona_name,
            "persona_role": persona_role
        }
        messages_history.append(message_dict)
    
    turn_count = 0
    if user_progress.orchestrator_data and 'state' in user_progress.orchestrator_data:
        turn_count = user_progress.orchestrator_data['state'].get('turn_count', 0)
    
    # OPTIMIZATION: Batch load all completed scenes
    completed_scene_ids = []
    scene_progresses = db.query(SceneProgress).filter(
        SceneProgress.user_progress_id == user_progress.id,
        SceneProgress.status == "completed"
    ).all()
    completed_scene_ids = [sp.scene_id for sp in scene_progresses]
    
    # Build scenes with personas using preloaded data
    scenes_with_personas = []
    for scene in all_scenes:
        scenes_with_personas.append({
            "id": scene.id,
            "title": scene.title,
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
                    "image_url": p.image_url
                }
                for p in scene_personas_map.get(scene.id, [])
                if not is_main_character(p.name, scenario.student_role)
            ]
        })
    
    case_study_url = getattr(scenario, 'case_study_url', None)
    if case_study_url:
        debug_log(f"[SIMULATION_INSTANCE] Found case study PDF: {case_study_url}")
    
    # Get personas for current scene using preloaded map
    involved_personas = scene_personas_map.get(current_scene.id, [])
    
    response_data = {
        "user_progress_id": user_progress.id,
        "scenario": {
            "id": scenario.id,
            "title": scenario.title,
            "description": scenario.description,
            "challenge": scenario.challenge,
            "industry": scenario.industry,
            "learning_objectives": scenario.learning_objectives if isinstance(scenario.learning_objectives, list) else [scenario.learning_objectives] if scenario.learning_objectives else [],
            "student_role": scenario.student_role,
            "total_scenes": total_scenes,
            "case_study_url": case_study_url
        },
        "current_scene": {
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
                    "image_url": p.image_url
                }
                for p in involved_personas
                if not is_main_character(p.name, scenario.student_role)
            ]
        },
        "all_scenes": scenes_with_personas,
        "simulation_status": instance.status if instance.status in ["completed", "graded", "submitted"] else user_progress.simulation_status,
        "instance_status": instance.status,
        "user_progress_status": user_progress.simulation_status,
        "instance_id": instance.id,
        "conversation_history": messages_history,
        "is_resuming": len(messages_history) > 0,
        "turn_count": turn_count,
        "completed_scene_ids": completed_scene_ids
    }
    
    return response_data


@router.post("/{instance_id}/complete", response_model=StudentSimulationInstanceResponse)
async def complete_simulation_instance(
    instance_id: int,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Complete a simulation instance"""
    
    instance = _get_published_instance_query(db, current_user.id, instance_id).first()
    
    if not instance:
        raise HTTPException(
            status_code=404, 
            detail="Simulation instance not found or simulation is not published"
        )
    
    if instance.status != "in_progress":
        raise HTTPException(status_code=400, detail="Simulation instance not in progress")
    
    now = datetime.now(timezone.utc)
    instance.status = "completed"
    instance.completed_at = now
    instance.completion_percentage = 100.0

    if instance.user_progress_id:
        user_progress = db.query(UserProgress).filter(UserProgress.id == instance.user_progress_id).first()
        if user_progress:
            user_progress.simulation_status = "completed"
            user_progress.last_activity = now
            try:
                sp = db.query(SceneProgress).filter(
                    SceneProgress.user_progress_id == user_progress.id,
                    SceneProgress.scene_id == user_progress.current_scene_id
                ).first()
                if sp and sp.status != "completed":
                    sp.status = "completed"
                    sp.completed_at = now
            except Exception:
                pass
    
    db.commit()
    db.refresh(instance)
    
    if not is_production:
        logger.info(f"Completed simulation instance {instance_id} for student {current_user.id}")
    return instance


@router.get("/assignment/{assignment_id}/instances")
async def get_simulation_assignment_instances(
    assignment_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get all student instances for a specific simulation assignment (professor view)"""
    try:
        if not is_production:
            logger.info(f"GET request: assignment_id={assignment_id}, user_id={current_user.id}")
        
        assignment = db.query(CohortSimulation).filter(
            CohortSimulation.id == assignment_id
        ).first()
        
        if not assignment:
            logger.warning(f"Assignment {assignment_id} not found")
            raise HTTPException(status_code=404, detail="Simulation assignment not found")
        
        cohort = db.query(Cohort).filter(
            Cohort.id == assignment.cohort_id,
            Cohort.created_by == current_user.id
        ).first()
        
        if not cohort:
            logger.warning(f"User {current_user.id} not authorized for cohort {assignment.cohort_id}")
            raise HTTPException(status_code=403, detail="Not authorized to view this data")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_simulation_assignment_instances (initial checks): {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch student instances: {str(e)}")
    
    try:
        from database.models import CohortStudent
        
        # OPTIMIZATION: Batch load all cohort students with user data
        cohort_students = db.query(CohortStudent, User).join(
            User, CohortStudent.student_id == User.id
        ).filter(
            CohortStudent.cohort_id == assignment.cohort_id,
            CohortStudent.status == "approved"
        ).all()
        
        if not is_production:
            logger.info(f"Found {len(cohort_students)} approved students in cohort {assignment.cohort_id}")
        
        # OPTIMIZATION: Batch load all instances for this assignment
        student_ids = [cs.CohortStudent.student_id for cs in cohort_students]
        existing_instances = db.query(StudentSimulationInstance).filter(
            StudentSimulationInstance.cohort_assignment_id == assignment_id,
            StudentSimulationInstance.student_id.in_(student_ids)
        ).all()
        
        instance_map = {instance.student_id: instance for instance in existing_instances}
        
        if not is_production:
            logger.info(f"Found {len(existing_instances)} existing instances for assignment {assignment_id}")
        
        # OPTIMIZATION: Batch load all user_progress records
        user_progress_ids = [inst.user_progress_id for inst in existing_instances if inst.user_progress_id]
        user_progress_map = {}
        if user_progress_ids:
            user_progresses = db.query(UserProgress).filter(
                UserProgress.id.in_(user_progress_ids)
            ).all()
            user_progress_map = {up.id: up for up in user_progresses}
        
        # OPTIMIZATION: Batch load all scenarios
        scenario_ids = [up.scenario_id for up in user_progress_map.values() if up.scenario_id]
        scenario_map = {}
        if scenario_ids:
            scenarios = db.query(Scenario).filter(Scenario.id.in_(scenario_ids)).all()
            scenario_map = {s.id: s for s in scenarios}
        
        # OPTIMIZATION: Batch load scene counts
        scene_count_map = {}
        if scenario_ids:
            scene_counts = db.query(
                ScenarioScene.scenario_id,
                func.count(ScenarioScene.id).label('count')
            ).filter(
                ScenarioScene.scenario_id.in_(scenario_ids)
            ).group_by(ScenarioScene.scenario_id).all()
            scene_count_map = {scenario_id: count for scenario_id, count in scene_counts}
        
        # OPTIMIZATION: Batch load completed scene progress
        completed_scene_count_map = {}
        if user_progress_ids:
            completed_counts = db.query(
                SceneProgress.user_progress_id,
                func.count(SceneProgress.id).label('count')
            ).filter(
                SceneProgress.user_progress_id.in_(user_progress_ids),
                SceneProgress.status == "completed"
            ).group_by(SceneProgress.user_progress_id).all()
            completed_scene_count_map = {up_id: count for up_id, count in completed_counts}
        
        result = []
        for cohort_student, student in cohort_students:
            instance = instance_map.get(student.id)
            
            if not instance:
                result.append({
                    "id": None,
                    "cohort_assignment_id": assignment_id,
                    "student_id": student.id,
                    "student_name": student.full_name,
                    "student_email": student.email,
                    "user_progress_id": None,
                    "status": "not_started",
                    "started_at": None,
                    "completed_at": None,
                    "submitted_at": None,
                    "grade": None,
                    "feedback": None,
                    "graded_by": None,
                    "graded_at": None,
                    "completion_percentage": 0.0,
                    "total_time_spent": 0,
                    "attempts_count": 0,
                    "hints_used": 0,
                    "is_overdue": False,
                    "days_late": 0,
                    "created_at": None,
                    "updated_at": None
                })
                continue
            
            completion_percentage = instance.completion_percentage or 0.0
            total_time_spent = instance.total_time_spent or 0

            try:
                user_progress = user_progress_map.get(instance.user_progress_id) if instance.user_progress_id else None
                
                if user_progress:
                    if (user_progress.simulation_status in ["completed", "graded"] or 
                        instance.status in ["completed", "graded", "submitted"]):
                        completion_percentage = 100.0
                        if instance.completion_percentage != 100.0:
                            instance.completion_percentage = 100.0
                            db.commit()
                    else:
                        scenario = scenario_map.get(user_progress.scenario_id) if user_progress.scenario_id else None
                        
                        if scenario:
                            total_scenes = scene_count_map.get(scenario.id, 0)
                            completed_scenes = completed_scene_count_map.get(user_progress.id, 0)
                            
                            if total_scenes > 0:
                                completion_percentage = (completed_scenes / total_scenes) * 100
                                if abs(completion_percentage - (instance.completion_percentage or 0)) > 0.01:
                                    instance.completion_percentage = completion_percentage
                                    db.commit()
                    
                    try:
                        start_dt = instance.started_at or user_progress.created_at
                        end_dt = instance.completed_at or user_progress.last_activity or user_progress.updated_at or datetime.now(timezone.utc)
                        if start_dt:
                            if start_dt.tzinfo is None:
                                start_dt = start_dt.replace(tzinfo=timezone.utc)
                            if end_dt and end_dt.tzinfo is None:
                                end_dt = end_dt.replace(tzinfo=timezone.utc)
                            if end_dt:
                                time_delta = end_dt - start_dt
                                total_time_spent = max(0, int(time_delta.total_seconds()))
                                if abs(total_time_spent - (instance.total_time_spent or 0)) > 1:
                                    instance.total_time_spent = total_time_spent
                                    db.commit()
                    except Exception as e:
                        logger.warning(f"Could not calculate time spent for instance {instance.id}: {e}")
            except Exception as e:
                logger.error(f"Error processing instance {instance.id}: {e}")
                completion_percentage = instance.completion_percentage or 0.0
                total_time_spent = instance.total_time_spent or 0
            
            result.append({
                "id": instance.id,
                "cohort_assignment_id": instance.cohort_assignment_id,
                "student_id": instance.student_id,
                "student_name": student.full_name,
                "student_email": student.email,
                "user_progress_id": instance.user_progress_id,
                "status": instance.status,
                "started_at": instance.started_at,
                "completed_at": instance.completed_at,
                "submitted_at": instance.submitted_at,
                "grade": instance.grade,
                "feedback": instance.feedback,
                "graded_by": instance.graded_by,
                "graded_at": instance.graded_at,
                "completion_percentage": completion_percentage,
                "total_time_spent": total_time_spent,
                "attempts_count": instance.attempts_count,
                "hints_used": instance.hints_used,
                "is_overdue": instance.is_overdue,
                "days_late": instance.days_late,
                "created_at": instance.created_at,
                "updated_at": instance.updated_at
            })
        
        if not is_production:
            logger.info(f"Successfully retrieved {len(result)} student instances for assignment {assignment_id}")
        return result
        
    except Exception as e:
        logger.error(f"Error fetching student instances for assignment {assignment_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch student instances: {str(e)}")


@router.get("/cohort/{cohort_id}/instances", response_model=List[StudentSimulationInstanceResponse])
async def get_cohort_simulation_instances(
    cohort_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get all simulation instances for a cohort (professor view)"""
    
    cohort = db.query(Cohort).filter(
        Cohort.id == cohort_id,
        Cohort.created_by == current_user.id
    ).first()
    
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    instances = db.query(StudentSimulationInstance).join(
        CohortSimulation,
        StudentSimulationInstance.cohort_assignment_id == CohortSimulation.id
    ).filter(
        CohortSimulation.cohort_id == cohort_id
    ).all()
    
    return instances


@router.post("/{instance_id}/grade", response_model=StudentSimulationInstanceResponse)
async def grade_simulation_instance(
    instance_id: int,
    grade_data: dict,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Grade a student simulation instance (professor only)"""
    
    instance = db.query(StudentSimulationInstance).filter(
        StudentSimulationInstance.id == instance_id
    ).first()
    
    if not instance:
        raise HTTPException(status_code=404, detail="Simulation instance not found")
    
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
        raise HTTPException(status_code=403, detail="Not authorized to grade this simulation")
    
    now = datetime.now(timezone.utc)
    instance.grade = grade_data.get("grade")
    instance.feedback = grade_data.get("feedback")
    instance.graded_by = current_user.id
    instance.graded_at = now
    instance.status = "graded"
    
    db.commit()
    db.refresh(instance)
    
    if not is_production:
        logger.info(f"Graded simulation instance {instance_id} with grade {instance.grade}")
    return instance


@router.get("/cohort/{cohort_id}/grading-summary")
async def get_cohort_grading_summary(
    cohort_id: int,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get grading summary for a cohort"""
    
    cohort = db.query(Cohort).filter(
        Cohort.id == cohort_id,
        Cohort.created_by == current_user.id
    ).first()
    
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    # OPTIMIZATION: Batch load all instances for the cohort
    instances = db.query(StudentSimulationInstance).join(
        CohortSimulation
    ).filter(
        CohortSimulation.cohort_id == cohort_id
    ).all()
    
    total_instances = len(instances)
    graded_instances = len([i for i in instances if i.grade is not None])
    pending_instances = total_instances - graded_instances
    
    graded_grades = [i.grade for i in instances if i.grade is not None]
    average_grade = sum(graded_grades) / len(graded_grades) if graded_grades else 0
    
    return {
        "total_instances": total_instances,
        "graded_instances": graded_instances,
        "pending_instances": pending_instances,
        "average_grade": round(average_grade, 2),
        "completion_rate": round((graded_instances / total_instances * 100) if total_instances > 0 else 0, 2)
    }