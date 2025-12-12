"""
Publishing service for business logic.

Handles all business logic for the publishing module including
simulation saving, publishing, and file storage operations.
"""

import asyncio
import base64
import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException

from common.db.models import (
    Simulation, SimulationPersona, SimulationScene, SimulationFile,
    User, scene_personas
)
from common.services.s3_service import s3_service
from common.utils.id_generator import generate_simulation_id
from .repository import PublishingRepository
from .tasks import (
    is_temporary_image_url as _is_temporary_image_url,
    is_s3_url as _is_s3_url,
    handle_image_uploads,
    enqueue_image_upload,
    get_upload_status,
    check_image_exists_in_s3
)

logger = logging.getLogger(__name__)


class PublishingService:
    """Service for publishing business logic."""
    
    def __init__(self, db: Session):
        self.db = db
        self.repository = PublishingRepository(db)
    
    async def handle_pdf_storage(
        self,
        simulation: Simulation,
        pdf_metadata: Dict[str, Any]
    ) -> None:
        """Handle PDF storage to S3."""
        logger.info(f"[PDF_STORAGE] Starting PDF storage for simulation {simulation.id}")
        
        filename = pdf_metadata.get("filename")
        if not filename:
            logger.warning("[PDF_STORAGE] Missing filename in PDF metadata")
            return
        
        file_size = pdf_metadata.get("file_size")
        file_type = pdf_metadata.get("file_type", "application/pdf")
        wasabi_url = pdf_metadata.get("wasabi_url")
        pdf_url = pdf_metadata.get("pdf_url")
        file_contents_base64 = pdf_metadata.get("file_contents_base64")
        temp_pdf_url = pdf_metadata.get("temp_pdf_url")
        
        # Check if PDF already exists in database
        existing_file = self.repository.get_simulation_file(simulation.id, filename)
        existing_case_study_url = getattr(simulation, 'case_study_url', None)
        
        if existing_case_study_url and _is_s3_url(existing_case_study_url):
            logger.info(f"[PDF_STORAGE] Simulation already has case_study_url: {existing_case_study_url}")
            return
        
        if existing_file and existing_file.file_path and _is_s3_url(existing_file.file_path):
            logger.info(f"[PDF_STORAGE] PDF already exists in database with S3 URL")
            if not existing_case_study_url:
                setattr(simulation, 'case_study_url', existing_file.file_path)
                self.db.add(simulation)
            return
        
        # Check if PDF already exists in S3
        s3_key = s3_service.get_case_study_key(simulation.id, filename)
        if await s3_service.file_exists(s3_key):
            s3_url = s3_service._build_public_url(s3_key)
            logger.info(f"[PDF_STORAGE] PDF already exists in S3: {s3_key}")
            
            self.repository.create_or_update_simulation_file(
                simulation.id, filename, s3_url, file_size, file_type
            )
            setattr(simulation, 'case_study_url', s3_url)
            self.db.add(simulation)
            return
        
        # Check if metadata already has S3 URL
        existing_url = None
        if wasabi_url and _is_s3_url(wasabi_url):
            existing_url = wasabi_url
        elif pdf_url and _is_s3_url(pdf_url):
            existing_url = pdf_url
        
        if existing_url:
            self.repository.create_or_update_scenario_file(
                simulation.id, filename, existing_url, file_size, file_type
            )
            setattr(simulation, 'case_study_url', existing_url)
            self.db.add(simulation)
            return
        
        # Upload from base64
        if file_contents_base64:
            pdf_bytes = base64.b64decode(file_contents_base64)
            s3_url = await s3_service.upload_from_bytes(pdf_bytes, s3_key, file_type)
            
            if s3_url:
                self.repository.create_or_update_simulation_file(
                    simulation.id, filename, s3_url, file_size, file_type
                )
                setattr(simulation, 'case_study_url', s3_url)
                self.db.add(simulation)
                logger.info(f"[PDF_STORAGE] Uploaded PDF to S3: {s3_url}")
            return
        
        # Upload from temp URL
        if temp_pdf_url:
            # Download from temp location and upload to final location
            # Extract S3 key from temp URL if it's already in S3
            if _is_s3_url(temp_pdf_url):
                # Extract key from URL
                parts = temp_pdf_url.split('/')
                if 'scenarios' in temp_pdf_url:
                    # Find the scenarios part and extract the key
                    idx = temp_pdf_url.find('scenarios/')
                    temp_key = temp_pdf_url[idx:]
                    pdf_bytes = await s3_service.download_file(temp_key)
                    if pdf_bytes:
                        s3_url = await s3_service.upload_from_bytes(pdf_bytes, s3_key, file_type)
                        if s3_url:
                            self.repository.create_or_update_scenario_file(
                                simulation.id, filename, s3_url, file_size, file_type
                            )
                            setattr(simulation, 'case_study_url', s3_url)
                            self.db.add(simulation)
                            # Delete temp file
                            await s3_service.delete_file(temp_key)
                            logger.info(f"[PDF_STORAGE] Moved PDF from temp to final location: {s3_url}")
            else:
                # Download from external URL and upload
                s3_url = await s3_service.upload_from_url(temp_pdf_url, s3_key, file_type)
                if s3_url:
                    self.repository.create_or_update_scenario_file(
                        simulation.id, filename, s3_url, file_size, file_type
                    )
                    setattr(simulation, 'case_study_url', s3_url)
                    self.db.add(simulation)
                    logger.info(f"[PDF_STORAGE] Uploaded PDF from URL to S3: {s3_url}")
    
    async def handle_image_uploads(
        self,
        personas_to_upload: List[Dict[str, Any]],
        scenes_to_upload: List[Dict[str, Any]]
    ) -> Tuple[int, int]:
        """Handle image uploads to S3 - delegates to tasks module."""
        return await handle_image_uploads(self.db, self.repository, personas_to_upload, scenes_to_upload)
    
    async def save_simulation_draft(
        self,
        simulation_id: Optional[int],
        user_id: Optional[int],
        data: Dict[str, Any]
    ) -> Simulation:
        """Save or update a simulation draft with personas and scenes."""
        logger.info(f"[SAVE] Saving simulation draft - simulation_id: {simulation_id}, user_id: {user_id}")
        
        # Get or create simulation
        if simulation_id:
            simulation = self.repository.get_simulation_by_id(simulation_id)
            if not simulation:
                raise HTTPException(status_code=404, detail="Simulation not found")
            if user_id and simulation.created_by != user_id:
                raise HTTPException(status_code=403, detail="You can only edit simulations you created")
        else:
            # Create new simulation
            unique_id = generate_simulation_id(self.db)
            simulation = Simulation(
                unique_id=unique_id,
                title=data.get("title", "Untitled Simulation"),
                description=data.get("description", ""),
                created_by=user_id,
                status="draft",
                is_draft=True
            )
            self.db.add(simulation)
            self.db.flush()  # Get the ID
        
        # Update simulation fields
        if "title" in data:
            simulation.title = data["title"]
        if "description" in data:
            simulation.description = data["description"]
        if "student_role" in data:
            simulation.student_role = data["student_role"]
        if "learning_outcomes" in data:
            learning_outcomes = data["learning_outcomes"]
            if isinstance(learning_outcomes, str):
                # Convert string to list
                learning_outcomes = [item.strip() for item in learning_outcomes.split('\n') if item.strip()]
            simulation.learning_objectives = learning_outcomes
        
        # Update completion status
        completion_status = data.get("completion_status", {})
        if completion_status:
            simulation.name_completed = completion_status.get("name_completed", False)
            simulation.description_completed = completion_status.get("description_completed", False)
            simulation.student_role_completed = completion_status.get("student_role_completed", False)
            simulation.personas_completed = completion_status.get("personas_completed", False)
            simulation.scenes_completed = completion_status.get("scenes_completed", False)
            simulation.images_completed = completion_status.get("images_completed", False)
            simulation.learning_outcomes_completed = completion_status.get("learning_outcomes_completed", False)
            simulation.ai_enhancement_completed = completion_status.get("ai_enhancement_completed", False)
        
        # Save grading config
        if "grading_prompt" in data:
            simulation.grading_prompt = data["grading_prompt"]
        if "rubric_title" in data or "rubric_criteria" in data or "rubric_performance_levels" in data:
            grading_config = {}
            if "rubric_title" in data:
                grading_config["title"] = data["rubric_title"]
            if "rubric_criteria" in data:
                grading_config["criteria"] = data["rubric_criteria"]
            if "rubric_performance_levels" in data:
                grading_config["performance_levels"] = data["rubric_performance_levels"]
            simulation.grading_config = grading_config
        
        simulation.updated_at = datetime.utcnow()
        self.db.add(simulation)
        self.db.flush()
        
        # Save personas
        if "personas" in data and isinstance(data["personas"], list):
            # Get IDs of personas in the new data
            new_persona_ids = {
                persona_data.get("id") 
                for persona_data in data["personas"] 
                if persona_data.get("id")
            }
            
            # Soft delete personas that are not in the new data
            existing_personas = self.repository.get_simulation_personas(simulation.id)
            for persona in existing_personas:
                if persona.id not in new_persona_ids:
                    persona.deleted_at = datetime.utcnow()
            
            # Create/update personas
            for idx, persona_data in enumerate(data["personas"]):
                persona_id = persona_data.get("id")
                persona = None
                
                if persona_id:
                    # Only query if persona_id is a valid integer (not a temporary string ID from frontend)
                    # Frontend sends temporary IDs like "persona-1765519956424-0" for new personas
                    is_valid_int = False
                    if isinstance(persona_id, int):
                        is_valid_int = True
                    elif isinstance(persona_id, str) and persona_id.isdigit():
                        is_valid_int = True
                        persona_id = int(persona_id)  # Convert to int for query
                    
                    if is_valid_int:
                        # Try to find existing non-deleted persona
                        persona = self.db.query(SimulationPersona).filter(
                            SimulationPersona.id == persona_id,
                            SimulationPersona.scenario_id == simulation.id,
                            SimulationPersona.deleted_at.is_(None)
                        ).first()
                
                # Handle image URL - never save temp URLs, only S3 URLs
                image_url = persona_data.get("imageUrl")
                if image_url and _is_temporary_image_url(image_url):
                    # Don't save temp URL - will be uploaded by worker
                    image_url = None
                elif image_url and not _is_s3_url(image_url):
                    # If not S3 URL and not temp, assume it's invalid
                    image_url = None
                
                if not persona:
                    # Create new persona (either no ID provided, or ID provided but not found/deleted)
                    # Set all fields before flushing to avoid NOT NULL constraint errors
                    persona = SimulationPersona(
                        scenario_id=simulation.id,
                        name=persona_data.get("name", f"Persona {idx + 1}"),
                        role=persona_data.get("role", ""),  # role is required, use empty string as default
                        background=persona_data.get("background"),
                        correlation=persona_data.get("correlation"),
                        primary_goals=persona_data.get("primary_goals"),
                        personality_traits=persona_data.get("personality_traits"),
                        system_prompt=persona_data.get("systemPrompt"),
                        image_url=image_url  # Only S3 URLs or None
                    )
                    self.db.add(persona)
                    self.db.flush()
                    
                    # Temp URLs will be handled after commit via handle_image_uploads
                else:
                    # Update existing persona fields
                    if "name" in persona_data:
                        persona.name = persona_data["name"]
                    if "role" in persona_data:
                        persona.role = persona_data["role"]
                    if "background" in persona_data:
                        persona.background = persona_data["background"]
                    if "correlation" in persona_data:
                        persona.correlation = persona_data["correlation"]
                    if "primary_goals" in persona_data:
                        persona.primary_goals = persona_data["primary_goals"]
                    if "personality_traits" in persona_data:
                        persona.personality_traits = persona_data["personality_traits"]
                    if "systemPrompt" in persona_data:
                        persona.system_prompt = persona_data["systemPrompt"]
                    if "imageUrl" in persona_data:
                        # Only save S3 URLs, enqueue temp URLs (will check S3 in handle_image_uploads)
                        if _is_temporary_image_url(persona_data.get("imageUrl")):
                            persona.image_url = None  # Will be updated by worker after S3 check
                        elif _is_s3_url(persona_data.get("imageUrl")):
                            persona.image_url = persona_data.get("imageUrl")
                        else:
                            persona.image_url = None
                
                persona.updated_at = datetime.utcnow()
                self.db.add(persona)
        
        # Save scenes
        if "scenes" in data and isinstance(data["scenes"], list):
            # Delete existing scenes (hard delete for scenes)
            existing_scenes = self.repository.get_simulation_scenes(simulation.id)
            for scene in existing_scenes:
                self.db.delete(scene)
            
            # Create new scenes
            for idx, scene_data in enumerate(data["scenes"]):
                scene = SimulationScene(
                    scenario_id=simulation.id,
                    title=scene_data.get("title", f"Scene {idx + 1}"),
                    scene_order=scene_data.get("scene_order", idx + 1)  # Start at 1, not 0
                )
                
                if "description" in scene_data:
                    scene.description = scene_data["description"]
                if "user_goal" in scene_data:
                    scene.user_goal = scene_data["user_goal"]
                if "timeout_turns" in scene_data:
                    scene.timeout_turns = scene_data["timeout_turns"]
                if "success_metric" in scene_data:
                    scene.success_metric = scene_data["success_metric"]
                
                # Handle image URL - never save temp URLs, only S3 URLs
                image_url = scene_data.get("imageUrl") or scene_data.get("image_url")
                if image_url and _is_temporary_image_url(image_url):
                    # Don't save temp URL - will be uploaded by worker
                    scene.image_url = None
                elif image_url and _is_s3_url(image_url):
                    scene.image_url = image_url
                else:
                    scene.image_url = None
                
                self.db.add(scene)
                self.db.flush()  # Flush to get scene.id for persona associations
                
                # If we had a temp URL, it will be handled after commit in handle_image_uploads
                
                # Save scene-persona associations (involved personas)
                # Standard format: personas_involved is an array of persona names
                if "personas_involved" in scene_data and isinstance(scene_data["personas_involved"], list):
                    for persona_name in scene_data["personas_involved"]:
                        if not persona_name or not isinstance(persona_name, str):
                            continue
                        
                        # Look up persona by name
                        persona = self.db.query(SimulationPersona).filter(
                            SimulationPersona.name == persona_name,
                            SimulationPersona.scenario_id == simulation.id,
                            SimulationPersona.deleted_at.is_(None)
                        ).first()
                        
                        if persona:
                            # Insert into scene_personas association table
                            self.db.execute(
                                scene_personas.insert().values(
                                    scene_id=scene.id,
                                    persona_id=persona.id,
                                    involvement_level="participant"  # Default involvement level
                                )
                            )
        
        self.db.commit()
        
        # After commit, collect temp URLs and check S3 before enqueueing
        # This prevents duplicate uploads when personas/scenes are recreated with new IDs
        personas_to_upload = []
        scenes_to_upload = []
        
        # Collect personas with temp URLs from original data
        if "personas" in data and isinstance(data["personas"], list):
            saved_personas = self.repository.get_simulation_personas(simulation.id)
            persona_by_name = {p.name: p for p in saved_personas}
            
            for persona_data in data["personas"]:
                temp_url = persona_data.get("imageUrl")
                if temp_url and _is_temporary_image_url(temp_url):
                    persona_name = persona_data.get("name")
                    persona = persona_by_name.get(persona_name)
                    if persona and not persona.image_url:  # Only if image_url is None (temp URL was set to None)
                        personas_to_upload.append({
                            "persona_id": persona.id,
                            "scenario_id": simulation.id,
                            "temp_url": temp_url
                        })
        
        # Collect scenes with temp URLs from original data
        if "scenes" in data and isinstance(data["scenes"], list):
            saved_scenes = self.repository.get_simulation_scenes(simulation.id)
            # Match scenes by order (since scenes are recreated)
            for idx, scene_data in enumerate(data["scenes"]):
                if idx < len(saved_scenes):
                    scene = saved_scenes[idx]
                    temp_url = scene_data.get("imageUrl") or scene_data.get("image_url")
                    if temp_url and _is_temporary_image_url(temp_url) and not scene.image_url:
                        scenes_to_upload.append({
                            "scene_id": scene.id,
                            "scenario_id": simulation.id,
                            "temp_url": temp_url
                        })
        
        # Enqueue uploads via handle_image_uploads (which checks S3 first)
        # This ensures S3 check happens before enqueueing, preventing duplicates
        if personas_to_upload or scenes_to_upload:
            await self.handle_image_uploads(personas_to_upload, scenes_to_upload)
        
        logger.info(f"[SAVE] Successfully saved simulation {simulation.id}")
        return simulation
    
    async def publish_simulation(
        self,
        simulation_id: int
    ) -> Simulation:
        """Publish a simulation (make it available for assignment)."""
        simulation = self.repository.get_simulation_by_id(simulation_id)
        if not simulation:
            raise HTTPException(status_code=404, detail="Simulation not found")
        
        # Check upload status before publishing
        upload_status = get_upload_status(simulation_id)
        has_pending_uploads = upload_status["status"] == "uploading" and upload_status["pending"] > 0
        
        # Verify all images are in S3 (check personas and scenes)
        personas = self.repository.get_simulation_personas(simulation_id)
        scenes = self.repository.get_simulation_scenes(simulation_id)
        
        missing_images = []
        images_updated_from_s3 = []
        
        for persona in personas:
            # Check if image_url is None (still uploading) or is a temp URL
            if not persona.image_url:
                # Redis might show pending, but check if image actually exists in S3
                # (worker may have processed but Redis update failed)
                s3_url = await check_image_exists_in_s3(simulation_id, "persona", persona.id)
                if s3_url:
                    # Image exists in S3 but DB not updated - fix it
                    persona.image_url = s3_url
                    self.db.add(persona)
                    images_updated_from_s3.append(f"Persona '{persona.name}'")
                    logger.warning(f"[PUBLISH] Persona '{persona.name}' image exists in S3 but DB was None - updated database")
                else:
                    # Image doesn't exist - worker not running or failed
                    missing_images.append(f"Persona '{persona.name}' image still uploading (not found in S3)")
            elif _is_temporary_image_url(persona.image_url):
                missing_images.append(f"Persona '{persona.name}' image not uploaded to S3")
        
        for scene in scenes:
            # Check if image_url is None (still uploading) or is a temp URL
            if not scene.image_url:
                # Redis might show pending, but check if image actually exists in S3
                s3_url = await check_image_exists_in_s3(simulation_id, "scene", scene.id)
                if s3_url:
                    # Image exists in S3 but DB not updated - fix it
                    scene.image_url = s3_url
                    self.db.add(scene)
                    images_updated_from_s3.append(f"Scene '{scene.title}'")
                    logger.warning(f"[PUBLISH] Scene '{scene.title}' image exists in S3 but DB was None - updated database")
                else:
                    # Image doesn't exist - worker not running or failed
                    missing_images.append(f"Scene '{scene.title}' image still uploading (not found in S3)")
            elif _is_temporary_image_url(scene.image_url):
                missing_images.append(f"Scene '{scene.title}' image not uploaded to S3")
        
        # Commit any database updates from S3 checks
        if images_updated_from_s3:
            self.db.commit()
            logger.info(f"[PUBLISH] Updated {len(images_updated_from_s3)} images from S3: {', '.join(images_updated_from_s3)}")
        
        # If we still have missing images, fail loudly
        if missing_images:
            error_msg = f"Cannot publish simulation: {len(missing_images)} images not ready. {', '.join(missing_images[:3])}"
            if has_pending_uploads:
                error_msg += f" (Redis shows {upload_status['pending']} pending uploads - worker may not be running)"
            raise HTTPException(
                status_code=400,
                detail=error_msg
            )
        
        # If Redis shows pending but all images are in S3, log warning
        if has_pending_uploads:
            logger.warning(f"[PUBLISH] Redis shows {upload_status['pending']} pending uploads but all images exist in S3 - Redis status may be stale")
        
        simulation.is_draft = False
        simulation.is_public = True
        simulation.status = "active"
        simulation.updated_at = datetime.utcnow()
        
        self.db.add(simulation)
        self.db.commit()
        
        logger.info(f"[PUBLISH] Published simulation {simulation_id}")
        return simulation
    
    def update_simulation_status(
        self,
        simulation_id: int,
        status: str,
        user_id: Optional[int] = None
    ) -> Simulation:
        """Update simulation status (draft, active, archived, creating)."""
        logger.info(f"[STATUS_UPDATE] Updating simulation {simulation_id} to status {status}")
        
        simulation = self.repository.get_simulation_by_id(simulation_id)
        if not simulation:
            raise HTTPException(status_code=404, detail="Simulation not found")
        
        # Check permissions - user can only update their own simulations
        if user_id and simulation.created_by != user_id:
            raise HTTPException(
                status_code=403,
                detail="You can only update simulations you created"
            )
        
        # Validate status
        valid_statuses = ["draft", "active", "archived", "creating"]
        if status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )
        
        # Update status and related fields
        simulation.status = status
        
        if status == "active":
            # Publishing: make it available for assignment
            simulation.is_draft = False
            simulation.is_public = True
        elif status == "draft":
            # Unpublishing: make it unavailable
            simulation.is_draft = True
            simulation.is_public = False
        # For "archived" and "creating", keep existing is_draft and is_public values
        
        simulation.updated_at = datetime.utcnow()
        
        self.db.add(simulation)
        self.db.commit()
        
        logger.info(f"[STATUS_UPDATE] Successfully updated simulation {simulation_id} to {status}")
        return simulation
    
    def delete_simulation(
        self,
        simulation_id: int,
        user_id: Optional[int] = None
    ) -> bool:
        """Delete a simulation (soft delete)."""
        logger.info(f"[DELETE] Deleting simulation {simulation_id}, user_id: {user_id}")
        
        success = self.repository.delete_simulation(simulation_id, user_id)
        if not success:
            if not self.repository.get_simulation_by_id(simulation_id):
                raise HTTPException(status_code=404, detail="Simulation not found")
            else:
                raise HTTPException(status_code=403, detail="You can only delete simulations you created")
        
        logger.info(f"[DELETE] Successfully deleted simulation {simulation_id}")
        return True
