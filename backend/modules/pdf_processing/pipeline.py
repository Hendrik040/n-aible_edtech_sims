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

from modules.auth.models import User

from .parser_service import parser_service
from .ai_extraction_service import ai_extraction_service
from .repository import get_repository
from .progress_service import progress_manager

logger = logging.getLogger(__name__)

# TODO: Fix image_generation import - needs to be moved to appropriate module
try:
    from api.image_generation import generate_scenes_with_images, generate_personas_with_avatars
except ImportError:
    # Placeholder functions if image_generation doesn't exist yet
    async def generate_scenes_with_images(scenes, session_id=None):
        return scenes
    
    async def generate_personas_with_avatars(personas):
        return personas


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
        Returns personas data and creates a scenario.
        """
        logger.info("[PIPELINE] Starting fast autofill processing...")
        start_time = time.time()
        
        try:
            # Create scenario record immediately with "creating" status
            scenario = self.repository.create_scenario(
                user_id=self.current_user.id if self.current_user else None,
                filename=file.filename or "Uploaded PDF"
            )
            scenario_id = scenario.id
            
            logger.info(f"[PIPELINE] Created scenario {scenario_id} with status '{scenario.status}'")
            
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
            logger.info(f"[PIPELINE] Saving autofill data to scenario {scenario_id}...")
            self.repository.save_autofill_data(scenario_id, personas_result)
            
            total_time = time.time() - start_time
            logger.info(f"[PIPELINE] Fast autofill completed in {total_time:.2f}s")
            
            return {
                "status": "fast_autofill_completed",
                "processing_time": total_time,
                "scenario_id": scenario_id,
                "title": personas_result.get("title", title),
                "student_role": personas_result.get("student_role", "Business Manager"),
                "personas": key_figures,
                "key_figures": key_figures
            }
            
        except Exception as e:
            logger.error(f"[PIPELINE] Fast autofill failed: {str(e)}")
            # Update scenario status to draft on error if it was created
            if 'scenario_id' in locals():
                self.repository.update_scenario_status_to_draft(scenario_id)
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
        
        scenario_id = None
        
        try:
            # Create scenario immediately
            scenario = self.repository.create_scenario(
                user_id=self.current_user.id if self.current_user else None,
                filename=file.filename or "Uploaded PDF"
            )
            scenario_id = scenario.id
            
            # Store scenario_id in progress data
            if session_id:
                if session_id not in progress_manager.progress_data:
                    progress_manager.progress_data[session_id] = {}
                progress_manager.progress_data[session_id]["scenario_id"] = scenario_id
            
            logger.info(f"[PIPELINE] Created scenario {scenario_id}")
            
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
                scenes_result = await generate_scenes_with_images(scenes_result, session_id)
            
            progress_manager.update_progress(session_id, "processing", 85, "Generating avatars...")
            
            # Step 5: Generate avatars for personas
            key_figures = personas_result.get("key_figures", [])
            if key_figures:
                key_figures = await generate_personas_with_avatars(key_figures)
            
            progress_manager.update_progress(session_id, "processing", 95, "Saving to database...")
            
            # Combine all results
            ai_result = {
                "title": personas_result.get("title", title),
                "description": personas_result.get("description", ""),
                "student_role": personas_result.get("student_role", "Business Manager"),
                "key_figures": key_figures,
                "scenes": scenes_result,
                "learning_outcomes": learning_outcomes
            }
            
            # Save to database
            self.repository.save_full_pdf_data(scenario_id, ai_result)
            
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
                "scenario_id": scenario_id,
                "message": "PDF parsed successfully"
            }
            
        except Exception as e:
            logger.error(f"[PIPELINE] Full processing failed: {str(e)}")
            
            # Update scenario status on error
            if scenario_id:
                self.repository.update_scenario_status_to_draft(scenario_id)
            
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
                "scenario_id": None
            }
            
        except Exception as e:
            logger.error(f"[PIPELINE] Full processing failed: {str(e)}")
            raise


# Helper function to create pipeline instance
def get_pipeline(db: Session, current_user: Optional[User] = None) -> PDFProcessingPipeline:
    """Get a pipeline instance"""
    return PDFProcessingPipeline(db, current_user)
