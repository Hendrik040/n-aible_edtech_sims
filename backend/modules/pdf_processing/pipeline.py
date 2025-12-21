"""
PDF processing pipeline that orchestrates all services.
Main orchestration logic extracted from api/parse_pdf.py
"""
import time
import asyncio
import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import UploadFile

from common.db.models import User

from .parser_service import parser_service
from .ai_extraction_service import ai_extraction_service
from .repository import get_repository
from .progress_service import progress_manager

logger = logging.getLogger(__name__)

from .image_generation_service import generate_scenes_with_images, generate_personas_with_avatars
from modules.publishing.service import PublishingService
from modules.publishing.tasks import is_temporary_image_url as _is_temporary_image_url


class PDFProcessingPipeline:
    """Pipeline for orchestrating PDF processing"""
    
    def __init__(self, db: Session, current_user: Optional[User] = None):
        self.db = db
        self.current_user = current_user
        self.repository = get_repository(db)
        self.parser = parser_service
        self.ai_service = ai_extraction_service
    
    async def process_fast_autofill(
        self, 
        file: UploadFile
    ) -> Dict[str, Any]:
        """
        Fast autofill processing - only extracts personas for quick form population.
        Returns personas data and creates a simulation.
        """
        logger.info("[PIPELINE] Starting fast autofill processing...")
        start_time = time.time()
        
        try:
            # Create simulation record immediately with "creating" status
            simulation = self.repository.create_simulation(
                user_id=self.current_user.id if self.current_user else None,
                filename=file.filename or "Uploaded PDF"
            )
            simulation_id = simulation.id
            
            logger.info(f"[PIPELINE] Created simulation {simulation_id} with status '{simulation.status}'")
            
            # Parse file
            logger.info(f"[PIPELINE] Parsing {file.filename}...")
            main_markdown = await self.parser.parse_file_flexible(file)
            
            # Preprocess content
            logger.info("[PIPELINE] Preprocessing content...")
            preprocessed = self.ai_service.preprocess_content(main_markdown)
            title = preprocessed["title"]
            content = preprocessed["cleaned_content"]
            
            # Fast AI call for personas only
            logger.info("[PIPELINE] Extracting personas...")
            personas_result = await self.ai_service.extract_personas_fast(content, title)
            
            # Generate avatars for personas
            key_figures = personas_result.get("key_figures", [])
            if key_figures:
                logger.info("[PIPELINE] Generating avatars for personas...")
                key_figures = await generate_personas_with_avatars(key_figures)
                personas_result["key_figures"] = key_figures
            
            # Save autofill data to database
            logger.info(f"[PIPELINE] Saving autofill data to simulation {simulation_id}...")
            self.repository.save_autofill_data(simulation_id, personas_result)
            
            total_time = time.time() - start_time
            logger.info(f"[PIPELINE] Fast autofill completed in {total_time:.2f}s")
            
            return {
                "status": "fast_autofill_completed",
                "processing_time": total_time,
                "simulation_id": simulation_id,
                "title": personas_result.get("title", title),
                "student_role": personas_result.get("student_role", "Business Manager"),
                "personas": key_figures,
                "key_figures": key_figures
            }
            
        except Exception as e:
            logger.error(f"[PIPELINE] Fast autofill failed: {str(e)}")
            # Update simulation status to draft on error if it was created
            if 'simulation_id' in locals():
                self.repository.update_simulation_status_to_draft(simulation_id)
            raise
    
    async def process_full_with_progress(
        self,
        file: UploadFile,
        session_id: str,
        context_files: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Full PDF processing with real-time progress updates.
        Extracts personas, scenes, learning outcomes, and generates images.
        """
        logger.info(f"[PIPELINE] Starting full processing with progress for session {session_id}")
        start_time = time.time()
        
        simulation_id = None
        
        try:
            # Create simulation immediately
            simulation = self.repository.create_simulation(
                user_id=self.current_user.id if self.current_user else None,
                filename=file.filename or "Uploaded PDF"
            )
            simulation_id = simulation.id
            
            # Store simulation_id in progress data
            if session_id:
                progress_manager.set_simulation_id(session_id, simulation_id)
            
            logger.info(f"[PIPELINE] Created simulation {simulation_id}")
            
            # Initialize progress
            progress_manager.update_progress(session_id, "upload", 0, "Starting file processing...")
            
            # Read file contents
            file_contents = await file.read()
            progress_manager.update_progress(session_id, "upload", 50, "File uploaded, starting parsing...")
            
            # Parse main file
            main_markdown = await self.parser.parse_pdf_contents(
                file_contents, 
                file.filename, 
                file.content_type, 
                session_id,
                progress_manager
            )
            
            # Parse context files if provided
            context_text = ""
            if context_files:
                logger.info(f"[PIPELINE] Processing {len(context_files)} context files...")
                # TODO: Implement context file processing
            
            # Preprocess content
            logger.info("[PIPELINE] Preprocessing content...")
            preprocessed = self.ai_service.preprocess_content(main_markdown)
            title = preprocessed["title"]
            cleaned_content = preprocessed["cleaned_content"]
            
            # Send title update
            if session_id:
                progress_manager.send_field_update(session_id, "title", title, "Extracted document title")
            
            # Prepare combined content
            if context_text.strip():
                combined_content = f"""
IMPORTANT CONTEXT FILES:
{context_text}

MAIN CASE STUDY CONTENT:
{cleaned_content}
"""
            else:
                combined_content = cleaned_content
            
            # AI processing pipeline
            logger.info("[PIPELINE] Starting AI processing...")
            progress_manager.update_progress(session_id, "processing", 20, "Extracting personas...")
            
            # Step 1: Extract personas
            personas_result = await self.ai_service.extract_personas_and_key_figures(
                combined_content, title, session_id
            )
            
            # Send description update
            if session_id:
                progress_manager.send_field_update(
                    session_id, 
                    "description", 
                    personas_result.get("description", ""), 
                    "Extracted document description"
                )
                progress_manager.send_field_update(
                    session_id, 
                    "student_role", 
                    personas_result.get("student_role", ""), 
                    "Identified student role"
                )
            
            progress_manager.update_progress(session_id, "processing", 40, "Generating scenes...")
            
            # Step 2: Generate scenes with persona context
            scenes_result = await self.ai_service.generate_scenes(
                combined_content, title, session_id, personas_result
            )
            
            progress_manager.update_progress(session_id, "processing", 60, "Generating learning outcomes...")
            
            # Step 3: Generate learning outcomes
            learning_outcomes = await self.ai_service.generate_learning_outcomes(
                combined_content, title, session_id
            )
            
            progress_manager.update_progress(session_id, "processing", 70, "Generating images...")
            
            # Step 4: Generate images for scenes
            if scenes_result:
                scenes_result = await generate_scenes_with_images(scenes_result, session_id, simulation_id)
            
            progress_manager.update_progress(session_id, "processing", 85, "Generating avatars...")
            
            # Step 5: Generate avatars for personas
            key_figures = personas_result.get("key_figures", [])
            if key_figures:
                key_figures = await generate_personas_with_avatars(key_figures)
            
            progress_manager.update_progress(session_id, "processing", 95, "Saving to database...")
            
            # Combine all results for saving
            ai_result = {
                "title": personas_result.get("title", title),
                "description": personas_result.get("description", ""),
                "student_role": personas_result.get("student_role", "Business Manager"),
                "key_figures": key_figures,
                "scenes": scenes_result,
                "learning_outcomes": learning_outcomes
            }
            
            # Save to database FIRST to get IDs for scenes and personas
            self.repository.save_full_pdf_data(simulation_id, ai_result)
            
            # Now query database to get saved scenes/personas with their IDs
            # Import models locally to avoid circular imports
            from common.db.models import SimulationScene, SimulationPersona
            
            # Create PublishingService to handle upload queue
            publishing_service = PublishingService(self.db)
            
            # Find scenes with temporary image URLs (now they have database IDs)
            # NOTE: Use key 'scenario_id' to match publishing.tasks.handle_image_uploads expectations.
            scenes_to_upload = []
            saved_scenes = self.db.query(SimulationScene).filter(
                SimulationScene.simulation_id == simulation_id,
                SimulationScene.deleted_at.is_(None)
            ).all()
            for scene in saved_scenes:
                if scene.image_url and _is_temporary_image_url(scene.image_url):
                    scenes_to_upload.append({
                        "scene_id": scene.id,
                        "scenario_id": simulation_id,
                        "temp_url": scene.image_url
                    })
            
            # Find personas with temporary image URLs (now they have database IDs)
            # NOTE: Use key 'scenario_id' to match publishing.tasks.handle_image_uploads expectations.
            personas_to_upload = []
            saved_personas = self.db.query(SimulationPersona).filter(
                SimulationPersona.simulation_id == simulation_id,
                SimulationPersona.deleted_at.is_(None)
            ).all()
            for persona in saved_personas:
                if persona.image_url and _is_temporary_image_url(persona.image_url):
                    personas_to_upload.append({
                        "persona_id": persona.id,
                        "scenario_id": simulation_id,
                        "temp_url": persona.image_url
                    })
            
            # Enqueue uploads (non-blocking)
            if personas_to_upload or scenes_to_upload:
                await publishing_service.handle_image_uploads(personas_to_upload, scenes_to_upload)
                logger.info(f"[PIPELINE] Enqueued {len(personas_to_upload)} persona and {len(scenes_to_upload)} scene uploads for simulation {simulation_id}")
            
            # Send final field updates
            if session_id:
                await asyncio.sleep(0.5)
                progress_manager.send_field_update(session_id, "personas", key_figures, f"Extracted {len(key_figures)} personas")
                await asyncio.sleep(0.5)
                progress_manager.send_field_update(session_id, "scenes", scenes_result, f"Generated {len(scenes_result)} scenes")
                await asyncio.sleep(0.5)
                progress_manager.send_field_update(session_id, "learning_outcomes", learning_outcomes, f"Generated {len(learning_outcomes)} outcomes")
                await asyncio.sleep(0.5)
                progress_manager.send_field_update(session_id, "ai_enhancement_complete", True, "AI enhancement completed")
            
            # Mark as complete
            progress_manager.complete_processing(session_id, {
                "success": True,
                "data": ai_result,
                "message": "PDF processing completed successfully"
            })
            
            total_time = time.time() - start_time
            logger.info(f"[PIPELINE] Full processing completed in {total_time:.2f}s")
            
            return {
                "success": True,
                "data": ai_result,
                "session_id": session_id,
                "simulation_id": simulation_id,
                "message": "PDF parsed successfully"
            }
            
        except Exception as e:
            logger.error(f"[PIPELINE] Full processing failed: {str(e)}")
            
            # Update simulation status on error
            if simulation_id:
                self.repository.update_simulation_status_to_draft(simulation_id)
            
            # Send error to progress manager
            if session_id:
                progress_manager.error_processing(session_id, f"PDF processing failed: {str(e)}")
            
            raise
    
    async def process_full(
        self,
        file: UploadFile,
        context_files: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Full PDF processing without progress updates (for direct API calls).
        """
        logger.info("[PIPELINE] Starting full processing without progress...")
        start_time = time.time()
        
        try:
            # Parse file
            main_markdown = await self.parser.parse_file_flexible(file)
            
            # Parse context files if provided
            context_text = ""
            if context_files:
                # TODO: Implement context file processing
                pass
            
            # Preprocess content
            preprocessed = self.ai_service.preprocess_content(main_markdown)
            title = preprocessed["title"]
            cleaned_content = preprocessed["cleaned_content"]
            
            # Prepare combined content
            if context_text.strip():
                combined_content = f"""
IMPORTANT CONTEXT FILES:
{context_text}

MAIN CASE STUDY CONTENT:
{cleaned_content}
"""
            else:
                combined_content = cleaned_content
            
            # AI processing - parallel execution
            logger.info("[PIPELINE] Starting parallel AI processing...")
            
            # Create tasks for parallel execution
            personas_task = self.ai_service.extract_personas_and_key_figures(combined_content, title)
            
            # Wait for personas first so scenes can use them
            personas_result = await personas_task
            
            # Now run scenes and learning outcomes in parallel
            tasks = [
                self.ai_service.generate_scenes(combined_content, title, None, personas_result),
                self.ai_service.generate_learning_outcomes(combined_content, title)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            scenes_result = results[0] if not isinstance(results[0], Exception) else []
            learning_outcomes = results[1] if not isinstance(results[1], Exception) else []
            
            # Combine results
            ai_result = {
                "title": personas_result.get("title", title),
                "description": personas_result.get("description", ""),
                "student_role": personas_result.get("student_role", "Business Manager"),
                "key_figures": personas_result.get("key_figures", []),
                "scenes": scenes_result,
                "learning_outcomes": learning_outcomes
            }
            
            total_time = time.time() - start_time
            logger.info(f"[PIPELINE] Full processing completed in {total_time:.2f}s")
            
            return {
                "status": "completed",
                "ai_result": ai_result,
                "simulation_id": None
            }
            
        except Exception as e:
            logger.error(f"[PIPELINE] Full processing failed: {str(e)}")
            raise


# Helper function to create pipeline instance
def get_pipeline(db: Session, current_user: Optional[User] = None) -> PDFProcessingPipeline:
    """Get a pipeline instance"""
    return PDFProcessingPipeline(db, current_user)
