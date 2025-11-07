"""
Publishing API endpoints for PDF-to-Scenario functionality
Handles scenario publishing
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import and_, or_, desc, func
from typing import List, Optional
import json
import asyncio
from datetime import datetime
import time
import secrets
import base64
from io import BytesIO

from database.connection import get_db
from utilities.rate_limiter import check_anonymous_review_rate_limit
from utilities.auth import get_current_user, get_current_user_optional
from utilities.debug_logging import debug_log
from services.wasabi_service import wasabi_service, upload_persona_avatar_from_url, upload_scene_image_from_url
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
        # Validate current_user
        if not current_user or not current_user.id:
            debug_log("[ERROR] Invalid current_user in get_scenarios")
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Start with base query - exclude soft-deleted scenarios and filter by current user
        query = db.query(Scenario).filter(
            Scenario.deleted_at.is_(None),
            Scenario.created_by == current_user.id
        )
        debug_log(f"[PUBLISHING] Starting query for user {current_user.id} with status filter: {status}")
        
        # Filter by status if provided
        if status:
            if status == "active":
                # For active scenarios, show only non-draft scenarios
                query = query.filter(Scenario.is_draft == False)
            elif status == "draft":
                # For draft scenarios, show draft scenarios OR scenarios being created
                # Simple or_ filter should work - if it fails, the try/except will catch it
                query = query.filter(
                    or_(
                        Scenario.is_draft == True,
                        Scenario.status == "creating"
                    )
                )
            elif status == "archived":
                # For archived scenarios, show scenarios with archived status
                query = query.filter(Scenario.status == "archived")
        
        # If no status filter provided, show only active (non-draft) scenarios by default
        # This prevents showing both draft and active versions of the same scenario
        # Exception: if include_drafts=True, show all scenarios regardless of draft status
        if not status and not include_drafts:
            query = query.filter(Scenario.is_draft == False)
        
        try:
            scenarios = query.all()
            debug_log(f"[PUBLISHING] Found {len(scenarios)} scenarios with status filter: {status}")
        except Exception as query_error:
            debug_log(f"[ERROR] Query execution failed: {str(query_error)}")
            import traceback
            debug_log(f"[ERROR] Traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Failed to query scenarios: {str(query_error)}")
        
        # Convert to response format with personas and scenes
        scenario_responses = []
        for scenario in scenarios:
            try:
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
                "status": scenario.status or "draft",  # Ensure status is never None - keep "creating" as-is for frontend
                "is_draft": scenario.is_draft if scenario.is_draft is not None else False,
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
            except Exception as scenario_error:
                debug_log(f"[ERROR] Failed to build response for scenario {scenario.id}: {scenario_error}")
                import traceback
                debug_log(f"[ERROR] Traceback: {traceback.format_exc()}")
                # Skip this scenario and continue with others
                continue
        
        return scenario_responses
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        debug_log(f"[ERROR] Error fetching scenarios: {e}")
        import traceback
        debug_log(f"[ERROR] Traceback: {traceback.format_exc()}")
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

async def _handle_pdf_storage(scenario, pdf_metadata, db):
    """Helper function to upload PDF to Wasabi and create/update ScenarioFile record"""
    try:
        # Extract PDF metadata
        filename = pdf_metadata.get("filename")
        file_size = pdf_metadata.get("file_size")
        file_type = pdf_metadata.get("file_type")
        wasabi_url = pdf_metadata.get("wasabi_url")
        pdf_url = pdf_metadata.get("pdf_url")
        file_contents_base64 = pdf_metadata.get("file_contents_base64")
        needs_upload = pdf_metadata.get("needs_upload", False)
        
        if not filename:
            debug_log(f"[PDF_STORAGE] Missing filename in PDF metadata")
            return
        
        # PRIORITY 1: If we have base64 encoded file, upload to proper case-studies path
        if file_contents_base64:
            debug_log(f"[PDF_STORAGE] Uploading PDF to proper case-studies path")
            # Decode base64 back to bytes
            pdf_bytes = base64.b64decode(file_contents_base64)

            # Generate S3 key
            s3_key = wasabi_service.get_case_study_key(scenario.id, filename)

            # Upload to Wasabi
            wasabi_url = await wasabi_service.upload_from_bytes(pdf_bytes, s3_key, file_type)

            if not wasabi_url:
                debug_log(f"[PDF_STORAGE] Failed to upload PDF to Wasabi, continuing without file storage")
                return

            # Verify the URL uses the correct path structure
            if wasabi_url and f'scenarios/{scenario.id}/case-study' in wasabi_url:
                debug_log(f"[PDF_STORAGE] ✅ PDF uploaded to correct hierarchical path: {wasabi_url}")
            elif wasabi_url and 'case-studies' in wasabi_url:
                debug_log(f"[PDF_STORAGE] ⚠️ WARNING: PDF in old flat structure (case-studies/), should be in scenarios/{scenario.id}/case-study/")
            elif wasabi_url and 'temp-pdfs' in wasabi_url:
                debug_log(f"[PDF_STORAGE] ⚠️ WARNING: PDF in temporary path, should be in scenarios/{scenario.id}/case-study/")

            debug_log(f"[PDF_STORAGE] Uploaded PDF to Wasabi: {wasabi_url}")

            # Check if ScenarioFile record already exists
            existing_file = db.query(ScenarioFile).filter(
                ScenarioFile.scenario_id == scenario.id,
                ScenarioFile.filename == filename
            ).first()

            if existing_file:
                # Update existing record
                existing_file.file_path = wasabi_url
                existing_file.file_size = file_size
                existing_file.file_type = file_type
                existing_file.processing_status = "completed"
                existing_file.processed_at = datetime.utcnow()
                db.add(existing_file)
                debug_log(f"[PDF_STORAGE] Updated existing ScenarioFile record ID {existing_file.id}")
            else:
                # Create new record
                scenario_file = ScenarioFile(
                    scenario_id=scenario.id,
                    filename=filename,
                    file_path=wasabi_url,
                    file_size=file_size,
                    file_type=file_type,
                    processing_status="completed",
                    uploaded_at=datetime.utcnow(),
                    processed_at=datetime.utcnow()
                )
                db.add(scenario_file)
                db.flush()
                debug_log(f"[PDF_STORAGE] Created new ScenarioFile record ID {scenario_file.id}")

        # PRIORITY 2: Handle large files uploaded to temporary storage
        elif pdf_metadata.get("temp_pdf_url"):
            temp_url = pdf_metadata.get("temp_pdf_url")
            debug_log(f"[PDF_STORAGE] Large file detected in temporary storage: {temp_url}")
            debug_log(f"[PDF_STORAGE] PDF metadata keys: {list(pdf_metadata.keys())}")
            debug_log(f"[PDF_STORAGE] Scenario ID: {scenario.id}, Filename: {filename}")
            debug_log(f"[PDF_STORAGE] Bucket name: {wasabi_service.bucket_name}")
            
            # Extract S3 key from URL
            # URL formats:
            # - AWS virtual-hosted: https://bucket.s3.region.amazonaws.com/key
            # - AWS path-style: https://s3.region.amazonaws.com/bucket/key
            # - Wasabi: https://endpoint/bucket/key
            from urllib.parse import urlparse
            parsed_url = urlparse(temp_url)
            hostname = parsed_url.netloc
            temp_path = parsed_url.path.lstrip('/')
            
            debug_log(f"[PDF_STORAGE] Parsed URL - hostname: {hostname}, path: {temp_path}")
            
            # Check if bucket name is in hostname (AWS virtual-hosted style)
            if wasabi_service.bucket_name and hostname.startswith(wasabi_service.bucket_name + '.'):
                # Virtual-hosted style: bucket.s3.region.amazonaws.com/key
                temp_s3_key = temp_path
                debug_log(f"[PDF_STORAGE] Detected AWS virtual-hosted style URL")
            elif temp_path.startswith(wasabi_service.bucket_name + '/'):
                # Path-style or Wasabi: endpoint/bucket/key
                temp_s3_key = temp_path[len(wasabi_service.bucket_name) + 1:]
                debug_log(f"[PDF_STORAGE] Detected path-style URL, removed bucket prefix")
            else:
                # Path might already be just the key
                temp_s3_key = temp_path
                debug_log(f"[PDF_STORAGE] Using path as-is (no bucket prefix detected)")
            
            debug_log(f"[PDF_STORAGE] Extracted temp S3 key: {temp_s3_key}")
            
            # Download from temporary location
            debug_log(f"[PDF_STORAGE] Downloading PDF from temp location: {temp_s3_key}")
            pdf_bytes = await wasabi_service.download_file(temp_s3_key)
            
            if not pdf_bytes:
                debug_log(f"[PDF_STORAGE] ❌ Failed to download from temporary location (got {len(pdf_bytes) if pdf_bytes else 0} bytes), skipping storage")
                return
            
            debug_log(f"[PDF_STORAGE] ✅ Downloaded {len(pdf_bytes)} bytes from temp location")
            
            # Generate final S3 key
            s3_key = wasabi_service.get_case_study_key(scenario.id, filename)
            debug_log(f"[PDF_STORAGE] Final S3 key will be: {s3_key}")
            
            # Upload to final location
            debug_log(f"[PDF_STORAGE] Uploading to final location: {s3_key}")
            wasabi_url = await wasabi_service.upload_from_bytes(pdf_bytes, s3_key, file_type)
            
            if not wasabi_url:
                debug_log(f"[PDF_STORAGE] ❌ Failed to upload PDF to final location, continuing without file storage")
                return
            
            debug_log(f"[PDF_STORAGE] ✅ Successfully uploaded to final location: {wasabi_url}")
            debug_log(f"[PDF_STORAGE] ✅ Expected path pattern 'scenarios/{scenario.id}/case-study/' in URL: {'scenarios/{}/case-study/'.format(scenario.id) in wasabi_url}")
            
            # Delete temporary file after successful move
            try:
                debug_log(f"[PDF_STORAGE] Deleting temporary file: {temp_s3_key}")
                deleted = await wasabi_service.delete_file(temp_s3_key)
                if deleted:
                    debug_log(f"[PDF_STORAGE] ✅ Deleted temporary file: {temp_s3_key}")
                else:
                    debug_log(f"[PDF_STORAGE] ⚠️ Delete operation returned False for: {temp_s3_key}")
            except Exception as e:
                debug_log(f"[PDF_STORAGE] ⚠️ Exception deleting temporary file {temp_s3_key}: {str(e)}")
                # Don't fail the entire operation if temp deletion fails
            
            # Create/update ScenarioFile record
            existing_file = db.query(ScenarioFile).filter(
                ScenarioFile.scenario_id == scenario.id,
                ScenarioFile.filename == filename
            ).first()
            
            if existing_file:
                existing_file.file_path = wasabi_url
                existing_file.file_size = file_size
                existing_file.file_type = file_type
                existing_file.processing_status = "completed"
                existing_file.processed_at = datetime.utcnow()
                db.add(existing_file)
                debug_log(f"[PDF_STORAGE] Updated existing ScenarioFile record ID {existing_file.id}")
            else:
                scenario_file = ScenarioFile(
                    scenario_id=scenario.id,
                    filename=filename,
                    file_path=wasabi_url,
                    file_size=file_size,
                    file_type=file_type,
                    processing_status="completed",
                    uploaded_at=datetime.utcnow(),
                    processed_at=datetime.utcnow()
                )
                db.add(scenario_file)
                db.flush()
                debug_log(f"[PDF_STORAGE] Created new ScenarioFile record ID {scenario_file.id}")
        
        # PRIORITY 3: Handle large files that need upload (needs_upload flag - fallback)
        elif needs_upload:
            debug_log(f"[PDF_STORAGE] Large file detected (needs_upload=true), but file contents not provided")
            debug_log(f"[PDF_STORAGE] ⚠️ Large files require re-upload from frontend. Skipping storage.")
            return
        
        # PRIORITY 3: Fallback to existing URL (legacy support for old temp-pdfs paths)
        else:
            existing_url = wasabi_url or pdf_url

            if existing_url:
                # Use existing URL - skip upload
                debug_log(f"[PDF_STORAGE] Using existing URL (legacy fallback): {existing_url}")

                # Check if ScenarioFile record already exists
                existing_file = db.query(ScenarioFile).filter(
                    ScenarioFile.scenario_id == scenario.id,
                    ScenarioFile.filename == filename
                ).first()

                if existing_file:
                    # Update existing record
                    existing_file.file_path = existing_url
                    if file_size:
                        existing_file.file_size = file_size
                    if file_type:
                        existing_file.file_type = file_type
                    existing_file.processing_status = "completed"
                    existing_file.processed_at = datetime.utcnow()
                    db.add(existing_file)
                    debug_log(f"[PDF_STORAGE] Updated existing ScenarioFile record ID {existing_file.id} with URL")
                else:
                    # Create new record
                    scenario_file = ScenarioFile(
                        scenario_id=scenario.id,
                        filename=filename,
                        file_path=existing_url,
                        file_size=file_size,
                        file_type=file_type,
                        processing_status="completed",
                        uploaded_at=datetime.utcnow(),
                        processed_at=datetime.utcnow()
                    )
                    db.add(scenario_file)
                    db.flush()
                    debug_log(f"[PDF_STORAGE] Created new ScenarioFile record ID {scenario_file.id} with URL")
            else:
                debug_log(f"[PDF_STORAGE] No URL or file_contents_base64 provided, skipping storage")
                return
    
    except Exception as e:
        debug_log(f"[PDF_STORAGE] Error during PDF storage: {str(e)}")
        # Don't fail the entire save operation if PDF storage fails

def _is_wasabi_url(url: str) -> bool:
    """
    Check if a URL is already a Wasabi/S3 URL (already saved).
    
    Args:
        url: URL to check
        
    Returns:
        True if URL is a Wasabi/S3 URL, False otherwise
    """
    if not url or not isinstance(url, str):
        return False
    
    url_lower = url.lower()
    # Check for Wasabi endpoint patterns
    if 'wasabisys.com' in url_lower or 'wasabi' in url_lower:
        return True
    # Check for AWS S3 patterns
    if 's3.amazonaws.com' in url_lower or 's3-' in url_lower and '.amazonaws.com' in url_lower:
        return True
    # Check if URL contains our bucket structure (scenarios/X/personas or scenarios/X/scenes)
    if 'scenarios/' in url_lower and ('personas/' in url_lower or 'scenes/' in url_lower):
        return True
    
    return False

async def _handle_image_uploads(
    personas_to_upload: List[dict],
    scenes_to_upload: List[dict],
    db: Session
) -> tuple[int, int]:
    """
    Helper function to upload persona avatars and scene images to Wasabi in parallel.
    Skips images that are already saved to Wasabi/S3.
    
    Args:
        personas_to_upload: List of dicts containing persona_id, scenario_id, temp_url
        scenes_to_upload: List of dicts containing scene_id, scenario_id, temp_url
        db: Database session
        
    Returns:
        Tuple of (personas_uploaded_count, scenes_uploaded_count)
    """
    try:
        personas_uploaded = 0
        scenes_uploaded = 0
        
        # Filter out personas/scenes that already have Wasabi URLs
        # Check database for existing Wasabi URLs
        persona_ids = [p.get("persona_id") for p in personas_to_upload if p.get("persona_id")]
        scene_ids = [s.get("scene_id") for s in scenes_to_upload if s.get("scene_id")]
        
        # Get existing URLs from database
        existing_persona_urls = {}
        if persona_ids:
            existing_personas = db.query(ScenarioPersona.id, ScenarioPersona.image_url).filter(
                ScenarioPersona.id.in_(persona_ids)
            ).all()
            existing_persona_urls = {p.id: p.image_url for p in existing_personas if p.image_url}
        
        existing_scene_urls = {}
        if scene_ids:
            existing_scenes = db.query(ScenarioScene.id, ScenarioScene.image_url).filter(
                ScenarioScene.id.in_(scene_ids)
            ).all()
            existing_scene_urls = {s.id: s.image_url for s in existing_scenes if s.image_url}
        
        # Filter personas: only upload if URL is not already a Wasabi URL
        personas_to_upload_filtered = []
        personas_skipped = 0
        for persona_info in personas_to_upload:
            temp_url = persona_info.get("temp_url")
            persona_id = persona_info.get("persona_id")
            
            # Check if URL is already a Wasabi URL
            if temp_url and _is_wasabi_url(temp_url):
                personas_skipped += 1
                debug_log(f"[IMAGE_STORAGE] Persona ID {persona_id}: Skipping upload - already a Wasabi URL: {temp_url[:80]}...")
                continue
            
            # Check if persona already has a Wasabi URL in database
            if persona_id and persona_id in existing_persona_urls:
                existing_url = existing_persona_urls[persona_id]
                if existing_url and _is_wasabi_url(existing_url):
                    personas_skipped += 1
                    debug_log(f"[IMAGE_STORAGE] Persona ID {persona_id}: Skipping upload - already has Wasabi URL in database")
                    continue
            
            personas_to_upload_filtered.append(persona_info)
        
        # Filter scenes: only upload if URL is not already a Wasabi URL
        scenes_to_upload_filtered = []
        scenes_skipped = 0
        for scene_info in scenes_to_upload:
            temp_url = scene_info.get("temp_url")
            scene_id = scene_info.get("scene_id")
            
            # Check if URL is already a Wasabi URL
            if temp_url and _is_wasabi_url(temp_url):
                scenes_skipped += 1
                debug_log(f"[IMAGE_STORAGE] Scene ID {scene_id}: Skipping upload - already a Wasabi URL: {temp_url[:80]}...")
                continue
            
            # Check if scene already has a Wasabi URL in database
            if scene_id and scene_id in existing_scene_urls:
                existing_url = existing_scene_urls[scene_id]
                if existing_url and _is_wasabi_url(existing_url):
                    scenes_skipped += 1
                    debug_log(f"[IMAGE_STORAGE] Scene ID {scene_id}: Skipping upload - already has Wasabi URL in database")
                    continue
            
            scenes_to_upload_filtered.append(scene_info)
        
        debug_log(f"[IMAGE_STORAGE] Filtered: {personas_skipped} personas and {scenes_skipped} scenes skipped (already saved)")
        debug_log(f"[IMAGE_STORAGE] Starting parallel upload for {len(personas_to_upload_filtered)} personas and {len(scenes_to_upload_filtered)} scenes")
        
        if not personas_to_upload_filtered and not scenes_to_upload_filtered:
            debug_log(f"[IMAGE_STORAGE] All images already saved to Wasabi - no uploads needed")
            return (0, 0)
        
        # Semaphore to limit concurrent uploads (10-20 recommended)
        upload_semaphore = asyncio.Semaphore(15)
        
        # Wrapper function for persona upload with semaphore
        async def upload_persona_with_semaphore(scenario_id: int, persona_id: int, temp_url: str) -> str:
            async with upload_semaphore:
                return await upload_persona_avatar_from_url(scenario_id, persona_id, temp_url)

        # Wrapper function for scene upload with semaphore
        async def upload_scene_with_semaphore(scenario_id: int, scene_id: int, temp_url: str) -> str:
            async with upload_semaphore:
                return await upload_scene_image_from_url(scenario_id, scene_id, temp_url)
        
        # Create upload tasks for personas with tracking (only filtered personas)
        persona_upload_tasks = []
        persona_task_map = []  # Maps task index to (persona, temp_url)
        for persona_info in personas_to_upload_filtered:
            temp_url = persona_info.get("temp_url")
            persona_id = persona_info.get("persona_id")
            scenario_id = persona_info.get("scenario_id")
            if temp_url and isinstance(temp_url, str) and temp_url.startswith("http") and persona_id and scenario_id:
                persona_upload_tasks.append(upload_persona_with_semaphore(scenario_id, persona_id, temp_url))
                persona_task_map.append((persona_info, temp_url))

        # Create upload tasks for scenes with tracking (only filtered scenes)
        scene_upload_tasks = []
        scene_task_map = []  # Maps task index to (scene, temp_url)
        for scene_info in scenes_to_upload_filtered:
            temp_url = scene_info.get("temp_url")
            scene_id = scene_info.get("scene_id")
            scenario_id = scene_info.get("scenario_id")
            if temp_url and isinstance(temp_url, str) and temp_url.startswith("http") and scene_id and scenario_id:
                scene_upload_tasks.append(upload_scene_with_semaphore(scenario_id, scene_id, temp_url))
                scene_task_map.append((scene_info, temp_url))
        
        # Upload all personas and scenes in parallel
        persona_results = []
        scene_results = []
        
        if persona_upload_tasks:
            persona_results = await asyncio.gather(*persona_upload_tasks, return_exceptions=True)
        
        if scene_upload_tasks:
            scene_results = await asyncio.gather(*scene_upload_tasks, return_exceptions=True)
        
        # Process persona upload results
        for i, result in enumerate(persona_results):
            persona_info, temp_url = persona_task_map[i]
            persona_id = persona_info.get("persona_id")
            if isinstance(result, Exception):
                debug_log(f"[IMAGE_STORAGE] Persona ID {persona_id}: Upload failed with exception, keeping temporary URL: {str(result)}")
            elif result and result.strip():
                if persona_id:
                    persona = db.query(ScenarioPersona).filter(ScenarioPersona.id == persona_id).first()
                    if persona:
                        # Success - update database with Wasabi URL
                        persona.image_url = result
                        db.add(persona)
                        personas_uploaded += 1
                        debug_log(f"[IMAGE_STORAGE] Persona {persona.name} (ID {persona.id}): Uploaded to Wasabi: {result}")
                    else:
                        debug_log(f"[IMAGE_STORAGE] Persona ID {persona_id} not found when recording upload result")
            else:
                debug_log(f"[IMAGE_STORAGE] Persona ID {persona_id}: Upload failed, keeping temporary URL")
        
        # Process scene upload results
        for i, result in enumerate(scene_results):
            scene_info, temp_url = scene_task_map[i]
            scene_id = scene_info.get("scene_id")
            if isinstance(result, Exception):
                debug_log(f"[IMAGE_STORAGE] Scene ID {scene_id}: Upload failed with exception, keeping temporary URL: {str(result)}")
            elif result and result.strip():
                if scene_id:
                    scene = db.query(ScenarioScene).filter(ScenarioScene.id == scene_id).first()
                    if scene:
                        # Success - update database with Wasabi URL
                        scene.image_url = result
                        db.add(scene)
                        scenes_uploaded += 1
                        debug_log(f"[IMAGE_STORAGE] Scene {scene.title} (ID {scene.id}): Uploaded to Wasabi: {result}")
                    else:
                        debug_log(f"[IMAGE_STORAGE] Scene ID {scene_id} not found when recording upload result")
            else:
                debug_log(f"[IMAGE_STORAGE] Scene ID {scene_id}: Upload failed, keeping temporary URL")
        
        debug_log(f"[IMAGE_STORAGE] Completed: {personas_uploaded}/{len(personas_to_upload)} personas, {scenes_uploaded}/{len(scenes_to_upload)} scenes uploaded to Wasabi")
        
        return (personas_uploaded, scenes_uploaded)
    
    except Exception as e:
        debug_log(f"[IMAGE_STORAGE] Error during image uploads: {str(e)}")
        # Don't fail the entire save operation if image upload fails
        return (0, 0)

def _save_scenario_to_db(
    db: Session,
    ai_result: dict,
    scenario_id: Optional[int],
    current_user: Optional[User]
):
    """
    Synchronous function to handle all database operations for saving a scenario.
    This function should be run in a thread pool to avoid blocking the event loop.
    """
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
    
    # Extract PDF metadata from AI result if present
    pdf_metadata = None
    if "pdf_metadata" in actual_ai_result:
        pdf_metadata = actual_ai_result["pdf_metadata"]
        filename = pdf_metadata.get("filename")
        file_size = pdf_metadata.get("file_size")
        debug_log(f"[PDF_STORAGE] Found PDF metadata in AI result: {filename}, {file_size} bytes")
        debug_log(f"[PDF_STORAGE] PDF metadata contents: {list(pdf_metadata.keys())}")
        if "temp_pdf_url" in pdf_metadata:
            debug_log(f"[PDF_STORAGE] temp_pdf_url present: {pdf_metadata.get('temp_pdf_url')}")
        if "file_contents_base64" in pdf_metadata:
            base64_len = len(pdf_metadata.get("file_contents_base64", ""))
            debug_log(f"[PDF_STORAGE] file_contents_base64 present: {base64_len} chars")
    else:
        debug_log(f"[PDF_STORAGE] ⚠️ No pdf_metadata found in AI result. Available keys: {list(actual_ai_result.keys())}")
    
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
        
        # PDF storage is async, handle it outside this sync function if possible
        # For now, let's keep it here and see if there's an async way to call it
        
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
        
    # This part needs to be async, so we'll handle it after this function returns
    # if pdf_metadata:
    #     await _handle_pdf_storage(scenario, pdf_metadata, db)

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
    kept_persona_ids: set[int] = set()
    personas_with_temp_urls: list[dict] = []  # List of dicts for Wasabi upload metadata
    
    # Get existing personas in one query
    existing_personas: dict[str, ScenarioPersona] = {}
    if 'existing_persona_ids' in locals() and existing_persona_ids:
        existing_persona_records = db.query(ScenarioPersona).filter(
            ScenarioPersona.id.in_(existing_persona_ids),
            ScenarioPersona.deleted_at.is_(None)
        ).all()
        for persona in existing_persona_records:
            normalized_name = (persona.name or "").strip().lower()
            if not normalized_name:
                continue
            current_ts = persona.updated_at or datetime.min
            existing_entry = existing_personas.get(normalized_name)
            existing_ts = existing_entry.updated_at if existing_entry and existing_entry.updated_at else datetime.min
            if not existing_entry or current_ts >= existing_ts:
                existing_personas[normalized_name] = persona
    
    # Batch process personas
    personas_to_update = []
    personas_to_create = []
    
    for figure in persona_list:
        if isinstance(figure, dict) and figure.get("name"):
            traits = figure.get("personality_traits", {}) or figure.get("traits", {})
            name_value = figure["name"].strip()
            normalized_name = name_value.lower()

            if normalized_name in existing_personas:
                # Prepare for batch update
                existing_persona = existing_personas[normalized_name]
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
                # Only update image_url if a non-empty URL is provided
                new_image_url = figure.get("imageUrl") or figure.get("image_url")
                if new_image_url and isinstance(new_image_url, str) and new_image_url.strip():
                    existing_persona.image_url = new_image_url
                existing_persona.updated_at = datetime.utcnow()
                personas_to_update.append(existing_persona)
                debug_log(f"[DEBUG] Updated persona {figure['name']} with system_prompt: {bool(figure.get('systemPrompt'))}")
                persona_mapping[name_value] = existing_persona.id
                kept_persona_ids.add(existing_persona.id)
                # Extract temporary URL for Wasabi upload
                # Only add if it's not already a Wasabi URL
                temp_url = figure.get("imageUrl") or figure.get("image_url")
                # Check if existing persona already has a Wasabi URL
                existing_wasabi_url = existing_persona.image_url if hasattr(existing_persona, 'image_url') else None
                # Only add to upload queue if:
                # 1. URL is provided and is HTTP
                # 2. URL is NOT already a Wasabi URL
                # 3. Existing persona doesn't already have a Wasabi URL
                if temp_url and isinstance(temp_url, str) and temp_url.startswith("http"):
                    # Note: _is_wasabi_url is defined above, we can use it directly
                    if not _is_wasabi_url(temp_url) and not (existing_wasabi_url and _is_wasabi_url(existing_wasabi_url)):
                        personas_with_temp_urls.append({
                            "persona_id": existing_persona.id,
                            "scenario_id": existing_persona.scenario_id,
                            "temp_url": temp_url
                        })
                    else:
                        debug_log(f"[IMAGE_STORAGE] Persona {existing_persona.id}: Skipping - already has Wasabi URL or URL is already Wasabi")
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
            kept_persona_ids.add(persona.id)
            # Extract temporary URL for Wasabi upload
            # Only add if it's not already a Wasabi URL
            temp_url = persona_data.get("image_url")
            if temp_url and isinstance(temp_url, str) and temp_url.startswith("http"):
                if not _is_wasabi_url(temp_url):
                    personas_with_temp_urls.append({
                        "persona_id": persona.id,
                        "scenario_id": persona.scenario_id,
                        "temp_url": temp_url
                    })
                else:
                    debug_log(f"[IMAGE_STORAGE] New persona {persona.id}: Skipping - URL is already Wasabi")
        debug_log(f"[OPTIMIZED] Created {len(personas_to_create)} new personas")
    
    debug_log(f"[IMAGE_STORAGE] Collected {len(personas_with_temp_urls)} personas with temporary URLs for Wasabi upload")

    # Save scenes - optimized batch operations
    scenes = actual_ai_result.get("scenes", [])
    debug_log(f"[OPTIMIZED] Saving {len(scenes)} scenes in batch...")
    kept_scene_ids: set[int] = set()
    scenes_with_temp_urls: list[dict] = []  # List of dicts for Wasabi upload metadata
    
    # Get existing scenes in one query
    existing_scenes: dict[str, ScenarioScene] = {}
    if 'existing_scene_ids' in locals() and existing_scene_ids:
        existing_scene_records = db.query(ScenarioScene).filter(
            ScenarioScene.id.in_(existing_scene_ids)
        ).all()
        for scene_record in existing_scene_records:
            title_key = (scene_record.title or "").strip().lower()
            if not title_key:
                # Fallback to ID to avoid collisions on missing titles
                title_key = f"__id__{scene_record.id}"
            current_ts = scene_record.updated_at or datetime.min
            existing_entry = existing_scenes.get(title_key)
            existing_ts = existing_entry.updated_at if existing_entry and existing_entry.updated_at else datetime.min
            if not existing_entry or current_ts >= existing_ts:
                existing_scenes[title_key] = scene_record
    
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
            
            normalized_title = scene_title.strip().lower()
            if not normalized_title:
                normalized_title = f"__untitled__{i}"

            # Initialize existing_scene to None
            existing_scene = None
            
            # Check if this scene already exists
            if normalized_title in existing_scenes:
                # Update existing scene
                existing_scene = existing_scenes[normalized_title]
                debug_log(f"[SCENE_UPDATE] 🔄 Found existing scene: {scene_title} (ID: {existing_scene.id})")
                
                # CRITICAL: Verify scene still exists before updating
                scene_still_exists = db.query(ScenarioScene.id).filter(ScenarioScene.id == existing_scene.id).first()
                if not scene_still_exists:
                    debug_log(f"[SCENE_UPDATE] ⚠️ WARNING: Scene {existing_scene.id} ({scene_title}) was deleted before update, will create new scene instead")
                    # Scene was deleted, create new one instead
                    existing_scene = None
                else:
                    existing_scene.description = scene.get("description", "")
                    existing_scene.user_goal = scene.get("user_goal", "")
                    existing_scene.scene_order = scene.get("sequence_order", i + 1)
                    existing_scene.estimated_duration = scene.get("estimated_duration", 30)
                    # Only update image_url if a non-empty URL is provided
                    new_image_url = scene.get("image_url", "")
                    if new_image_url and isinstance(new_image_url, str) and new_image_url.strip():
                        existing_scene.image_url = new_image_url
                    existing_scene.image_prompt = f"Business scene: {scene_title}"
                    existing_scene.timeout_turns = int(scene.get("timeout_turns") or 15)
                    existing_scene.success_metric = success_metric
                    existing_scene.updated_at = datetime.utcnow()
                    kept_scene_ids.add(existing_scene.id)
                    debug_log(f"[SCENE_UPDATE] ✅ Updated existing scene: {scene_title} (ID: {existing_scene.id}), success_metric: {success_metric}")
            
            # If we have an existing scene (either matched or verified), update relationships
            if existing_scene:
                # Extract temporary URL for Wasabi upload
                # Only add if it's not already a Wasabi URL
                temp_url = scene.get("image_url", "")
                existing_wasabi_url = existing_scene.image_url if hasattr(existing_scene, 'image_url') else None
                if temp_url and isinstance(temp_url, str) and temp_url.startswith("http"):
                    if not _is_wasabi_url(temp_url) and not (existing_wasabi_url and _is_wasabi_url(existing_wasabi_url)):
                        scenes_with_temp_urls.append({
                            "scene_id": existing_scene.id,
                            "scenario_id": existing_scene.scenario_id,
                            "temp_url": temp_url
                        })
                    else:
                        debug_log(f"[IMAGE_STORAGE] Scene {existing_scene.id}: Skipping - already has Wasabi URL or URL is already Wasabi")
                
                # Update scene-persona relationships
                # First, verify the scene actually exists in the database
                debug_log(f"[SCENE_UPDATE] 🔍 Verifying scene {existing_scene.id} ({scene_title}) exists before relationship update...")
                scene_exists = db.query(ScenarioScene.id).filter(ScenarioScene.id == existing_scene.id).first()
                if not scene_exists:
                    debug_log(f"[SCENE_UPDATE] ⚠️ CRITICAL WARNING: Scene {existing_scene.id} ({scene_title}) no longer exists in database, skipping relationship update")
                    debug_log(f"[SCENE_UPDATE] This indicates a race condition - scene was deleted between match and update")
                    continue
                debug_log(f"[SCENE_UPDATE] ✅ Scene {existing_scene.id} verified, proceeding with relationship update")

                # Remove existing relationships for this scene
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
                        try:
                            db.execute(
                                scene_personas.insert().values(
                                    scene_id=existing_scene.id,
                                    persona_id=persona_id,
                                    involvement_level="participant"
                                )
                            )
                            debug_log(f"✅ Linked persona '{persona_name}' (ID: {persona_id}) to scene {scene_title}")
                            linked_count += 1
                        except Exception as link_error:
                            debug_log(f"❌ ERROR linking persona '{persona_name}' (ID: {persona_id}) to scene {scene_title}: {str(link_error)}")
                            # Continue with other personas instead of crashing
                    else:
                        # Try case-insensitive match
                        found_match = False
                        for mapping_name, persona_id in persona_mapping.items():
                            if persona_name.lower().strip() == mapping_name.lower().strip():
                                try:
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
                                except Exception as link_error:
                                    debug_log(f"❌ ERROR linking persona '{persona_name}' (matched '{mapping_name}', ID: {persona_id}) to scene {scene_title}: {str(link_error)}")
                                    # Try next match or continue
                        
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

                # Verify the scene was actually created and has an ID
                if not scene_record.id:
                    debug_log(f"❌ ERROR: Scene '{scene_title}' was not assigned an ID after flush, skipping relationship creation")
                    continue

                kept_scene_ids.add(scene_record.id)
                debug_log(f"Created new scene: {scene_record.title} (ID: {scene_record.id}), success_metric: {scene_record.success_metric}")
                # Extract temporary URL for Wasabi upload
                # Only add if it's not already a Wasabi URL
                temp_url = scene.get("image_url", "")
                if temp_url and isinstance(temp_url, str) and temp_url.startswith("http"):
                    if not _is_wasabi_url(temp_url):
                        scenes_with_temp_urls.append({
                            "scene_id": scene_record.id,
                            "scenario_id": scene_record.scenario_id,
                            "temp_url": temp_url
                        })
                    else:
                        debug_log(f"[IMAGE_STORAGE] New scene {scene_record.id}: Skipping - URL is already Wasabi")
                
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
                        try:
                            db.execute(
                                scene_personas.insert().values(
                                    scene_id=scene_record.id,
                                    persona_id=persona_id,
                                    involvement_level="participant"
                                )
                            )
                            debug_log(f"✅ Linked persona '{persona_name}' (ID: {persona_id}) to scene {scene_title}")
                            linked_count += 1
                        except Exception as link_error:
                            debug_log(f"❌ ERROR linking persona '{persona_name}' (ID: {persona_id}) to new scene {scene_title} (ID: {scene_record.id}): {str(link_error)}")
                            # Continue with other personas instead of crashing
                    else:
                        # Try case-insensitive match
                        found_match = False
                        for mapping_name, persona_id in persona_mapping.items():
                            if persona_name.lower().strip() == mapping_name.lower().strip():
                                try:
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
                                except Exception as link_error:
                                    debug_log(f"❌ ERROR linking persona '{persona_name}' (matched '{mapping_name}', ID: {persona_id}) to new scene {scene_title} (ID: {scene_record.id}): {str(link_error)}")
                                    # Try next match or continue
                        
                        if not found_match:
                            debug_log(f"❌ Persona '{persona_name}' not found in persona_mapping for scene {scene_title}")
                            debug_log(f"❌ Available mappings: {list(persona_mapping.keys())}")

                # This code should run ONCE per scene, not per persona
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
        
        debug_log(f"[IMAGE_STORAGE] Collected {len(scenes_with_temp_urls)} scenes with temporary URLs for Wasabi upload")
        
        # This part is async, handle it after this function returns
        # if personas_with_temp_urls or scenes_with_temp_urls:
        #     personas_uploaded, scenes_uploaded = await _handle_image_uploads(personas_with_temp_urls, scenes_with_temp_urls, db)
        #     debug_log(f"[IMAGE_STORAGE] Wasabi upload summary: {personas_uploaded} personas, {scenes_uploaded} scenes")
        
        # Clean up old scenes and personas that are no longer needed (only for existing scenarios)
        if 'existing_scene_ids' in locals() and existing_scene_ids:
            existing_scene_ids_set = set(existing_scene_ids)
            # Find scenes that were deleted (exist in old but not in new)
            deleted_scene_ids = [sid for sid in existing_scene_ids_set if sid not in kept_scene_ids]
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
                    debug_log(f"[SCENE_DELETE] 🗑️ Safely deleting {len(safe_to_delete)} scenes: {safe_to_delete}")
                    debug_log(f"[SCENE_DELETE] Kept scene IDs: {sorted(kept_scene_ids)}")
                    debug_log(f"[SCENE_DELETE] This deletion happens AFTER scene processing - check for race conditions")
                    
                    # Delete scene-persona relationships for safe-to-delete scenes
                    db.execute(scene_personas.delete().where(scene_personas.c.scene_id.in_(safe_to_delete)))
                    # Delete the scenes themselves using ORM to keep session state consistent
                    scenes_to_remove = db.query(ScenarioScene).filter(ScenarioScene.id.in_(safe_to_delete)).all()
                    debug_log(f"[SCENE_DELETE] Found {len(scenes_to_remove)} scenes to remove from database")
                    for scene_obj in scenes_to_remove:
                        debug_log(f"[SCENE_DELETE] Deleting scene: {scene_obj.title} (ID: {scene_obj.id})")
                        db.delete(scene_obj)
                    db.flush()
                    debug_log(f"[SCENE_DELETE] ✅ Deleted {len(safe_to_delete)} safe scenes and their relationships")
        
        # Initialize deleted_persona_ids outside the if block
        deleted_persona_ids = []
        if 'existing_persona_ids' in locals() and existing_persona_ids:
            # Find personas that were deleted (exist in old but not in new)
            deleted_persona_ids = [pid for pid in existing_persona_ids if pid not in kept_persona_ids]
            debug_log(f"[DEBUG] Existing persona IDs: {existing_persona_ids}")
            debug_log(f"[DEBUG] Persona IDs to keep: {sorted(kept_persona_ids)}")
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

    return scenario, pdf_metadata, personas_with_temp_urls, scenes_with_temp_urls, title

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
    
    debug_log(f"[SAVE] 💾 Starting save_scenario_draft - scenario_id: {scenario_id}, user: {current_user.id if current_user else 'None'}")
    
    try:
        # Parse JSON from request body
        ai_result = await request.json()
        debug_log(f"[SAVE] 📥 Received AI result with keys: {list(ai_result.keys())}")

        scenario, pdf_metadata, personas_with_temp_urls, scenes_with_temp_urls, title = _save_scenario_to_db(
            db=db,
            ai_result=ai_result,
            scenario_id=scenario_id,
            current_user=current_user
        )

        if pdf_metadata:
            await _handle_pdf_storage(scenario, pdf_metadata, db)
        
        # Trigger parallel image uploads to Wasabi
        if personas_with_temp_urls or scenes_with_temp_urls:
            personas_uploaded, scenes_uploaded = await _handle_image_uploads(personas_with_temp_urls, scenes_with_temp_urls, db)
            debug_log(f"[IMAGE_STORAGE] Wasabi upload summary: {personas_uploaded} personas, {scenes_uploaded} scenes")
        
        db.commit() # Commit changes from async uploads
        debug_log(f"Successfully saved draft scenario {scenario.id}")
        return {
            "status": "saved",
            "scenario_id": scenario.id,
            "message": f"Scenario '{title}' saved as draft"
        }
        
    except HTTPException as exc:
        db.rollback()
        raise exc
    except Exception as e:
        import traceback
        debug_log(f"Error in save_scenario_draft: {e}")
        debug_log(f"Traceback: {traceback.format_exc()}")
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
    Publish a scenario - just flip flags, no validation
    """
    debug_log(f"[PUBLISH] 🚀 Starting publish for scenario {scenario_id}")
    debug_log(f"[PUBLISH] Request data: {publish_request}")
    
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    
    if not scenario:
        debug_log(f"[PUBLISH] ❌ Scenario {scenario_id} not found")
        raise HTTPException(status_code=404, detail="Scenario not found")
    
    debug_log(f"[PUBLISH] ✅ Found scenario: {scenario.title} (status: {scenario.status}, is_draft: {scenario.is_draft})")
    
    # Flip flags
    scenario.is_draft = False
    scenario.is_public = True
    scenario.status = "active"
    scenario.category = publish_request.category
    scenario.difficulty_level = publish_request.difficulty_level
    scenario.tags = publish_request.tags
    scenario.estimated_duration = publish_request.estimated_duration
    scenario.updated_at = datetime.utcnow()
    
    debug_log(f"[PUBLISH] 📝 Updated scenario flags - committing to database...")
    db.commit()
    debug_log(f"[PUBLISH] ✅ Successfully published scenario {scenario_id}")
    
    return {
        "status": "published",
        "scenario_id": scenario.id,
        "message": f"Scenario '{scenario.title}' has been published"
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

@router.post("/cleanup/temp-pdfs")
async def cleanup_temp_pdfs(
    days_old: int = Query(7, description="Delete files older than this many days"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Clean up temporary PDF files from S3 storage.
    Deletes files in temp-pdfs/ folder older than specified days.
    """
    from services.wasabi_service import wasabi_service
    
    try:
        deleted_count = await wasabi_service.cleanup_temp_pdfs(days_old=days_old)
        return {
            "status": "success",
            "deleted_count": deleted_count,
            "message": f"Deleted {deleted_count} temporary PDF files older than {days_old} days"
        }
    except Exception as e:
        debug_log(f"[CLEANUP] Error cleaning up temp PDFs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to cleanup temp PDFs: {str(e)}")

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
