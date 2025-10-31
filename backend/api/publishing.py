"""
Publishing API endpoints for PDF-to-Scenario functionality
Handles scenario publishing, marketplace browsing, cloning, and reviews
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import and_, or_, desc, func
from typing import List, Optional
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import time
import secrets

from database.connection import get_db
from utilities.rate_limiter import check_anonymous_review_rate_limit
from utilities.auth import get_current_user, get_current_user_optional
from utilities.debug_logging import debug_log
from database.models import (
    Scenario, ScenarioPersona, ScenarioScene, ScenarioFile, 
    ScenarioReview, User, scene_personas, UserProgress,
    ConversationLog, SceneProgress
)
from database.schemas import (
    ScenarioPublishingResponse, ScenarioPublishRequest, MarketplaceFilters,
    MarketplaceResponse, ScenarioReviewCreate, ScenarioReviewResponse,
    AIProcessingResult, ScenarioPersonaResponse, ScenarioSceneResponse
)

router = APIRouter(prefix="/api/publishing/scenarios", tags=["Publishing"])

# Performance optimization constants
DB_EXECUTOR = ThreadPoolExecutor(max_workers=4)
BATCH_SIZE = 100  # For bulk database operations

# --- SCENARIO PUBLISHING ENDPOINTS ---

@router.get("/", response_model=List[ScenarioPublishingResponse])
async def get_scenarios(
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None, description="Filter by status: draft, active, archived"),
    include_drafts: Optional[bool] = Query(False, description="Include draft scenarios (for testing)"),
    current_user: User = Depends(get_current_user)
):
    """Get scenarios with optional filtering by status"""
    try:
        # Start with base query - exclude soft-deleted scenarios and filter by current user
        query = db.query(Scenario).filter(
            Scenario.deleted_at.is_(None),
            Scenario.created_by == current_user.id
        )
        
        # Filter by status if provided
        if status:
            if status == "active":
                # For active scenarios, show only non-draft scenarios
                query = query.filter(Scenario.is_draft == False)
            elif status == "draft":
                # For draft scenarios, show only draft scenarios
                query = query.filter(Scenario.is_draft == True)
            elif status == "archived":
                # For archived scenarios, show scenarios with archived status
                query = query.filter(Scenario.status == "archived")
        
        # If no status filter provided, show only active (non-draft) scenarios by default
        # This prevents showing both draft and active versions of the same scenario
        # Exception: if include_drafts=True, show all scenarios regardless of draft status
        if not status and not include_drafts:
            query = query.filter(Scenario.is_draft == False)
        
        scenarios = query.all()
        debug_log(f"Found {len(scenarios)} scenarios with status filter: {status}")
        
        # Convert to response format with personas and scenes
        scenario_responses = []
        for scenario in scenarios:
            # Get personas for this scenario (excluding soft-deleted)
            personas = db.query(ScenarioPersona).filter(
                ScenarioPersona.scenario_id == scenario.id,
                ScenarioPersona.deleted_at.is_(None)
            ).all()
            
            # Get scenes for this scenario
            scenes = db.query(ScenarioScene).filter(
                ScenarioScene.scenario_id == scenario.id
            ).order_by(ScenarioScene.scene_order).all()
            
            # Fix learning_objectives if it's a string (convert to list)
            learning_objectives = scenario.learning_objectives or []
            if isinstance(learning_objectives, str):
                learning_objectives = [item.strip() for item in learning_objectives.split('\n') if item.strip()]
            
            scenario_responses.append({
                "id": scenario.id,
                "title": scenario.title or "",
                "description": scenario.description or "",
                "challenge": scenario.challenge or "",
                "industry": scenario.industry or "Business",
                "learning_objectives": learning_objectives,
                "student_role": scenario.student_role or "Business Analyst",
                "category": scenario.category,
                "difficulty_level": scenario.difficulty_level,
                "estimated_duration": scenario.estimated_duration,
                "tags": scenario.tags,
                "pdf_title": scenario.pdf_title,
                "pdf_source": scenario.pdf_source,
                "processing_version": scenario.processing_version,
                "rating_avg": scenario.rating_avg,
                "rating_count": scenario.rating_count,
                "source_type": scenario.source_type,
                "is_public": scenario.is_public,
                "is_template": scenario.is_template,
                "allow_remixes": scenario.allow_remixes,
                "usage_count": scenario.usage_count,
                "clone_count": scenario.clone_count,
                "created_by": scenario.created_by,
                "created_at": scenario.created_at,
                "updated_at": scenario.updated_at,
                "status": scenario.status,
                "is_draft": scenario.is_draft,
                "personas": [
                    {
                        "id": persona.id,
                        "name": persona.name,
                        "role": persona.role,
                        "background": persona.background,
                        "correlation": persona.correlation,
                        "primary_goals": persona.primary_goals or [],
                        "personality_traits": persona.personality_traits or {},
                        "system_prompt": persona.system_prompt,
                        "image_url": persona.image_url
                    }
                    for persona in personas
                ],
                "scenes": [
                    {
                        "id": scene.id,
                        "title": scene.title,
                        "description": scene.description,
                        "user_goal": scene.user_goal,
                        "scene_order": scene.scene_order,
                        "estimated_duration": scene.estimated_duration,
                        "image_url": scene.image_url,
                        "timeout_turns": scene.timeout_turns,
                        "success_metric": scene.success_metric
                    }
                    for scene in scenes
                ],
                "completion_status": scenario.completion_status or {},
                "name_completed": scenario.name_completed,
                "description_completed": scenario.description_completed,
                "student_role_completed": scenario.student_role_completed,
                "personas_completed": scenario.personas_completed,
                "scenes_completed": scenario.scenes_completed,
                "images_completed": scenario.images_completed,
                "learning_outcomes_completed": scenario.learning_outcomes_completed,
                "ai_enhancement_completed": scenario.ai_enhancement_completed
            })
        
        return scenario_responses
        
    except Exception as e:
        debug_log(f"Error fetching scenarios: {e}")
        import traceback
        debug_log(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch scenarios: {str(e)}")

@router.get("/drafts/", response_model=List[ScenarioPublishingResponse])
async def get_draft_scenarios(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get draft scenarios only"""
    try:
        # Get only draft scenarios created by the current user - exclude soft-deleted ones
        scenarios = db.query(Scenario).filter(
            Scenario.is_draft == True,
            Scenario.deleted_at.is_(None),
            Scenario.created_by == current_user.id
        ).all()
        debug_log(f"Found {len(scenarios)} draft scenarios")
        
        # Convert to response format - simplified
        scenario_responses = []
        for scenario in scenarios:
            # Fix learning_objectives if it's a string (convert to list)
            learning_objectives = scenario.learning_objectives or []
            if isinstance(learning_objectives, str):
                learning_objectives = [item.strip() for item in learning_objectives.split('\n') if item.strip()]
            
            scenario_responses.append({
                "id": scenario.id,
                "title": scenario.title or "",
                "description": scenario.description or "",
                "challenge": scenario.challenge or "",
                "industry": scenario.industry or "Business",
                "learning_objectives": learning_objectives,
                "student_role": scenario.student_role or "Business Analyst",
                "category": scenario.category,
                "difficulty_level": scenario.difficulty_level,
                "estimated_duration": scenario.estimated_duration,
                "tags": scenario.tags,
                "pdf_title": scenario.pdf_title,
                "pdf_source": scenario.pdf_source,
                "processing_version": scenario.processing_version,
                "rating_avg": scenario.rating_avg,
                "rating_count": scenario.rating_count,
                "source_type": scenario.source_type,
                "is_public": scenario.is_public,
                "is_template": scenario.is_template,
                "allow_remixes": scenario.allow_remixes,
                "usage_count": scenario.usage_count,
                "clone_count": scenario.clone_count,
                "created_by": scenario.created_by,
                "created_at": scenario.created_at,
                "updated_at": scenario.updated_at,
                "personas": [],
                "scenes": [],
                "completion_status": scenario.completion_status or {},
                "name_completed": scenario.name_completed,
                "description_completed": scenario.description_completed,
                "student_role_completed": scenario.student_role_completed,
                "personas_completed": scenario.personas_completed,
                "scenes_completed": scenario.scenes_completed,
                "images_completed": scenario.images_completed,
                "learning_outcomes_completed": scenario.learning_outcomes_completed,
                "ai_enhancement_completed": scenario.ai_enhancement_completed
            })
        
        return scenario_responses
        
    except Exception as e:
        debug_log(f"Error fetching draft scenarios: {e}")
        import traceback
        debug_log(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch draft scenarios: {str(e)}")

@router.post("/save")
async def save_scenario_draft(
    request: Request,
    scenario_id: Optional[int] = Query(None, description="Scenario ID for updates (requires authentication)"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Save AI processing results as a draft scenario
    Called when user clicks "Save" button
    
    Security: 
    - If scenario_id is provided, requires authentication and ownership verification
    - If no scenario_id, creates a new scenario (create-only behavior)
    - No longer allows title-based lookups for security
    """
    
    try:
        # Parse JSON from request body
        ai_result = await request.json()
        
        debug_log("Saving scenario as draft...")
        debug_log(f"AI result keys: {list(ai_result.keys())}")
        debug_log(f"Scenario ID: {scenario_id}")
        debug_log(f"Current user: {current_user.id if current_user else 'None'}")
        debug_log(f"Scenario ID type: {type(scenario_id)}")
        debug_log(f"Scenario ID is None: {scenario_id is None}")
        
        # Check if we received the wrapper response instead of direct AI result
        if "ai_result" in ai_result and isinstance(ai_result["ai_result"], dict):
            debug_log("Detected wrapper response, extracting ai_result...")
            actual_ai_result = ai_result["ai_result"]
        else:
            actual_ai_result = ai_result
        
        debug_log(f"Actual AI result keys: {list(actual_ai_result.keys())}")
        debug_log(f"Key figures count: {len(actual_ai_result.get('key_figures', []))}")
        debug_log(f"Scenes count: {len(actual_ai_result.get('scenes', []))}")
        
        # Extract title from AI result
        title = actual_ai_result.get("title", "Untitled Scenario")
        debug_log(f"Extracted title: {title}")
        
        scenario = None
        
        # Handle update case: scenario_id provided
        if scenario_id is not None:
            if not current_user:
                raise HTTPException(
                    status_code=401,
                    detail="Authentication required to update existing scenarios"
                )
            
            # Find scenario and verify ownership
            scenario = db.query(Scenario).filter_by(id=scenario_id).first()
            if not scenario:
                raise HTTPException(
                    status_code=404,
                    detail=f"Scenario with ID {scenario_id} not found"
                )
            
            # Verify ownership
            if scenario.created_by != current_user.id:
                raise HTTPException(
                    status_code=403,
                    detail="You can only update scenarios you created"
                )
            
            debug_log(f"Updating existing scenario with ID: {scenario.id}")
            scenario.title = title
            scenario.description = actual_ai_result.get("description", "")
            scenario.challenge = actual_ai_result.get("description", "")
            scenario.learning_objectives = actual_ai_result.get("learning_outcomes", [])
            scenario.student_role = actual_ai_result.get("student_role", "Business Analyst")
            scenario.completion_status = actual_ai_result.get("completion_status", {})
            scenario.grading_config = actual_ai_result.get("grading_config", {})
            
            # Update rubric fields
            scenario.rubric_title = actual_ai_result.get("rubric_title")
            scenario.rubric_criteria = actual_ai_result.get("rubric_criteria")
            scenario.rubric_performance_levels = actual_ai_result.get("rubric_performance_levels")
            scenario.grading_prompt = actual_ai_result.get("grading_prompt")
            
            # Preserve the current status when saving (don't force to draft)
            # Only set to draft if it's a brand new scenario (no existing status)
            if not scenario.status or scenario.status == "":
                scenario.status = "draft"
                scenario.is_draft = True
                scenario.is_public = False
                debug_log(f"Setting new scenario status to draft")
            else:
                debug_log(f"Preserving existing status: {scenario.status}")
            
            # Set completion boolean fields - only set to true if all sections are complete
            completion_status = actual_ai_result.get("completion_status", {})
            
            # Set individual completion fields based on their actual completion state
            scenario.name_completed = completion_status.get("name_completed", False)
            scenario.description_completed = completion_status.get("description_completed", False)
            scenario.student_role_completed = completion_status.get("student_role_completed", False)
            scenario.personas_completed = completion_status.get("personas_completed", False)
            scenario.scenes_completed = completion_status.get("scenes_completed", False)
            scenario.images_completed = completion_status.get("images_completed", False)
            scenario.learning_outcomes_completed = completion_status.get("learning_outcomes_completed", False)
            scenario.ai_enhancement_completed = completion_status.get("ai_enhancement_completed", False)
            scenario.grading_config_completed = completion_status.get("grading_config_completed", False)
            
            scenario.updated_at = datetime.utcnow()
            db.flush()
            # Store existing scene and persona IDs for cleanup
            existing_scene_ids = [id for (id,) in db.query(ScenarioScene.id).filter(ScenarioScene.scenario_id == scenario.id).all()]
            existing_persona_ids = [id for (id,) in db.query(ScenarioPersona.id).filter(
                ScenarioPersona.scenario_id == scenario.id,
                ScenarioPersona.deleted_at.is_(None)
            ).all()]
            debug_log(f"Found {len(existing_scene_ids)} existing scenes and {len(existing_persona_ids)} existing personas to potentially clean up")
        
        # Handle create case: no scenario_id provided
        else:
            # ALWAYS check for existing scenarios first to prevent duplicates
            # This is a safety net in case the frontend doesn't pass scenario_id
            existing_scenario = None
            
            if current_user:
                # For authenticated users, check for scenarios with same title by same user
                existing_scenario = db.query(Scenario).filter(
                    Scenario.title == title,
                    Scenario.created_by == current_user.id,
                    Scenario.deleted_at.is_(None)
                ).order_by(Scenario.updated_at.desc()).first()  # Get most recent
                debug_log(f"Checking for existing scenario for user {current_user.id} with title '{title}'")
            else:
                # For unauthenticated users, check for scenarios with same title and no user
                existing_scenario = db.query(Scenario).filter(
                    Scenario.title == title,
                    Scenario.created_by.is_(None),
                    Scenario.deleted_at.is_(None)
                ).order_by(Scenario.updated_at.desc()).first()  # Get most recent
                debug_log(f"Checking for existing scenario (no user) with title '{title}'")
            
            if existing_scenario:
                debug_log(f"DUPLICATE PREVENTION: Found existing scenario ID {existing_scenario.id}, updating instead of creating new one")
                # Update the existing scenario instead of creating a new one
                existing_scenario.description = actual_ai_result.get("description", "")
                existing_scenario.challenge = actual_ai_result.get("description", "")
                existing_scenario.learning_objectives = actual_ai_result.get("learning_outcomes", [])
                existing_scenario.student_role = actual_ai_result.get("student_role", "Business Analyst")
                existing_scenario.completion_status = actual_ai_result.get("completion_status", {})
                existing_scenario.grading_config = actual_ai_result.get("grading_config", {})
                existing_scenario.rubric_title = actual_ai_result.get("rubric_title")
                existing_scenario.rubric_criteria = actual_ai_result.get("rubric_criteria")
                existing_scenario.rubric_performance_levels = actual_ai_result.get("rubric_performance_levels")
                existing_scenario.updated_at = datetime.utcnow()
                scenario = existing_scenario
                debug_log(f"Updated existing scenario {scenario.id} instead of creating duplicate")
            else:
                debug_log(f"No existing scenario found, creating new one with title '{title}'")
                # Generate unique ID for new scenario
                unique_id = f"SC-{secrets.token_urlsafe(8).upper()}"
                debug_log(f"Generated unique_id: {unique_id}")
                
                # Create scenario record as draft
                scenario = Scenario(
                    unique_id=unique_id,
                    title=title,
                    description=actual_ai_result.get("description", ""),
                    challenge=actual_ai_result.get("description", ""),
                    industry="Business",
                    learning_objectives=actual_ai_result.get("learning_outcomes", []),
                    student_role=actual_ai_result.get("student_role", "Business Analyst"),
                    source_type="pdf_upload",
                    pdf_title=title,
                    pdf_source="Uploaded PDF",
                    processing_version="1.0",
                    is_public=False,  # Draft - not public
                    allow_remixes=True,
                    status="draft",  # Set status to draft when creating
                    is_draft=True,  # Mark as draft
                    published_version_id=None,  # No published version yet
                    draft_of_id=None,  # This is the original draft
                    created_by=current_user.id if current_user else None,
                    completion_status=actual_ai_result.get("completion_status", {}),
                    grading_config=actual_ai_result.get("grading_config", {}),
                    rubric_title=actual_ai_result.get("rubric_title"),
                    rubric_criteria=actual_ai_result.get("rubric_criteria"),
                    rubric_performance_levels=actual_ai_result.get("rubric_performance_levels"),
                    grading_prompt=actual_ai_result.get("grading_prompt"),
                    name_completed=False,  # Will be set after creation
                    description_completed=False,
                    student_role_completed=False,
                    personas_completed=False,
                    scenes_completed=False,
                    images_completed=False,
                    learning_outcomes_completed=False,
                    ai_enhancement_completed=False,
                    grading_config_completed=False,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                try:
                    db.add(scenario)
                    db.flush()
                except Exception as e:
                    if "unique_title_per_user_active" in str(e) or "unique_title_per_user" in str(e):
                        debug_log(f"Unique constraint violation - scenario with same title already exists, updating instead")
                        # Rollback the failed transaction first
                        db.rollback()
                        # Find the existing scenario and update it
                        existing_scenario = db.query(Scenario).filter(
                            Scenario.title == title,
                            Scenario.created_by == current_user.id if current_user else None,
                            Scenario.deleted_at.is_(None)
                        ).first()
                        if existing_scenario:
                            # Update the existing scenario with new data
                            existing_scenario.description = actual_ai_result.get("description", "")
                            existing_scenario.challenge = actual_ai_result.get("description", "")
                            existing_scenario.learning_objectives = actual_ai_result.get("learning_outcomes", [])
                            existing_scenario.student_role = actual_ai_result.get("student_role", "Business Analyst")
                            existing_scenario.completion_status = actual_ai_result.get("completion_status", {})
                            existing_scenario.grading_config = actual_ai_result.get("grading_config", {})
                            existing_scenario.rubric_title = actual_ai_result.get("rubric_title")
                            existing_scenario.rubric_criteria = actual_ai_result.get("rubric_criteria")
                            existing_scenario.rubric_performance_levels = actual_ai_result.get("rubric_performance_levels")
                            existing_scenario.updated_at = datetime.utcnow()
                            scenario = existing_scenario
                            debug_log(f"Updated existing scenario {scenario.id} due to unique constraint violation")
                        else:
                            # If no existing scenario found, try with a timestamp-based unique title
                            debug_log(f"No existing scenario found, creating with unique timestamp")
                            import time
                            timestamp = int(time.time())
                            unique_title = f"{title} ({timestamp})"
                            scenario.title = unique_title
                            db.add(scenario)
                            db.flush()
                            debug_log(f"Created new scenario with unique title: {unique_title}")
                    else:
                        raise e
            
            # Set completion boolean fields based on individual completion state
            completion_status_for_db = actual_ai_result.get("completion_status", {})
            
            scenario.name_completed = completion_status_for_db.get("name_completed", False)
            scenario.description_completed = completion_status_for_db.get("description_completed", False)
            scenario.student_role_completed = completion_status_for_db.get("student_role_completed", False)
            scenario.personas_completed = completion_status_for_db.get("personas_completed", False)
            scenario.scenes_completed = completion_status_for_db.get("scenes_completed", False)
            scenario.images_completed = completion_status_for_db.get("images_completed", False)
            scenario.learning_outcomes_completed = completion_status_for_db.get("learning_outcomes_completed", False)
            scenario.ai_enhancement_completed = completion_status_for_db.get("ai_enhancement_completed", False)
            db.flush()

        # Save personas - optimized batch operations
        persona_mapping = {}
        key_figures = actual_ai_result.get("key_figures", [])
        personas = actual_ai_result.get("personas", [])
        persona_list = key_figures if key_figures else personas
        
        # Extract ALL unique personas from scenes' personas_involved fields
        scenes = actual_ai_result.get("scenes", [])
        scene_persona_names = set()
        for scene in scenes:
            personas_involved = scene.get("personas_involved", [])
            for persona_name in personas_involved:
                scene_persona_names.add(persona_name)
        
        debug_log(f"[OPTIMIZED] Found {len(scene_persona_names)} unique personas in scenes: {list(scene_persona_names)}")
        
        # Add scene personas that aren't in key_figures
        key_figure_names = {p.get("name", "") for p in persona_list}
        missing_personas = scene_persona_names - key_figure_names
        
        if missing_personas:
            debug_log(f"[OPTIMIZED] Adding {len(missing_personas)} missing personas from scenes: {list(missing_personas)}")
            for persona_name in missing_personas:
                # Create a basic persona entry for scene-only personas
                persona_list.append({
                    "name": persona_name,
                    "role": "Team Member",  # Default role
                    "correlation": f"Participant in the business scenario",
                    "background": f"Key participant in the business scenario",
                    "primary_goals": ["Support team objectives", "Contribute to success"],
                    "personality_traits": {
                        "analytical": 6,
                        "creative": 5,
                        "assertive": 6,
                        "collaborative": 7,
                        "detail_oriented": 6
                    },
                    "is_main_character": False
                })
        
        debug_log(f"[OPTIMIZED] Saving {len(persona_list)} personas in batch...")
        new_persona_ids = []
        
        # Get existing personas in one query
        existing_personas = {}
        if 'existing_persona_ids' in locals() and existing_persona_ids:
            existing_persona_records = db.query(ScenarioPersona).filter(
                ScenarioPersona.id.in_(existing_persona_ids),
                ScenarioPersona.deleted_at.is_(None)
            ).all()
            existing_personas = {p.name: p for p in existing_persona_records}
        
        # Batch process personas
        personas_to_update = []
        personas_to_create = []
        
        for figure in persona_list:
            if isinstance(figure, dict) and figure.get("name"):
                traits = figure.get("personality_traits", {}) or figure.get("traits", {})
                
                if figure["name"] in existing_personas:
                    # Prepare for batch update
                    existing_persona = existing_personas[figure["name"]]
                    existing_persona.role = figure.get("role", "")
                    existing_persona.background = figure.get("background", "")
                    existing_persona.correlation = figure.get("correlation", "")
                    existing_persona.primary_goals = figure.get("primary_goals", []) or figure.get("primaryGoals", [])
                    existing_persona.personality_traits = traits
                    # Normalize systemPrompt: null/empty/whitespace -> None
                    _sp = figure.get("systemPrompt")
                    if isinstance(_sp, str):
                        _sp = _sp.strip()
                    existing_persona.system_prompt = _sp if _sp else None
                    existing_persona.image_url = figure.get("imageUrl")
                    existing_persona.updated_at = datetime.utcnow()
                    personas_to_update.append(existing_persona)
                    debug_log(f"[DEBUG] Updated persona {figure['name']} with system_prompt: {bool(figure.get('systemPrompt'))}")
                    persona_mapping[figure["name"]] = existing_persona.id
                    new_persona_ids.append(existing_persona.id)
                else:
                    # Prepare for batch creation
                    persona_data = {
                        "scenario_id": scenario.id,
                        "name": figure.get("name", ""),
                        "role": figure.get("role", ""),
                        "background": figure.get("background", ""),
                        "correlation": figure.get("correlation", ""),
                        "primary_goals": figure.get("primary_goals", []) or figure.get("primaryGoals", []),
                        "personality_traits": traits,
                        "system_prompt": figure.get("systemPrompt"),
                        "image_url": figure.get("imageUrl"),
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                    personas_to_create.append((figure["name"], persona_data))
                    debug_log(f"[DEBUG] Created persona {figure['name']} with system_prompt: {bool(figure.get('systemPrompt'))}")
        
        # Execute batch updates
        if personas_to_update:
            for persona in personas_to_update:
                db.add(persona)
            debug_log(f"[OPTIMIZED] Updated {len(personas_to_update)} existing personas")
        
        # Execute batch creation
        if personas_to_create:
            for name, persona_data in personas_to_create:
                persona = ScenarioPersona(**persona_data)
                db.add(persona)
                db.flush()  # Get ID
                persona_mapping[name] = persona.id
                new_persona_ids.append(persona.id)
            debug_log(f"[OPTIMIZED] Created {len(personas_to_create)} new personas")

        # Save scenes - optimized batch operations
        scenes = actual_ai_result.get("scenes", [])
        debug_log(f"[OPTIMIZED] Saving {len(scenes)} scenes in batch...")
        new_scene_ids = []
        
        # Get existing scenes in one query
        existing_scenes = {}
        if 'existing_scene_ids' in locals() and existing_scene_ids:
            existing_scene_records = db.query(ScenarioScene).filter(
                ScenarioScene.id.in_(existing_scene_ids)
            ).all()
            existing_scenes = {scene.title: scene for scene in existing_scene_records}
        
        for i, scene in enumerate(scenes):
            if isinstance(scene, dict) and scene.get("title"):
                # Robustly extract success_metric
                success_metric = (
                    scene.get("successMetric") or
                    scene.get("success_metric") or
                    scene.get("success_criteria")
                )
                if not success_metric and scene.get("objectives"):
                    success_metric = scene["objectives"][0]
                
                scene_title = scene.get("title", "")
                
                # Check if this scene already exists
                if scene_title in existing_scenes:
                    # Update existing scene
                    existing_scene = existing_scenes[scene_title]
                    existing_scene.description = scene.get("description", "")
                    existing_scene.user_goal = scene.get("user_goal", "")
                    existing_scene.scene_order = scene.get("sequence_order", i + 1)
                    existing_scene.estimated_duration = scene.get("estimated_duration", 30)
                    existing_scene.image_url = scene.get("image_url", "")
                    existing_scene.image_prompt = f"Business scene: {scene_title}"
                    existing_scene.timeout_turns = int(scene.get("timeout_turns") or 15)
                    existing_scene.success_metric = success_metric
                    existing_scene.updated_at = datetime.utcnow()
                    db.add(existing_scene)
                    new_scene_ids.append(existing_scene.id)
                    debug_log(f"Updated existing scene: {scene_title}, success_metric: {success_metric}")
                    
                    # Update scene-persona relationships
                    # First, remove existing relationships for this scene
                    db.execute(scene_personas.delete().where(scene_personas.c.scene_id == existing_scene.id))
                    
                    # Helper function to check if persona is the main character (student role)
                    def is_main_character(persona_name, student_role):
                        if not student_role or not persona_name:
                            return False
                        
                        import re
                        
                        # Extract just the name part from student role (before any parentheses or additional info)
                        student_name = student_role.split('(')[0].strip()
                        
                        # Remove common title prefixes (Mr., Mrs., Ms., Dr., Prof., etc.) and normalize
                        def normalize_name(name):
                            normalized = name.strip()
                            # Remove title prefixes
                            normalized = re.sub(r'^(Mr\.|Mrs\.|Ms\.|Miss|Dr\.|Prof\.|Professor)\s+', '', normalized, flags=re.IGNORECASE)
                            # Remove all non-alphabetic characters
                            normalized = re.sub(r'[^a-zA-Z]', '', normalized).lower()
                            return normalized
                        
                        return normalize_name(persona_name) == normalize_name(student_name)
                    
                    # Then add new relationships
                    personas_involved = scene.get("personas_involved", [])
                    debug_log(f"🔍 Scene {scene_title} personas_involved: {personas_involved}")
                    debug_log(f"🔍 Available persona_mapping keys: {list(persona_mapping.keys())}")
                    debug_log(f"🔍 Persona mapping details: {persona_mapping}")
                    
                    # Filter out the student role from personas_involved
                    student_role = scenario.student_role if scenario else None
                    personas_involved_filtered = [
                        p for p in personas_involved 
                        if not is_main_character(p, student_role)
                    ]
                    debug_log(f"🔍 Student role: {student_role}")
                    debug_log(f"🔍 Personas after filtering main character: {personas_involved_filtered}")
                    
                    if not personas_involved_filtered or len(personas_involved_filtered) == 0:
                        debug_log(f"⚠️ [WARNING] No personas_involved found after filtering for scene {scene_title}")
                        # Don't skip the scene, just continue without personas
                    
                    unique_persona_names = set(personas_involved_filtered)
                    linked_count = 0
                    for persona_name in unique_persona_names:
                        debug_log(f"🔍 Processing persona: '{persona_name}'")
                        # Try exact match first
                        if persona_name in persona_mapping:
                            persona_id = persona_mapping[persona_name]
                            db.execute(
                                scene_personas.insert().values(
                                    scene_id=existing_scene.id,
                                    persona_id=persona_id,
                                    involvement_level="participant"
                                )
                            )
                            debug_log(f"✅ Linked persona '{persona_name}' (ID: {persona_id}) to scene {scene_title}")
                            linked_count += 1
                        else:
                            # Try case-insensitive match
                            found_match = False
                            for mapping_name, persona_id in persona_mapping.items():
                                if persona_name.lower().strip() == mapping_name.lower().strip():
                                    db.execute(
                                        scene_personas.insert().values(
                                            scene_id=existing_scene.id,
                                            persona_id=persona_id,
                                            involvement_level="participant"
                                        )
                                    )
                                    debug_log(f"✅ Linked persona '{persona_name}' (matched '{mapping_name}', ID: {persona_id}) to scene {scene_title}")
                                    linked_count += 1
                                    found_match = True
                                    break
                            
                            if not found_match:
                                debug_log(f"❌ Persona '{persona_name}' not found in persona_mapping for scene {scene_title}")
                                debug_log(f"❌ Available mappings: {list(persona_mapping.keys())}")
                    
                    debug_log(f"📊 Scene {scene_title}: Linked {linked_count}/{len(unique_persona_names)} personas")
                    
                    # Verify the relationships were created
                    if linked_count > 0:
                        # Check what was actually created
                        created_relationships = db.execute(
                            scene_personas.select().where(scene_personas.c.scene_id == existing_scene.id)
                        ).fetchall()
                        debug_log(f"✅ Verified: {len(created_relationships)} relationships created for scene {scene_title}")
                    else:
                        debug_log(f"❌ WARNING: No relationships created for scene {scene_title}")
                else:
                    # Create new scene
                    scene_record = ScenarioScene(
                        scenario_id=scenario.id,
                        title=scene_title,
                        description=scene.get("description", ""),
                        user_goal=scene.get("user_goal", ""),
                        scene_order=scene.get("sequence_order", i + 1),  # Use sequence_order from frontend, fallback to loop index
                        estimated_duration=scene.get("estimated_duration", 30),
                        image_url=scene.get("image_url", ""),
                        image_prompt=f"Business scene: {scene_title}",
                        timeout_turns=int(scene.get("timeout_turns") or 15),
                        success_metric=success_metric,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    db.add(scene_record)
                    db.flush()
                    new_scene_ids.append(scene_record.id)
                    debug_log(f"Created new scene: {scene_record.title}, success_metric: {scene_record.success_metric}")
                    
                    # Helper function to check if persona is the main character (student role)
                    def is_main_character_new(persona_name, student_role):
                        if not student_role or not persona_name:
                            return False
                        
                        import re
                        
                        # Extract just the name part from student role (before any parentheses or additional info)
                        student_name = student_role.split('(')[0].strip()
                        
                        # Remove common title prefixes (Mr., Mrs., Ms., Dr., Prof., etc.) and normalize
                        def normalize_name(name):
                            normalized = name.strip()
                            # Remove title prefixes
                            normalized = re.sub(r'^(Mr\.|Mrs\.|Ms\.|Miss|Dr\.|Prof\.|Professor)\s+', '', normalized, flags=re.IGNORECASE)
                            # Remove all non-alphabetic characters
                            normalized = re.sub(r'[^a-zA-Z]', '', normalized).lower()
                            return normalized
                        
                        return normalize_name(persona_name) == normalize_name(student_name)
                    
                    # Link only involved personas to each scene
                    personas_involved = scene.get("personas_involved", [])
                    debug_log(f"🔍 Scene {scene_title} personas_involved: {personas_involved}")
                    debug_log(f"🔍 Available persona_mapping keys: {list(persona_mapping.keys())}")
                    debug_log(f"🔍 Persona mapping details: {persona_mapping}")
                    
                    # Filter out the student role from personas_involved
                    student_role = scenario.student_role if scenario else None
                    personas_involved_filtered = [
                        p for p in personas_involved 
                        if not is_main_character_new(p, student_role)
                    ]
                    debug_log(f"🔍 Student role: {student_role}")
                    debug_log(f"🔍 Personas after filtering main character: {personas_involved_filtered}")
                    
                    if not personas_involved_filtered or len(personas_involved_filtered) == 0:
                        debug_log(f"⚠️ [WARNING] No personas_involved found after filtering for scene {scene_title}")
                        # Don't skip the scene, just continue without personas
                    
                    unique_persona_names = set(personas_involved_filtered)
                    linked_count = 0
                    for persona_name in unique_persona_names:
                        debug_log(f"🔍 Processing persona: '{persona_name}'")
                        # Try exact match first
                        if persona_name in persona_mapping:
                            persona_id = persona_mapping[persona_name]
                            db.execute(
                                scene_personas.insert().values(
                                    scene_id=scene_record.id,
                                    persona_id=persona_id,
                                    involvement_level="participant"
                                )
                            )
                            debug_log(f"✅ Linked persona '{persona_name}' (ID: {persona_id}) to scene {scene_title}")
                            linked_count += 1
                        else:
                            # Try case-insensitive match
                            found_match = False
                            for mapping_name, persona_id in persona_mapping.items():
                                if persona_name.lower().strip() == mapping_name.lower().strip():
                                    db.execute(
                                        scene_personas.insert().values(
                                            scene_id=scene_record.id,
                                            persona_id=persona_id,
                                            involvement_level="participant"
                                        )
                                    )
                                    debug_log(f"✅ Linked persona '{persona_name}' (matched '{mapping_name}', ID: {persona_id}) to scene {scene_title}")
                                    linked_count += 1
                                    found_match = True
                                    break
                            
                            if not found_match:
                                debug_log(f"❌ Persona '{persona_name}' not found in persona_mapping for scene {scene_title}")
                                debug_log(f"❌ Available mappings: {list(persona_mapping.keys())}")
                    
                    debug_log(f"📊 Scene {scene_title}: Linked {linked_count}/{len(unique_persona_names)} personas")
                    
                    # Verify the relationships were created
                    if linked_count > 0:
                        # Check what was actually created
                        created_relationships = db.execute(
                            scene_personas.select().where(scene_personas.c.scene_id == scene_record.id)
                        ).fetchall()
                        debug_log(f"✅ Verified: {len(created_relationships)} relationships created for scene {scene_title}")
                    else:
                        debug_log(f"❌ WARNING: No relationships created for scene {scene_title}")
        
        # Clean up old scenes and personas that are no longer needed (only for existing scenarios)
        if 'existing_scene_ids' in locals() and existing_scene_ids:
            # Find scenes that were deleted (exist in old but not in new)
            deleted_scene_ids = [sid for sid in existing_scene_ids if sid not in new_scene_ids]
            if deleted_scene_ids:
                debug_log(f"Checking if {len(deleted_scene_ids)} scenes can be safely deleted: {deleted_scene_ids}")
                
                # Check if any of these scenes are still referenced by user_progress or conversation_logs
                from database.models import UserProgress, ConversationLog
                referenced_by_user_progress = db.query(UserProgress.current_scene_id).filter(
                    UserProgress.current_scene_id.in_(deleted_scene_ids)
                ).distinct().all()
                referenced_by_conversation_logs = db.query(ConversationLog.scene_id).filter(
                    ConversationLog.scene_id.in_(deleted_scene_ids)
                ).distinct().all()
                
                referenced_scene_ids = set()
                referenced_scene_ids.update([r[0] for r in referenced_by_user_progress if r[0] is not None])
                referenced_scene_ids.update([r[0] for r in referenced_by_conversation_logs if r[0] is not None])
                
                # Only delete scenes that are not referenced
                safe_to_delete = [sid for sid in deleted_scene_ids if sid not in referenced_scene_ids]
                unsafe_to_delete = [sid for sid in deleted_scene_ids if sid in referenced_scene_ids]
                
                if unsafe_to_delete:
                    debug_log(f"Cannot delete {len(unsafe_to_delete)} scenes as they are still referenced by user_progress or conversation_logs: {unsafe_to_delete}")
                
                if safe_to_delete:
                    debug_log(f"Safely deleting {len(safe_to_delete)} scenes: {safe_to_delete}")
                    # Delete scene-persona relationships for safe-to-delete scenes
                    db.execute(scene_personas.delete().where(scene_personas.c.scene_id.in_(safe_to_delete)))
                # Delete the scenes themselves
                    db.query(ScenarioScene).filter(ScenarioScene.id.in_(safe_to_delete)).delete()
                    debug_log(f"Deleted safe scenes and their relationships")
        
        # Initialize deleted_persona_ids outside the if block
        deleted_persona_ids = []
        if 'existing_persona_ids' in locals() and existing_persona_ids:
            # Find personas that were deleted (exist in old but not in new)
            deleted_persona_ids = [pid for pid in existing_persona_ids if pid not in new_persona_ids]
            debug_log(f"[DEBUG] Existing persona IDs: {existing_persona_ids}")
            debug_log(f"[DEBUG] New persona IDs: {new_persona_ids}")
            debug_log(f"[DEBUG] Deleted persona IDs: {deleted_persona_ids}")
            if deleted_persona_ids:
                debug_log(f"Checking if {len(deleted_persona_ids)} personas can be safely deleted: {deleted_persona_ids}")
        
        # Only proceed with deletion if there are personas to delete
        if deleted_persona_ids:
            # Use soft deletion for all personas (like simulations)
            debug_log(f"Soft deleting {len(deleted_persona_ids)} personas: {deleted_persona_ids}")
            
            # Soft delete the personas by marking them as deleted
            db.query(ScenarioPersona).filter(ScenarioPersona.id.in_(deleted_persona_ids)).update({
                'deleted_at': datetime.utcnow(),
                'deleted_by': current_user.id if current_user else None,
                'deletion_reason': 'User deletion from draft'
            })
            
            # Remove scene-persona relationships for soft-deleted personas
            db.execute(scene_personas.delete().where(scene_personas.c.persona_id.in_(deleted_persona_ids)))
            
            debug_log(f"Soft deleted {len(deleted_persona_ids)} personas from scenario")
        
        db.commit()
        debug_log(f"Successfully saved draft scenario {scenario.id}")
        return {
            "status": "saved",
            "scenario_id": scenario.id,
            "message": f"Scenario '{title}' saved as draft"
        }
        
    except Exception as e:
        print(f"[ERROR] Failed to save scenario: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save scenario: {str(e)}")

@router.put("/{scenario_id}/status")
async def update_scenario_status(
    scenario_id: int,
    status_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update scenario status (draft, active, archived) and return full scenario object"""
    try:
        scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")
        
        # Check permissions - only creator can update status
        if scenario.created_by != current_user.id:
            raise HTTPException(status_code=403, detail="You can only update scenarios you created")
        
        new_status = status_data.get("status")
        if new_status not in ["draft", "active", "archived"]:
            raise HTTPException(status_code=400, detail="Invalid status. Must be 'draft', 'active', or 'archived'")
        
        # Update status and related fields
        scenario.status = new_status
        scenario.updated_at = datetime.utcnow()
        
        # Update is_draft and is_public based on status
        if new_status == "active":
            scenario.is_draft = False
            scenario.is_public = True
        elif new_status == "draft":
            scenario.is_draft = True
            scenario.is_public = False
        # archived status keeps existing is_draft/is_public values
        
        db.commit()
        db.refresh(scenario)
        
        debug_log(f"Updated scenario {scenario_id} status to {new_status} (is_draft: {scenario.is_draft})")
        
        # Get personas for this scenario (excluding soft-deleted)
        personas = db.query(ScenarioPersona).filter(
            ScenarioPersona.scenario_id == scenario.id,
            ScenarioPersona.deleted_at.is_(None)
        ).all()
        
        # Get scenes for this scenario
        scenes = db.query(ScenarioScene).filter(
            ScenarioScene.scenario_id == scenario.id
        ).order_by(ScenarioScene.scene_order).all()
        
        # Fix learning_objectives if it's a string (convert to list)
        learning_objectives = scenario.learning_objectives or []
        if isinstance(learning_objectives, str):
            learning_objectives = [item.strip() for item in learning_objectives.split('\n') if item.strip()]
        
        # Return full scenario object matching the format from get_scenarios
        return {
            "id": scenario.id,
            "title": scenario.title or "",
            "description": scenario.description or "",
            "challenge": scenario.challenge or "",
            "industry": scenario.industry or "Business",
            "learning_objectives": learning_objectives,
            "student_role": scenario.student_role or "Business Analyst",
            "category": scenario.category,
            "difficulty_level": scenario.difficulty_level,
            "estimated_duration": scenario.estimated_duration,
            "tags": scenario.tags,
            "pdf_title": scenario.pdf_title,
            "pdf_source": scenario.pdf_source,
            "processing_version": scenario.processing_version,
            "rating_avg": scenario.rating_avg,
            "rating_count": scenario.rating_count,
            "source_type": scenario.source_type,
            "is_public": scenario.is_public,
            "is_template": scenario.is_template,
            "allow_remixes": scenario.allow_remixes,
            "usage_count": scenario.usage_count,
            "clone_count": scenario.clone_count,
            "created_by": scenario.created_by,
            "created_at": scenario.created_at,
            "updated_at": scenario.updated_at,
            "status": scenario.status,
            "is_draft": scenario.is_draft,
            "personas": [
                {
                    "id": persona.id,
                    "name": persona.name,
                    "role": persona.role,
                    "background": persona.background,
                    "correlation": persona.correlation,
                    "primary_goals": persona.primary_goals or [],
                    "personality_traits": persona.personality_traits or {},
                    "system_prompt": persona.system_prompt,
                    "image_url": persona.image_url
                }
                for persona in personas
            ],
            "scenes": [
                {
                    "id": scene.id,
                    "title": scene.title,
                    "description": scene.description,
                    "user_goal": scene.user_goal,
                    "scene_order": scene.scene_order,
                    "estimated_duration": scene.estimated_duration,
                    "image_url": scene.image_url,
                    "timeout_turns": scene.timeout_turns,
                    "success_metric": scene.success_metric
                }
                for scene in scenes
            ],
            "completion_status": scenario.completion_status or {},
            "name_completed": scenario.name_completed,
            "description_completed": scenario.description_completed,
            "student_role_completed": scenario.student_role_completed,
            "personas_completed": scenario.personas_completed,
            "scenes_completed": scenario.scenes_completed,
            "images_completed": scenario.images_completed,
            "learning_outcomes_completed": scenario.learning_outcomes_completed,
            "ai_enhancement_completed": scenario.ai_enhancement_completed
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        debug_log(f"Failed to update scenario status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update scenario status: {str(e)}")

@router.delete("/unique/{unique_id}")
async def delete_scenario_by_unique_id(
    unique_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Delete scenario by unique_id"""
    try:
        scenario = db.query(Scenario).filter(Scenario.unique_id == unique_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")
        
        # Check permissions - only creator can delete
        if current_user and scenario.created_by != current_user.id:
            raise HTTPException(status_code=403, detail="You can only delete scenarios you created")
        
        # Soft delete
        scenario.deleted_at = datetime.utcnow()
        scenario.deleted_by = current_user.id if current_user else None
        
        db.commit()
        
        return {
            "status": "success",
            "message": "Scenario deleted successfully",
            "unique_id": unique_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete scenario: {str(e)}")

@router.post("/publish/{scenario_id}")
async def publish_scenario(
    scenario_id: int,
    publish_request: ScenarioPublishRequest,
    db: Session = Depends(get_db)
):
    """
    Publish a scenario to the marketplace
    Converts a draft scenario to public with metadata
    """
    
    # Get scenario with all related data
    scenario = db.query(Scenario).options(
        selectinload(Scenario.personas),
        selectinload(Scenario.scenes),
        selectinload(Scenario.files)
    ).filter(Scenario.id == scenario_id).first()
    
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    
    debug_log(f"Publishing scenario {scenario_id}")
    debug_log(f"Found scenario title: '{scenario.title}'")
    debug_log(f"Found scenario description length: {len(scenario.description or '')}")
    debug_log(f"Scenario personas count: {len(scenario.personas)}")
    debug_log(f"Scenario scenes count: {len(scenario.scenes)}")
    
    # Validate scenario is ready for publishing
    if not scenario.title or not scenario.description:
        debug_log(f"Validation failed - title: '{scenario.title}', description: '{scenario.description}'")
        raise HTTPException(
            status_code=400, 
            detail="Scenario must have title and description to publish"
        )
    
    if not scenario.personas:
        raise HTTPException(
            status_code=400,
            detail="Scenario must have at least one persona to publish"
        )
    
    if not scenario.scenes:
        raise HTTPException(
            status_code=400,
            detail="Scenario must have at least one scene to publish"
        )
    
    # Check if this draft already has a published version
    existing_published = None
    debug_log(f"Draft scenario {scenario.id} (unique_id: {scenario.unique_id}) has published_version_id: {scenario.published_version_id}")
    
    # Refresh the scenario from the database to get the latest published_version_id
    db.refresh(scenario)
    debug_log(f"After refresh - published_version_id: {scenario.published_version_id}")
    
    if scenario.published_version_id:
        existing_published = db.query(Scenario).filter(
            Scenario.id == scenario.published_version_id
        ).first()
        if existing_published:
            debug_log(f"Found existing published version: {existing_published.id} (unique_id: {existing_published.unique_id})")
        else:
            debug_log(f"Published version {scenario.published_version_id} not found - will create new one")
    else:
        debug_log(f"No published version exists - will create new one")
    
    # ALWAYS update the existing scenario instead of creating a new one
    debug_log(f"Publishing scenario {scenario.id} (unique_id: {scenario.unique_id})")
    debug_log(f"Converting draft to published - keeping same ID and unique_id")
    
    # Update the existing scenario to be published
    scenario.is_draft = False  # Convert to published
    scenario.is_public = True
    scenario.status = "active"
    scenario.category = publish_request.category
    scenario.difficulty_level = publish_request.difficulty_level
    scenario.tags = publish_request.tags
    scenario.estimated_duration = publish_request.estimated_duration
    scenario.updated_at = datetime.utcnow()
    
    # The scenario keeps its original ID and unique_id
    published_scenario = scenario
    
    debug_log(f"Converted scenario {scenario.id} to published with unique_id: {scenario.unique_id}")
    
    # No need to copy personas and scenes - we're using the same scenario
    debug_log(f"Using existing personas and scenes for published scenario {published_scenario.id}")
    
    db.commit()
    db.refresh(published_scenario)
    
    return {
        "status": "published",
        "scenario_id": published_scenario.id,
        "draft_id": scenario.id,
        "message": f"Scenario '{scenario.title}' has been published to the marketplace"
    }

@router.get("/marketplace", response_model=MarketplaceResponse)
async def get_marketplace_scenarios(
    category: Optional[str] = Query(None),
    difficulty_level: Optional[str] = Query(None),
    tags: Optional[str] = Query(None),  # Comma-separated tags
    min_rating: Optional[float] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Browse published scenarios in the marketplace
    Supports filtering, search, and pagination
    """
    
    # Build query for published scenarios
    query = db.query(Scenario).filter(Scenario.is_public == True)
    
    # Apply filters
    if category:
        query = query.filter(Scenario.category == category)
    
    if difficulty_level:
        query = query.filter(Scenario.difficulty_level == difficulty_level)
    
    if tags:
        tag_list = [tag.strip() for tag in tags.split(",")]
        # Check if any of the requested tags exist in the scenario tags
        for tag in tag_list:
            query = query.filter(Scenario.tags.contains([tag]))
    
    if min_rating:
        query = query.filter(Scenario.rating_avg >= min_rating)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Scenario.title.ilike(search_term),
                Scenario.description.ilike(search_term),
                Scenario.industry.ilike(search_term)
            )
        )
    
    # Get total count for pagination
    total = query.count()
    
    # Apply pagination and ordering
    scenarios = query.options(
        selectinload(Scenario.personas),
        selectinload(Scenario.scenes),
        selectinload(Scenario.creator)
    ).order_by(
        desc(Scenario.rating_avg),
        desc(Scenario.usage_count),
        desc(Scenario.created_at)
    ).offset((page - 1) * page_size).limit(page_size).all()
    
    # Calculate total pages
    total_pages = (total + page_size - 1) // page_size
    
    return MarketplaceResponse(
        scenarios=scenarios,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )

@router.get("/{scenario_id}/full", response_model=ScenarioPublishingResponse)
async def get_scenario_full(
    scenario_id: int,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Get full scenario details with personas, scenes, and reviews
    Increments usage count for public scenarios
    
    Security:
    - Public scenarios can be accessed by anyone
    - Private scenarios can only be accessed by their creator
    """
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    
    # Check access permissions
    if not scenario.is_public:
        if not current_user:
            raise HTTPException(
                status_code=401, 
                detail="Authentication required to access private scenarios"
            )
        if scenario.created_by != current_user.id:
            raise HTTPException(
                status_code=403, 
                detail="You can only access scenarios you created"
            )
    
    if scenario.is_public:
        scenario.usage_count += 1
        db.commit()
    reviews = db.query(ScenarioReview).options(
        selectinload(ScenarioReview.reviewer)
    ).filter(
        ScenarioReview.scenario_id == scenario_id
    ).order_by(desc(ScenarioReview.created_at)).limit(10).all()
    scenario_dict = scenario.__dict__.copy()
    scenario_dict['reviews'] = reviews
    scenes = db.query(ScenarioScene).filter(ScenarioScene.scenario_id == scenario_id).order_by(ScenarioScene.scene_order).all()
    from database.schemas import ScenarioSceneResponse, ScenarioPersonaResponse
    
    scene_dicts = []
    for scene in scenes:
        scene_data = scene.__dict__.copy()
        
        # Query personas involved in this scene through the junction table (excluding soft-deleted)
        involved_personas = db.query(ScenarioPersona).join(
            scene_personas, ScenarioPersona.id == scene_personas.c.persona_id
        ).filter(
            scene_personas.c.scene_id == scene.id,
            ScenarioPersona.deleted_at.is_(None)
        ).all()
        
        # Build personas as ScenarioPersonaResponse objects
        persona_dicts = []
        for persona in involved_personas:
            persona_data = ScenarioPersonaResponse(
                id=persona.id,
                scenario_id=persona.scenario_id,
                name=persona.name,
                role=persona.role,
                background=persona.background,
                correlation=persona.correlation,
                primary_goals=(
                    [persona.primary_goals] if isinstance(persona.primary_goals, str) and persona.primary_goals else
                    persona.primary_goals if isinstance(persona.primary_goals, list) else []
                ),
                personality_traits=persona.personality_traits or {},
                image_url=persona.image_url,
                created_at=persona.created_at,
                updated_at=persona.updated_at
            ).model_dump()
            persona_dicts.append(persona_data)
        
        scene_data['personas'] = persona_dicts
        scene_data['personas_involved'] = [p.name for p in involved_personas]
        scene_dicts.append(scene_data)
    scenario_dict['scenes'] = [ScenarioSceneResponse.model_validate(scene).model_dump() for scene in scene_dicts]
    # Ensure all required fields for ScenarioPublishingResponse are present
    required_fields = [
        'id', 'title', 'description', 'challenge', 'industry', 'learning_objectives',
        'student_role', 'category', 'difficulty_level', 'estimated_duration', 'tags',
        'pdf_title', 'pdf_source', 'processing_version', 'rating_avg', 'rating_count',
        'source_type', 'is_public', 'is_template', 'allow_remixes', 'usage_count',
        'clone_count', 'created_by', 'created_at', 'updated_at'
    ]
    for field in required_fields:
        if field not in scenario_dict:
            scenario_dict[field] = getattr(scenario, field, None)
    # Fix learning_objectives if it's a string
    if isinstance(scenario_dict.get('learning_objectives'), str):
        items = [item.strip() for item in scenario_dict['learning_objectives'].split('\n') if item.strip()]
        scenario_dict['learning_objectives'] = items
    return scenario_dict

@router.post("/{scenario_id}/clone")
async def clone_scenario(
    scenario_id: int,
    db: Session = Depends(get_db)
):
    """
    Clone a scenario for editing
    Creates a copy of the scenario with all personas and scenes
    """
    
    # Get original scenario with all related data
    original = db.query(Scenario).options(
        selectinload(Scenario.personas),
        selectinload(Scenario.scenes).selectinload(ScenarioScene.personas),
        selectinload(Scenario.files)
    ).filter(Scenario.id == scenario_id).first()
    
    if not original:
        raise HTTPException(status_code=404, detail="Scenario not found")
    
    if not original.is_public and not original.allow_remixes:
        raise HTTPException(
            status_code=403, 
            detail="This scenario cannot be cloned"
        )
    
    # Create new scenario (clone)
    new_scenario = Scenario(
        title=f"{original.title} (Copy)",
        description=original.description,
        challenge=original.challenge,
        industry=original.industry,
        learning_objectives=original.learning_objectives,
        student_role=original.student_role,
        category=original.category,
        difficulty_level=original.difficulty_level,
        estimated_duration=original.estimated_duration,
        tags=original.tags,
        pdf_title=original.pdf_title,
        pdf_source=original.pdf_source,
        processing_version=original.processing_version,
        grading_config=original.grading_config,
        source_type="cloned",
        is_public=False,  # Clones start as private
        allow_remixes=True,
        created_by=None,  # No user authentication yet
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(new_scenario)
    db.flush()  # Get the new scenario ID
    
    # Clone personas
    persona_mapping = {}  # old_id -> new_id
    for persona in original.personas:
        new_persona = ScenarioPersona(
            scenario_id=new_scenario.id,
            name=persona.name,
            role=persona.role,
            background=persona.background,
            correlation=persona.correlation,
            primary_goals=persona.primary_goals,
            personality_traits=persona.personality_traits,
            system_prompt=(persona.system_prompt.strip() if isinstance(persona.system_prompt, str) else None) if persona.system_prompt else None,
            image_url=persona.image_url
        )
        db.add(new_persona)
        db.flush()
        persona_mapping[persona.id] = new_persona.id
    
    # Clone scenes
    for scene in original.scenes:
        new_scene = ScenarioScene(
            scenario_id=new_scenario.id,
            title=scene.title,
            description=scene.description,
            user_goal=scene.user_goal,
            scene_order=scene.scene_order,
            estimated_duration=scene.estimated_duration,
            image_url=scene.image_url,
            image_prompt=scene.image_prompt
        )
        db.add(new_scene)
        db.flush()
        
        # Clone scene-persona relationships
        for persona in scene.personas:
            if persona.id in persona_mapping:
                new_persona_id = persona_mapping[persona.id]
                # Add relationship through junction table
                db.execute(
                    scene_personas.insert().values(
                        scene_id=new_scene.id,
                        persona_id=new_persona_id,
                        involvement_level='participant'
                    )
                )
    
    # Clone files (metadata only, not actual file content)
    for file in original.files:
        new_file = ScenarioFile(
            scenario_id=new_scenario.id,
            filename=f"cloned_{file.filename}",
            file_type=file.file_type,
            original_content=file.original_content,
            processed_content=file.processed_content,
            processing_status="completed"
        )
        db.add(new_file)
    
    # Update clone count
    original.clone_count += 1
    
    db.commit()
    db.refresh(new_scenario)
    
    return {
        "status": "cloned",
        "original_scenario_id": scenario_id,
        "new_scenario_id": new_scenario.id,
        "message": f"Scenario cloned successfully as '{new_scenario.title}'"
    }

@router.delete("/{scenario_id}")
async def delete_scenario(
    scenario_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Soft delete a scenario by marking it as deleted.
    Only the scenario creator can delete their scenarios.
    User progress data is preserved in the archive.
    """
    from services.soft_deletion import SoftDeletionService
    
    scenario = db.query(Scenario).filter(
        Scenario.id == scenario_id,
        Scenario.deleted_at.is_(None)  # Only get non-deleted scenarios
    ).first()
    
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    
    # Check if the current user owns this scenario
    if scenario.created_by != current_user.id:
        raise HTTPException(
            status_code=403, 
            detail="You can only delete scenarios you created"
        )

    # Use soft deletion service
    service = SoftDeletionService(db)
    success = service.soft_delete_scenario(
        scenario_id=scenario_id,
        deleted_by=current_user.id,
        reason="User deletion"
    )
    
    if not success:
        raise HTTPException(
            status_code=500, 
            detail="Failed to delete scenario"
        )
    
    return {
        "status": "success", 
        "message": f"Scenario {scenario_id} deleted successfully. User progress data has been archived."
    }

@router.post("/cleanup/archives")
async def cleanup_archives(
    days_old: int = Query(30, ge=1, le=365, description="Days after which to clean up archives"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Clean up old archived user progress records
    Only admin users can perform cleanup
    """
    from services.soft_deletion import SoftDeletionService
    
    # Check if user is admin (you can adjust this logic)
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403, 
            detail="Only admin users can perform cleanup"
        )
    
    service = SoftDeletionService(db)
    
    # Get stats before cleanup
    stats_before = service.get_archive_stats()
    
    # Run cleanup
    cleaned_count = service.cleanup_old_archives(days_old)
    
    # Get stats after cleanup
    stats_after = service.get_archive_stats()
    
    return {
        "status": "success",
        "message": f"Cleanup completed. Removed {cleaned_count} records older than {days_old} days.",
        "stats_before": stats_before,
        "stats_after": stats_after,
        "records_cleaned": cleaned_count
    }

@router.get("/cleanup/stats")
async def get_cleanup_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get archive statistics
    """
    from services.soft_deletion import SoftDeletionService
    
    service = SoftDeletionService(db)
    stats = service.get_archive_stats()
    
    return {
        "status": "success",
        "archive_stats": stats
    }

# --- SCENARIO REVIEW ENDPOINTS ---

@router.post("/{scenario_id}/reviews", response_model=ScenarioReviewResponse)
async def create_scenario_review(
    scenario_id: int,
    review: ScenarioReviewCreate,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Create a review for a scenario
    Updates the scenario's average rating
    Includes rate limiting for anonymous reviews
    """
    
    # Check rate limit for anonymous reviews
    rate_limit_result = check_anonymous_review_rate_limit(request)
    
    # Check if scenario exists
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    
    # For now, skip user validation since we don't have authentication
    # TODO: Implement proper user authentication for reviews
    
    # Create new review (without user validation for now)
    new_review = ScenarioReview(
        scenario_id=scenario_id,
        reviewer_id=None,  # No user authentication yet
        rating=review.rating,
        review_text=review.review_text,
        pros=review.pros,
        cons=review.cons,
        use_case=review.use_case
    )
    
    db.add(new_review)
    
    # Update scenario rating
    avg_rating = db.query(func.avg(ScenarioReview.rating)).filter(
        ScenarioReview.scenario_id == scenario_id
    ).scalar()
    
    rating_count = db.query(func.count(ScenarioReview.id)).filter(
        ScenarioReview.scenario_id == scenario_id
    ).scalar()
    
    scenario.rating_avg = round(float(avg_rating or 0), 2)
    scenario.rating_count = int(rating_count or 0) + 1  # Include the new review
    
    db.commit()
    db.refresh(new_review)
    
    # Add rate limit headers to response
    from utilities.rate_limiter import rate_limiter, ANONYMOUS_REVIEW_CONFIG
    headers = rate_limiter.get_rate_limit_headers(rate_limit_result, ANONYMOUS_REVIEW_CONFIG)
    for header_name, header_value in headers.items():
        response.headers[header_name] = header_value
    
    return new_review

@router.get("/{scenario_id}/reviews", response_model=List[ScenarioReviewResponse])
async def get_scenario_reviews(
    scenario_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Get reviews for a scenario with pagination
    """
    
    reviews = db.query(ScenarioReview).options(
        selectinload(ScenarioReview.reviewer)
    ).filter(
        ScenarioReview.scenario_id == scenario_id
    ).order_by(
        desc(ScenarioReview.created_at)
    ).offset((page - 1) * page_size).limit(page_size).all()
    
    return reviews

# --- UTILITY ENDPOINTS ---

@router.get("/categories")
async def get_scenario_categories(db: Session = Depends(get_db)):
    """
    Get available scenario categories
    """
    
    categories = db.query(Scenario.category).filter(
        Scenario.category.isnot(None),
        Scenario.is_public == True
    ).distinct().all()
    
    return {
        "categories": [cat[0] for cat in categories if cat[0]],
        "predefined": [
            "Leadership", "Strategy", "Operations", "Marketing", 
            "Finance", "Human Resources", "Technology", "Innovation"
        ]
    }

@router.get("/difficulty-levels")
async def get_difficulty_levels():
    """
    Get available difficulty levels
    """
    
    return {
        "levels": ["Beginner", "Intermediate", "Advanced"],
        "descriptions": {
            "Beginner": "Suitable for students new to business case studies",
            "Intermediate": "Requires basic business knowledge and analytical skills",
            "Advanced": "Complex scenarios requiring deep business expertise"
        }
    } 
