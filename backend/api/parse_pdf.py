import os
import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form
from sqlalchemy.orm import Session
import httpx
import openai
from typing import List, Optional
# PyPDF2 removed - using LlamaParse for all PDF parsing
from datetime import datetime
import unicodedata
from functools import wraps
import time

from database.connection import get_db, settings
from database.models import Scenario, ScenarioPersona, ScenarioScene, ScenarioFile, scene_personas
from services.embedding_service import embedding_service

# =============================================================================
# IMAGE GENERATION: ENABLED
# =============================================================================
# Image generation is currently enabled and will generate DALL-E images for each scene.
# This will consume API credits (~$0.16-0.24 per PDF for 4-6 images).
# 
# To disable image generation to reduce costs:
# 1. Comment out the image generation code block (lines ~777-794)
# 2. Add "image_urls = [""] * len(scenes)" as a temporary replacement
# 3. Update the debug print statement to show "Disabled (API cost reduction)"
# =============================================================================

LLAMAPARSE_API_KEY = settings.llamaparse_api_key
OPENAI_API_KEY = settings.openai_api_key
from utilities.secure_logging import secure_print_api_key_status
from utilities.debug_logging import debug_log
from utilities.rate_limiter import async_retry
from .pdf_progress import progress_manager

secure_print_api_key_status("LLAMAPARSE_API_KEY", LLAMAPARSE_API_KEY)
secure_print_api_key_status("OPENAI_API_KEY", OPENAI_API_KEY)

router = APIRouter()

# Performance optimization constants
MAX_CONCURRENT_LLAMAPARSE = 3  # Limit concurrent LlamaParse requests
MAX_CONCURRENT_OPENAI = 2      # Limit concurrent OpenAI requests
MAX_CONCURRENT_IMAGES = 4      # Limit concurrent image generations

# Thread pool for CPU-bound operations
CPU_EXECUTOR = ThreadPoolExecutor(max_workers=4)

LLAMAPARSE_API_URL = "https://api.cloud.llamaindex.ai/api/parsing/upload"
LLAMAPARSE_JOB_URL = "https://api.cloud.llamaindex.ai/api/parsing/job"

def async_retry(retries: int = 3, delay: float = 1.0):
    """Decorator for async retry logic with exponential backoff"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < retries - 1:
                        wait_time = delay * (2 ** attempt)
                        print(f"[RETRY] {func.__name__} attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        print(f"[ERROR] {func.__name__} failed after {retries} attempts: {e}")
            raise last_exception
        return wrapper
    return decorator

async def extract_text_from_context_files(context_files: List[UploadFile]) -> str:
    """Extract text from context files using LlamaParse for PDFs and direct extraction for text files"""
    context_texts = []
    for file in context_files:
        filename = file.filename.lower()
        if filename.endswith('.pdf'):
            try:
                # Use LlamaParse for PDF files
                text = await parse_with_llamaparse(file)
                context_texts.append(f"[Context File: {file.filename}]\n{text.strip()}\n")
            except Exception as e:
                context_texts.append(f"[Context File: {file.filename}]\n[Could not extract PDF text: {e}]\n")
        elif filename.endswith('.txt'):
            try:
                contents = await file.read()
                text = contents.decode('utf-8', errors='ignore')
                context_texts.append(f"[Context File: {file.filename}]\n{text.strip()}\n")
            except Exception as e:
                context_texts.append(f"[Context File: {file.filename}]\n[Could not extract TXT text: {e}]\n")
        else:
            context_texts.append(f"[Context File: {file.filename}]\n[Unsupported file type]\n")
    return "\n".join(context_texts)

async def parse_file_flexible(file: UploadFile, session_id: str = None) -> str:
    """Parse a file using the appropriate method based on file type."""
    filename = file.filename.lower() if file.filename else ""
    
    # For PDF files, use LlamaParse
    if filename.endswith('.pdf') or file.content_type == "application/pdf":
        return await parse_with_llamaparse(file, session_id)
    
    # For text-based files, extract text directly
    elif filename.endswith(('.txt', '.md')) or file.content_type in ["text/plain", "text/markdown"]:
        return await extract_text_from_file(file)
    
    # For Word documents, try to extract text (basic implementation)
    elif filename.endswith(('.doc', '.docx')) or file.content_type in ["application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
        return await extract_text_from_file(file)
    
    else:
        # Fallback: try LlamaParse for other file types
        debug_log(f"Unknown file type {file.content_type}, trying LlamaParse as fallback...")
        return await parse_with_llamaparse(file)

async def extract_text_from_file(file: UploadFile) -> str:
    """Extract text from text-based files (TXT, MD, etc.)"""
    try:
        contents = await file.read()
        text = contents.decode('utf-8', errors='ignore')
        return f"[File: {file.filename}]\n{text.strip()}\n"
    except Exception as e:
        return f"[File: {file.filename}]\n[Could not extract text: {e}]\n"

# Global semaphore for LlamaParse requests
_llamaparse_semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLAMAPARSE)

@async_retry(retries=3, delay=2.0)
async def parse_with_llamaparse(file: UploadFile, session_id: str = None) -> str:
    """Send a file to LlamaParse and return the parsed markdown content with rate limiting."""
    if not LLAMAPARSE_API_KEY:
        raise HTTPException(status_code=500, detail="LlamaParse API key not configured.")
    
    async with _llamaparse_semaphore:  # Rate limiting
        debug_log(f"[OPTIMIZED] Starting LlamaParse for {file.filename}")
        start_time = time.time()
        
        try:
            # Update progress: Starting upload
            if session_id:
                progress_manager.update_progress(session_id, "upload", 10, "Reading file...")
            
            # Read file contents once and store them
            contents = await file.read()
            headers = {"Authorization": f"Bearer {LLAMAPARSE_API_KEY}"}
            files = {"file": (file.filename, contents, file.content_type)}
            
            # Update progress: File read, starting upload
            if session_id:
                progress_manager.update_progress(session_id, "upload", 50, "Uploading to LlamaParse...")
            
            # Use optimized HTTP client with connection pooling
            limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
            timeout = httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=120.0)
            
            async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
                try:
                    # Upload with retry logic built into decorator
                    upload_response = await client.post(LLAMAPARSE_API_URL, headers=headers, files=files)
                    upload_response.raise_for_status()
                    
                    # Update progress: Upload complete
                    if session_id:
                        progress_manager.update_progress(session_id, "upload", 100, "Upload complete")
                    
                    job_data = upload_response.json()
                    job_id = job_data.get("id") or job_data.get("job_id") or job_data.get("jobId")
                    
                    if not job_id:
                        raise HTTPException(status_code=500, detail=f"No job ID in LlamaParse response")
                    
                    debug_log(f"[OPTIMIZED] Got job ID: {job_id} for {file.filename}")
                    
                    # Update progress: Starting processing
                    if session_id:
                        progress_manager.update_progress(session_id, "processing", 5, "Processing document...")
                    
                    # Optimized polling with exponential backoff
                    wait_times = [1, 2, 3, 5, 5, 5]  # Faster initial polling
                    max_polls = 40  # Reduced from 60
                    
                    for attempt in range(max_polls):
                        status_response = await client.get(f"{LLAMAPARSE_JOB_URL}/{job_id}", headers=headers)
                        status_response.raise_for_status()
                        status_data = status_response.json()
                        
                        # Update progress based on attempt number
                        if session_id:
                            processing_progress = min(5 + (attempt * 2), 95)  # Gradually increase from 5% to 95%
                            progress_manager.update_progress(
                                session_id, 
                                "processing", 
                                processing_progress, 
                                f"Processing document... (attempt {attempt + 1}/{max_polls})",
                                {"job_id": job_id, "attempt": attempt + 1}
                            )
                        
                        status = status_data.get("status")
                        if status in ["COMPLETED", "SUCCESS"]:
                            debug_log(f"[OPTIMIZED] Job {job_id} completed in {time.time() - start_time:.2f}s")
                            
                            # Update progress: Processing complete, retrieving results
                            if session_id:
                                progress_manager.update_progress(session_id, "processing", 100, "Processing complete, retrieving results...")
                            
                            # Try multiple result formats in parallel
                            result_tasks = [
                                _get_llamaparse_result(client, job_id, "markdown", headers),
                                _get_llamaparse_result(client, job_id, "text", headers)
                            ]
                            
                            results = await asyncio.gather(*result_tasks, return_exceptions=True)
                            
                            # Use first successful result
                            for result in results:
                                if isinstance(result, str) and result.strip():
                                    debug_log(f"[OPTIMIZED] Retrieved result for {file.filename}, length: {len(result)}")
                                    return result
                            
                            # Fallback to status_data
                            if "parsed_document" in status_data:
                                parsed_doc = status_data["parsed_document"]
                                if isinstance(parsed_doc, dict) and "text" in parsed_doc:
                                    return parsed_doc["text"]
                            
                            return ""
                            
                        elif status == "FAILED":
                            error_msg = status_data.get("error", "Unknown error")
                            if session_id:
                                progress_manager.error_processing(session_id, f"LlamaParse job failed: {error_msg}")
                            raise HTTPException(status_code=500, detail=f"LlamaParse job failed: {error_msg}")
                        
                        # Dynamic wait time
                        wait_time = wait_times[min(attempt, len(wait_times) - 1)]
                        await asyncio.sleep(wait_time)
                    
                    if session_id:
                        progress_manager.error_processing(session_id, f"LlamaParse job timed out for {file.filename}")
                    raise HTTPException(status_code=500, detail=f"LlamaParse job timed out for {file.filename}")
                    
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:  # Rate limited
                        await asyncio.sleep(5)  # Wait longer for rate limits
                        raise e  # Let retry decorator handle it
                    raise HTTPException(status_code=e.response.status_code, detail=f"LlamaParse API error: {e}")
                    
        except Exception as e:
            debug_log(f"[ERROR] LlamaParse failed for {file.filename}: {str(e)}")
            raise

async def _get_llamaparse_result(client: httpx.AsyncClient, job_id: str, result_type: str, headers: dict) -> str:
    """Helper to get LlamaParse result in specific format"""
    try:
        if result_type == "markdown":
            response = await client.get(f"{LLAMAPARSE_JOB_URL}/{job_id}/result/markdown", headers=headers)
        else:
            response = await client.get(f"{LLAMAPARSE_JOB_URL}/{job_id}/result", headers=headers)
        
        response.raise_for_status()
        
        if result_type == "markdown":
            return response.text
        else:
            data = response.json()
            return data.get("text", "")
            
    except Exception as e:
        debug_log(f"Failed to get {result_type} result: {e}")
        return ""

@router.post("/api/parse-pdf-fast-autofill/")
async def parse_pdf_fast_autofill(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """FAST endpoint specifically for autofill - returns only personas, no images or scenes"""
    debug_log("[FAST_AUTOFILL] Starting fast autofill processing...")
    start_time = time.time()
    
    if not LLAMAPARSE_API_KEY:
        raise HTTPException(status_code=500, detail="LlamaParse API key not configured.")
    
    try:
        # 1. Fast file parsing (no context files for speed)
        debug_log(f"[FAST_AUTOFILL] Parsing {file.filename}...")
        main_markdown = await parse_file_flexible(file)
        
        # 2. Quick preprocessing
        preprocessed = preprocess_case_study_content(main_markdown)
        title = preprocessed["title"]
        content = preprocessed["cleaned_content"]
        
        # 3. FAST AI call with minimal prompt
        debug_log("[FAST_AUTOFILL] Extracting personas with streamlined AI call...")
        personas_result = await _fast_persona_extraction(content, title)
        
        total_time = time.time() - start_time
        debug_log(f"[FAST_AUTOFILL] Completed in {total_time:.2f}s")
        
        return {
            "status": "fast_autofill_completed",
            "processing_time": total_time,
            "title": personas_result.get("title", title),
            "student_role": personas_result.get("student_role", "Business Manager"),
            "personas": personas_result.get("key_figures", []),
            "key_figures": personas_result.get("key_figures", [])
        }
        
    except Exception as e:
        debug_log(f"[FAST_AUTOFILL_ERROR] {str(e)}")
        # Return fallback personas immediately
        fallback = _create_fallback_result(title or "Business Case", "")
        return {
            "status": "fast_autofill_fallback",
            "processing_time": time.time() - start_time,
            "title": fallback["title"],
            "student_role": fallback["student_role"],
            "personas": fallback["key_figures"],
            "key_figures": fallback["key_figures"]
        }

@router.get("/api/get-default-personas/")
async def get_default_personas():
    """INSTANT endpoint for default personas - no file processing required"""
    return {
        "status": "instant_fallback",
        "processing_time": 0.001,
        "title": "Business Case Study",
        "student_role": "Business Manager",
        "personas": [
            {
                "name": "Senior Executive",
                "role": "Executive Leader", 
                "background": "Experienced leader with strategic oversight and decision-making authority.",
                "primary_goals": ["Drive strategic growth", "Ensure organizational success", "Manage stakeholder relationships"],
                "personality_traits": {"analytical": 8, "creative": 6, "assertive": 7, "collaborative": 7, "detail_oriented": 8}
            },
            {
                "name": "Operations Manager",
                "role": "Operations Lead",
                "background": "Operational expert focused on day-to-day execution and process optimization.",
                "primary_goals": ["Optimize processes", "Ensure efficiency", "Manage operational resources"],
                "personality_traits": {"analytical": 9, "creative": 4, "assertive": 6, "collaborative": 8, "detail_oriented": 9}
            },
            {
                "name": "Financial Analyst",
                "role": "Finance Professional",
                "background": "Financial expert responsible for budget analysis and financial planning.",
                "primary_goals": ["Ensure financial health", "Analyze investment opportunities", "Manage risk"],
                "personality_traits": {"analytical": 10, "creative": 3, "assertive": 5, "collaborative": 6, "detail_oriented": 10}
            },
            {
                "name": "Marketing Director",
                "role": "Marketing Lead",
                "background": "Marketing professional focused on brand strategy and customer engagement.",
                "primary_goals": ["Build brand awareness", "Drive customer acquisition", "Develop marketing strategies"],
                "personality_traits": {"analytical": 6, "creative": 9, "assertive": 7, "collaborative": 8, "detail_oriented": 6}
            }
        ],
        "key_figures": [
            {
                "name": "Senior Executive",
                "role": "Executive Leader", 
                "background": "Experienced leader with strategic oversight and decision-making authority.",
                "primary_goals": ["Drive strategic growth", "Ensure organizational success", "Manage stakeholder relationships"],
                "personality_traits": {"analytical": 8, "creative": 6, "assertive": 7, "collaborative": 7, "detail_oriented": 8}
            },
            {
                "name": "Operations Manager",
                "role": "Operations Lead",
                "background": "Operational expert focused on day-to-day execution and process optimization.",
                "primary_goals": ["Optimize processes", "Ensure efficiency", "Manage operational resources"],
                "personality_traits": {"analytical": 9, "creative": 4, "assertive": 6, "collaborative": 8, "detail_oriented": 9}
            },
            {
                "name": "Financial Analyst",
                "role": "Finance Professional",
                "background": "Financial expert responsible for budget analysis and financial planning.",
                "primary_goals": ["Ensure financial health", "Analyze investment opportunities", "Manage risk"],
                "personality_traits": {"analytical": 10, "creative": 3, "assertive": 5, "collaborative": 6, "detail_oriented": 10}
            },
            {
                "name": "Marketing Director",
                "role": "Marketing Lead",
                "background": "Marketing professional focused on brand strategy and customer engagement.",
                "primary_goals": ["Build brand awareness", "Drive customer acquisition", "Develop marketing strategies"],
                "personality_traits": {"analytical": 6, "creative": 9, "assertive": 7, "collaborative": 8, "detail_oriented": 6}
            }
        ]
    }

async def parse_pdf_with_progress(
    file: UploadFile,
    context_files: Optional[List[UploadFile]] = None,
    save_to_db: bool = False,
    session_id: str = None,
    db: Session = None
):
    """Parse PDF with real-time progress tracking"""
    import uuid
    
    debug_log(f"[DEBUG] Received session_id parameter: {session_id}")
    debug_log(f"[DEBUG] Session_id type: {type(session_id)}")
    
    # Generate session ID if not provided
    if not session_id:
        session_id = str(uuid.uuid4())
        debug_log(f"[DEBUG] Generated new session_id: {session_id}")
    
    debug_log(f"/api/parse-pdf-with-progress/ endpoint hit with session_id: {session_id}")
    
    # Initialize progress tracking immediately
    if session_id:
        debug_log(f"[PROGRESS] Initializing progress tracking for session: {session_id}")
        progress_manager.update_progress(session_id, "upload", 0, "Starting file processing...")
        debug_log(f"[PROGRESS] Session initialized, checking if exists: {session_id in progress_manager.progress_data}")
    
    # Normalize context_files to empty list if None
    if context_files is None:
        context_files = []
    elif not isinstance(context_files, list):
        context_files = [context_files]
    
    if not LLAMAPARSE_API_KEY:
        if session_id:
            progress_manager.error_processing(session_id, "LlamaParse API key not configured")
        raise HTTPException(status_code=500, detail="LlamaParse API key not configured.")
    
    # Support PDF, TXT, and other text-based files for the main file
    supported_main_types = ["application/pdf", "text/plain", "text/markdown", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]
    if file.content_type not in supported_main_types and not (file.filename and file.filename.lower().endswith(('.pdf', '.txt', '.md', '.doc', '.docx'))):
        if session_id:
            progress_manager.error_processing(session_id, "Unsupported file type")
        raise HTTPException(status_code=400, detail="Only PDF, TXT, MD, DOC, and DOCX files are supported for the main file.")
    
    try:
        # Process all files in optimized parallel batches
        debug_log(f"[PROGRESS] Starting parallel processing of {len(context_files) + 1} files...")
        start_time = time.time()
        
        # Create semaphore for file processing to avoid overwhelming the system
        file_semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLAMAPARSE)
        
        async def process_file_with_semaphore(file_item, name):
            async with file_semaphore:
                return await parse_file_flexible(file_item, session_id)
        
        # Create tasks for all files (main PDF + context files)
        tasks = []
        
        # Add main file task (highest priority)
        main_task = process_file_with_semaphore(file, "main_file")
        tasks.append(("main_file", main_task))
        
        # Add context file tasks
        for i, ctx_file in enumerate(context_files):
            ctx_task = process_file_with_semaphore(ctx_file, f"context_{i}")
            tasks.append((ctx_file.filename, ctx_task))
        
        debug_log(f"[PROGRESS] Created {len(tasks)} parallel tasks with semaphore control")
        
        # Execute all tasks in parallel with timeout protection
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*[task for _, task in tasks], return_exceptions=True),
                timeout=300.0  # 5 minute total timeout
            )
        except asyncio.TimeoutError:
            if session_id:
                progress_manager.error_processing(session_id, "File processing timed out after 5 minutes")
            raise HTTPException(status_code=504, detail="File processing timed out after 5 minutes")
        
        # Process results efficiently
        main_markdown = ""
        context_markdowns = []
        
        for i, (name, result) in enumerate(zip([name for name, _ in tasks], results)):
            if isinstance(result, Exception):
                debug_log(f"[ERROR] Failed to process {name}: {result}")
                if name == "main_file":
                    if session_id:
                        progress_manager.error_processing(session_id, f"Failed to process main file: {result}")
                    raise result  # Main file failure is critical
                else:
                    context_markdowns.append(f"[Context File: {name}]\n[Could not extract context: {result}]\n")
            else:
                debug_log(f"[PROGRESS] Successfully processed {name}, content length: {len(result)}")
                if name == "main_file":
                    main_markdown = result
                else:
                    context_markdowns.append(f"[Context File: {name}]\n{result.strip()}\n")
        
        context_text = "\n".join(context_markdowns)
        file_processing_time = time.time() - start_time
        debug_log(f"[PROGRESS] All files processed in {file_processing_time:.2f}s. Main: {len(main_markdown)}, Context: {len(context_text)}")
        
        # Preprocess content once (CPU-bound, run in thread pool)
        debug_log("[PROGRESS] Preprocessing content...")
        preprocessed = await asyncio.get_event_loop().run_in_executor(
            CPU_EXECUTOR, preprocess_case_study_content, main_markdown
        )
        
        title = preprocessed["title"]
        cleaned_content = preprocessed["cleaned_content"]
        
        # Send title update immediately
        if session_id:
            progress_manager.send_field_update(session_id, "title", title, "Extracted document title")
        
        # Process with AI using optimized pipeline with real-time updates
        debug_log("[PROGRESS] Starting AI processing pipeline...")
        ai_start_time = time.time()
        
        try:
            ai_result = await process_with_ai_optimized_with_updates_from_preprocessed(preprocessed, context_text, session_id)
        except Exception as e:
            debug_log(f"[ERROR] AI processing with updates failed: {e}")
            # Fallback to regular processing
            ai_result = await process_with_ai_optimized_from_preprocessed(preprocessed, context_text)
            
        ai_processing_time = time.time() - ai_start_time
        debug_log(f"[PROGRESS] AI processing completed in {ai_processing_time:.2f}s")
        
        # Update progress: Processing complete
        progress_manager.update_progress(session_id, "processing", 100, "Processing complete")
        
        # Send field updates incrementally as they're processed
        if session_id and ai_result:
            try:
                # Send title update immediately
                if "title" in ai_result:
                    progress_manager.send_field_update(session_id, "title", ai_result["title"], "Extracted document title")
                    await asyncio.sleep(0.5)  # Small delay to show incremental updates
                
                # Send description update
                if "description" in ai_result:
                    progress_manager.send_field_update(session_id, "description", ai_result["description"], "Extracted document description")
                    await asyncio.sleep(0.5)
                
                # Send student role update
                if "student_role" in ai_result:
                    progress_manager.send_field_update(session_id, "student_role", ai_result["student_role"], "Identified student role")
                    await asyncio.sleep(0.5)
                
                # Send personas update
                if "key_figures" in ai_result:
                    progress_manager.send_field_update(session_id, "personas", ai_result["key_figures"], f"Extracted {len(ai_result['key_figures'])} personas")
                    await asyncio.sleep(0.5)
                
                # Send scenes update
                if "scenes" in ai_result:
                    debug_log(f"[DEBUG] Sending scenes update with {len(ai_result['scenes'])} scenes")
                    for i, scene in enumerate(ai_result["scenes"]):
                        debug_log(f"[DEBUG] Scene {i+1}: {scene.get('title', 'Untitled')} - Image URL: {scene.get('image_url', 'None')}")
                    progress_manager.send_field_update(session_id, "scenes", ai_result["scenes"], f"Generated {len(ai_result['scenes'])} scenes")
                    await asyncio.sleep(0.5)
                
                # Send learning outcomes update
                if "learning_outcomes" in ai_result:
                    progress_manager.send_field_update(session_id, "learning_outcomes", ai_result["learning_outcomes"], f"Generated {len(ai_result['learning_outcomes'])} learning outcomes")
                    await asyncio.sleep(0.5)
                
                # Send AI enhancement completion update
                progress_manager.send_field_update(session_id, "ai_enhancement_complete", True, "AI enhancement completed successfully")
                
                # Mark as complete only after all field updates are sent
                progress_manager.complete_processing(session_id, {
                    "success": True,
                    "data": ai_result,
                    "message": "PDF parsing completed successfully"
                })
                    
            except Exception as e:
                debug_log(f"[ERROR] Failed to send field updates: {e}")
                progress_manager.error_processing(session_id, f"Failed to send field updates: {e}")
        
        # Ensure personas are properly formatted for frontend
        if "key_figures" in ai_result:
            debug_log(f"[DEBUG] Found {len(ai_result['key_figures'])} personas in AI result")
            for i, persona in enumerate(ai_result["key_figures"]):
                debug_log(f"[DEBUG] Persona {i+1}: {persona.get('name', 'Unknown')} - {persona.get('role', 'Unknown role')}")
        else:
            debug_log("[WARNING] No key_figures found in AI result")

        # Debug: Log personas_involved for all scenes and scene_cards before saving
        for key in ["scenes", "scene_cards"]:
            if key in ai_result:
                for scene in ai_result[key]:
                    print(f"[DEBUG] Scene '{scene.get('title', scene.get('scene_title', ''))}' personas_involved: {scene.get('personas_involved', [])}")
        
        # Save to database if requested
        if save_to_db:
            debug_log("[PROGRESS] Database saving not implemented yet")
            # TODO: Implement database saving functionality
            return {
                "success": True,
                "data": ai_result,
                "session_id": session_id,
                "message": "PDF parsed successfully (database saving not implemented)"
            }
        else:
            # Processing already completed after field updates
            # No need to call complete_processing again
            
            return {
                "success": True,
                "data": ai_result,
                "session_id": session_id,
                "message": "PDF parsed successfully"
            }
            
    except Exception as e:
        debug_log(f"[ERROR] PDF parsing failed: {e}")
        if session_id:
            progress_manager.error_processing(session_id, f"PDF parsing failed: {e}")
        raise HTTPException(status_code=500, detail=f"PDF parsing failed: {e}")

@router.post("/parse-pdf-with-progress")
async def parse_pdf_with_progress_route(
    file: UploadFile = File(...),
    context_files: Optional[List[UploadFile]] = File(None),
    save_to_db: bool = Form(False),
    session_id: str = Form(None),
    db: Session = Depends(get_db)
):
    """Parse PDF with real-time progress tracking via WebSocket"""
    return await parse_pdf_with_progress(file, context_files, save_to_db, session_id, db)

@router.post("/api/parse-pdf/")
async def parse_pdf(
    file: UploadFile = File(...),
    context_files: Optional[List[UploadFile]] = File(None),
    save_to_db: bool = False,  # Changed to False - don't auto-save
    db: Session = Depends(get_db)
):
    """Main endpoint: Parse PDF and context files, then process with AI"""
    debug_log("/api/parse-pdf/ endpoint hit")
    
    # Normalize context_files to empty list if None
    if context_files is None:
        context_files = []
    elif not isinstance(context_files, list):
        # If FastAPI passes a single UploadFile, wrap it in a list
        context_files = [context_files]
    if not LLAMAPARSE_API_KEY:
        raise HTTPException(status_code=500, detail="LlamaParse API key not configured.")
    # Support PDF, TXT, and other text-based files for the main file
    supported_main_types = ["application/pdf", "text/plain", "text/markdown", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]
    if file.content_type not in supported_main_types and not (file.filename and file.filename.lower().endswith(('.pdf', '.txt', '.md', '.doc', '.docx'))):
        raise HTTPException(status_code=400, detail="Only PDF, TXT, MD, DOC, and DOCX files are supported for the main file.")
    
    try:
        # Process all files in optimized parallel batches
        debug_log(f"[OPTIMIZED] Starting parallel processing of {len(context_files) + 1} files...")
        start_time = time.time()
        
        # Create semaphore for file processing to avoid overwhelming the system
        file_semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLAMAPARSE)
        
        async def process_file_with_semaphore(file_item, name):
            async with file_semaphore:
                return await parse_file_flexible(file_item)
        
        # Create tasks for all files (main PDF + context files)
        tasks = []
        
        # Add main file task (highest priority)
        main_task = process_file_with_semaphore(file, "main_file")
        tasks.append(("main_file", main_task))
        
        # Add context file tasks
        for i, ctx_file in enumerate(context_files):
            ctx_task = process_file_with_semaphore(ctx_file, f"context_{i}")
            tasks.append((ctx_file.filename, ctx_task))
        
        debug_log(f"[OPTIMIZED] Created {len(tasks)} parallel tasks with semaphore control")
        
        # Execute all tasks in parallel with timeout protection
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*[task for _, task in tasks], return_exceptions=True),
                timeout=300.0  # 5 minute total timeout
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="File processing timed out after 5 minutes")
        
        # Process results efficiently
        main_markdown = ""
        context_markdowns = []
        
        for i, (name, result) in enumerate(zip([name for name, _ in tasks], results)):
            if isinstance(result, Exception):
                debug_log(f"[ERROR] Failed to process {name}: {result}")
                if name == "main_file":
                    raise result  # Main file failure is critical
                else:
                    context_markdowns.append(f"[Context File: {name}]\n[Could not extract context: {result}]\n")
            else:
                debug_log(f"[OPTIMIZED] Successfully processed {name}, content length: {len(result)}")
                if name == "main_file":
                    main_markdown = result
                else:
                    context_markdowns.append(f"[Context File: {name}]\n{result.strip()}\n")
        
        context_text = "\n".join(context_markdowns)
        file_processing_time = time.time() - start_time
        debug_log(f"[OPTIMIZED] All files processed in {file_processing_time:.2f}s. Main: {len(main_markdown)}, Context: {len(context_text)}")
        
        # Process with AI using optimized pipeline
        debug_log("[OPTIMIZED] Starting AI processing pipeline...")
        ai_start_time = time.time()
        ai_result = await process_with_ai_optimized_with_updates(main_markdown, context_text)
        ai_processing_time = time.time() - ai_start_time
        debug_log(f"[OPTIMIZED] AI processing completed in {ai_processing_time:.2f}s")
        
        # Ensure personas are properly formatted for frontend
        if "key_figures" in ai_result:
            debug_log(f"[DEBUG] Found {len(ai_result['key_figures'])} personas in AI result")
            for i, persona in enumerate(ai_result["key_figures"]):
                debug_log(f"[DEBUG] Persona {i+1}: {persona.get('name', 'Unknown')} - {persona.get('role', 'Unknown role')}")
        else:
            debug_log("[WARNING] No key_figures found in AI result")

        # Debug: Log personas_involved for all scenes and scene_cards before saving
        for key in ["scenes", "scene_cards"]:
            if key in ai_result:
                for scene in ai_result[key]:
                    print(f"[DEBUG] Scene '{scene.get('title', scene.get('scene_title', ''))}' personas_involved: {scene.get('personas_involved', [])}")
        
        # Save to database if requested
        scenario_id = None
        if save_to_db:
            print("[DEBUG] Saving AI results to database...")
            # TODO: Get user_id from authentication context once implemented
            user_id = 0  # Default user ID for now
            # TODO: Implement proper database saving functionality
            # For now, just return a placeholder scenario ID
            scenario_id = None
            debug_log("[DEBUG] Database saving not yet implemented - returning None for scenario_id")
            print(f"[DEBUG] Scenario saved with ID: {scenario_id}")
        return {
            "status": "completed",
            "ai_result": ai_result,
            "scenario_id": scenario_id
        }
            
    except Exception as e:
        print(f"[ERROR] Exception in parse_pdf endpoint: {str(e)}")
        import traceback
        print(f"[ERROR] Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to parse PDF: {str(e)}")

def preprocess_case_study_content(raw_content: str) -> dict:
    """Pre-process the parsed content to extract clean case study information"""
    print("[DEBUG] Pre-processing case study content")
    
    # If content is a dict with markdown, extract the markdown
    if isinstance(raw_content, dict) and "markdown" in raw_content:
        content = raw_content["markdown"]
    elif isinstance(raw_content, str):
        # Check if it's a JSON string with markdown
        try:
            import json
            parsed_json = json.loads(raw_content)
            if isinstance(parsed_json, dict) and "markdown" in parsed_json:
                content = parsed_json["markdown"]
            else:
                content = raw_content
        except (json.JSONDecodeError, TypeError):
            content = raw_content
    else:
        content = raw_content
    
    print(f"[DEBUG] Raw content length: {len(content)}")
    
    # Clean up formatting artifacts
    content = content.replace('  ', ' ')  # Remove double spaces
    content = content.replace(' \n', '\n')  # Remove trailing spaces
    content = content.replace('\n ', '\n')  # Remove leading spaces
    
    # Split into lines and process
    lines = content.split('\n')
    cleaned_lines = []
    title = None
    
    # First pass: extract title from markdown headers
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Look for markdown headers (e.g., "# Title")
        if line.startswith('# '):
            title = line.replace('# ', '').strip()
            print(f"[DEBUG] Found title in markdown header: {title}")
            break
    
    # If no title found in headers, look for the first meaningful line
    if not title:
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Skip metadata and formatting artifacts
            if any(skip_pattern in line.upper() for skip_pattern in [
                'HARVARD BUSINESS SCHOOL', 'REV:', 'PAGE', '©', 'COPYRIGHT', 'ALL RIGHTS RESERVED',
                'DOCUMENT ID:', 'FILE:', 'CREATED:', 'MODIFIED:', '9-', 'R E V :'
            ]):
                continue
                
            # Skip lines that are just numbers, dates, or formatting
            if re.match(r'^[\d\s\-\.]+$', line):  # Just numbers, spaces, dashes, dots
                continue
                
            # Skip very short lines or all-uppercase lines
            if len(line) < 5 or line.isupper():
                continue
                
            # This looks like a title
            title = line
            print(f"[DEBUG] Found title in content: {title}")
            break
    
    # Fallback title
    if not title:
        title = "Business Case Study"

    # Clean content (only remove obvious metadata)
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Skip only the most obvious metadata lines
        if any(skip_pattern in line.upper() for skip_pattern in [
            'COPYRIGHT ENCODED', 'DOCUMENT ID:', 'FILE:', 'CREATED:', 'MODIFIED:', 
            'AUTHORIZED FOR USE ONLY', 'THIS DOCUMENT IS FOR USE ONLY BY'
        ]):
            continue
            
        # Skip lines that are just formatting artifacts
        if len(line) == 0 or re.match(r'^[\s\-\_\.]+$', line):
            continue
            
        # Keep everything else
        cleaned_lines.append(line)
    
    cleaned_content = '\n'.join(cleaned_lines)
    
    print(f"[DEBUG] Extracted title: {title}")
    print(f"[DEBUG] Cleaned content length: {len(cleaned_content)}")
    
    return {
        "title": title,
        "cleaned_content": cleaned_content
    }

# Global semaphore for OpenAI requests
_openai_semaphore = asyncio.Semaphore(MAX_CONCURRENT_OPENAI)
_image_semaphore = asyncio.Semaphore(MAX_CONCURRENT_IMAGES)

async def _fast_persona_extraction(content: str, title: str) -> dict:
    """Fast persona extraction with minimal AI call for autofill"""
    debug_log("[FAST_AI] Starting fast persona extraction...")
    
    prompt = f"""You are a JSON generator for business case study analysis. Extract key information quickly.

STUDENT ROLE IDENTIFICATION:
For the "student_role" field, determine what role the student should assume in this simulation. This could be:
- A specific character from the case study (e.g., "Ng'ang'a Wanjohi", "The CEO", "The Marketing Manager")
- A business role/position (e.g., "Business Analyst", "Consultant", "Strategic Advisor", "Investment Analyst")
- A stakeholder role (e.g., "Board Member", "Investor", "Customer Representative")
- A decision-maker role (e.g., "Project Manager", "Operations Director", "Financial Controller")

PRIORITY: Look for the MAIN CHARACTER or PROTAGONIST of the case study first. If there's a clear main character who is the central figure making decisions, the student should play that character.

Look for clues in the case study such as:
- The main character's name and title (e.g., "Ng'ang'a Wanjohi, CEO of...")
- "You are [character name]" or "You play the role of [character]"
- "As [character name], you must..."
- "Students are asked to step into the shoes of [character]"
- "You are asked to..." or "Students are tasked with..."
- "As a [role], you must..."
- "Your role is to..."
- "You have been hired as..."
- "You are the [position] and must decide..."

If there's a clear main character/protagonist, use their name and title (e.g., "Ng'ang'a Wanjohi (CEO of KasKazi Network)").
If no specific character is mentioned, default to "Business Analyst" as it's a common role for case study analysis.

Return JSON with:
{{
  "title": "<exact title>",
  "description": "<A comprehensive, detailed background description (5-7 paragraphs) covering: business context, challenges, stakeholders, financial details, market dynamics, and decision implications. Include specific numbers, dates, and examples.>",
  "student_role": "<specific role the student will assume>",
  "key_figures": [
    {{
      "name": "<name or title>",
      "role": "<their role>",
      "correlation": "<relationship to narrative>",
      "background": "<2-3 sentence background>",
      "primary_goals": ["<goal1>", "<goal2>", "<goal3>"],
      "personality_traits": {{
        "analytical": <0-10>,
        "creative": <0-10>,
        "assertive": <0-10>,
        "collaborative": <0-10>,
        "detail_oriented": <0-10>
      }}
    }}
  ]
}}

CONTENT:
{content[:2000]}...
"""
    
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a JSON generator for business case study analysis. Create detailed descriptions with specific information, numbers, and context. Be thorough and informative."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4000,
                temperature=0.1,
            )
        )
        
        generated_text = response.choices[0].message.content
        
        # Extract JSON from response
        match = re.search(r'({[\s\S]*})', generated_text)
        if match:
            json_str = match.group(1)
            result = json.loads(json_str)
            debug_log(f"[FAST_AI] Extracted student_role: {result.get('student_role', 'NOT_FOUND')}")
            return result
        else:
            debug_log("[FAST_AI] No JSON found in response")
            return _create_fallback_result(title, content)
            
    except Exception as e:
        debug_log(f"[FAST_AI_ERROR] {str(e)}")
        return _create_fallback_result(title, content)

def _create_fallback_result(title: str, content: str) -> dict:
    """Create fallback result when AI extraction fails"""
    debug_log("[FALLBACK] Creating fallback result...")
    
    # Try to extract a basic role from content
    student_role = "Business Analyst"  # Default
    
    if content:
        content_lower = content.lower()
        if "students are tasked" in content_lower or "you are asked" in content_lower:
            if "analyze" in content_lower:
                student_role = "Business Analyst"
            elif "evaluate" in content_lower:
                student_role = "Strategic Advisor"
            elif "decide" in content_lower or "decision" in content_lower:
                student_role = "Decision Maker"
            elif "consultant" in content_lower:
                student_role = "Business Consultant"
    
    return {
        "title": title or "Business Case Study",
        "student_role": student_role,
        "key_figures": [
            {
                "name": "Senior Executive",
                "role": "Executive Leader",
                "correlation": "Key decision maker in the business scenario",
                "background": "Experienced leader with strategic oversight and decision-making authority.",
                "primary_goals": ["Drive strategic growth", "Ensure organizational success", "Manage stakeholder relationships"],
                "personality_traits": {
                    "analytical": 8,
                    "creative": 6,
                    "assertive": 7,
                    "collaborative": 7,
                    "detail_oriented": 8
                }
            },
            {
                "name": "Operations Manager",
                "role": "Operations Lead",
                "correlation": "Operational expert in the business scenario",
                "background": "Operational expert focused on day-to-day execution and process optimization.",
                "primary_goals": ["Optimize processes", "Ensure efficiency", "Manage operational resources"],
                "personality_traits": {
                    "analytical": 9,
                    "creative": 4,
                    "assertive": 6,
                    "collaborative": 8,
                    "detail_oriented": 9
                }
            },
            {
                "name": "Financial Analyst",
                "role": "Finance Professional",
                "correlation": "Financial expert in the business scenario",
                "background": "Financial expert responsible for budget analysis and financial planning.",
                "primary_goals": ["Ensure financial health", "Analyze investment opportunities", "Manage risk"],
                "personality_traits": {
                    "analytical": 10,
                    "creative": 3,
                    "assertive": 5,
                    "collaborative": 6,
                    "detail_oriented": 10
                }
            }
        ]
    }

async def extract_personas_and_key_figures_optimized(combined_content: str, title: str, session_id: str = None) -> dict:
    """
    Extract structured personas and key figures from a business case study.
    
    Analyzes the provided case study text and returns a parsed JSON-like dictionary containing the case title, a comprehensive background description, the recommended student role, and a list of key figures (personas) with detailed attributes.
    
    Parameters:
        combined_content (str): Full case study text to analyze.
        title (str): The case study title or candidate title to include in the result.
        session_id (str, optional): Optional session identifier for tracing or logging; not required for parsing.
    
    Returns:
        dict: A dictionary with the following keys:
            - "title": The exact title of the case study.
            - "description": A detailed, multi-paragraph background that gives students full context.
            - "student_role": The specific role the student should assume in the simulation.
            - "key_figures": A list of persona objects; each persona includes:
                - "name": Full name or descriptive title.
                - "role": Their role in the narrative.
                - "correlation": Relationship to the narrative.
                - "background": A 2-3 sentence background.
                - "primary_goals": List of primary goals.
                - "personality_traits": Dict with numeric scores for "analytical", "creative", "assertive", "collaborative", and "detail_oriented".
                - "is_main_character": True if this persona matches the student_role, otherwise False.
    
    If extraction fails or the AI output lacks valid personas, a deterministic fallback persona set is returned.
    """
    debug_log("[AI] Starting persona extraction...")
    
    prompt = f"""You are a highly structured JSON-only generator trained to analyze business case studies for college business education.

CRITICAL: You must identify ALL named individuals, companies, organizations, and significant unnamed roles mentioned within the case study narrative. Focus ONLY on characters and entities that are part of the business story being told.

Instructions for key_figures identification:
- Find ALL types of key figures that can be turned into personas, including:
  * Named individuals who are characters in the case study (people with first and last names like "John Smith", "Mary Johnson", "Wanjohi", etc.)
  * Companies and organizations mentioned in the narrative (e.g., "Kaskazi Network", "Competitors", "Suppliers")
  * Unnamed but important roles within the story (e.g., "The CEO", "The Board of Directors", "The Marketing Manager")
  * Groups and stakeholders in the narrative (e.g., "Customers", "Employees", "Shareholders", "Partners")
  * External entities mentioned in the story (e.g., "Government Agencies", "Regulatory Bodies", "Industry Analysts")
  * Any entity that influences the narrative or decision-making process within the case study
- Include both named and unnamed entities that are part of the business story
- Even if someone/thing is mentioned only once or briefly, include them if they have a discernible role in the narrative
- CRITICAL: Do NOT include the student, the player, or the role/position the student is playing (as specified in "student_role") in the key_figures array.

STUDENT ROLE IDENTIFICATION:
For the "student_role" field, determine what role the student should assume in this simulation. This could be:
- A specific character from the case study (e.g., "Ng'ang'a Wanjohi", "The CEO", "The Marketing Manager")
- A business role/position (e.g., "Business Analyst", "Consultant", "Strategic Advisor", "Investment Analyst")
- A stakeholder role (e.g., "Board Member", "Investor", "Customer Representative")
- A decision-maker role (e.g., "Project Manager", "Operations Director", "Financial Controller")

PRIORITY: Look for the MAIN CHARACTER or PROTAGONIST of the case study first. If there's a clear main character who is the central figure making decisions, the student should play that character.

Look for clues in the case study such as:
- The main character's name and title (e.g., "Ng'ang'a Wanjohi, CEO of...")
- "You are [character name]" or "You play the role of [character]"
- "As [character name], you must..."
- "Students are asked to step into the shoes of [character]"
- "You are asked to..." or "Students are tasked with..."
- "As a [role], you must..."
- "Your role is to..."
- "You have been hired as..."
- "You are the [position] and must decide..."

If there's a clear main character/protagonist, use their name and title (e.g., "Ng'ang'a Wanjohi (CEO of KasKazi Network)").
If no specific character is mentioned, default to "Business Analyst" as it's a common role for case study analysis.

Your task is to analyze the following business case study content and return a JSON object with exactly the following fields:
  "title": "<The exact title of the business case study>",
  "description": "<A comprehensive, detailed background description that provides students with complete context. This should be 5-7 paragraphs covering: 1) The business/organizational context, current situation, and market environment, 2) Key challenges, problems, opportunities, and competitive landscape, 3) Relevant background information, stakeholders, constraints, and historical context, 4) The specific scenario, crisis, or decision point that students need to address, 5) Financial context, market dynamics, and business model details, 6) Key relationships, partnerships, and external factors, 7) The implications and stakes of the decisions to be made. Include specific details, numbers, dates, and concrete examples from the case study. Students should understand the full situation, context, and complexity without needing to read the original document.>",
  "student_role": "<The specific role the student will assume - be specific and descriptive>",
  "key_figures": [
    {{
      "name": "<Full name or descriptive title>",
      "role": "<Their role>",
      "correlation": "<Relationship to the narrative>",
      "background": "<2-3 sentence background>",
      "primary_goals": ["<Goal 1>", "<Goal 2>", "<Goal 3>"],
      "personality_traits": {{
        "analytical": <0-10>,
        "creative": <0-10>,
        "assertive": <0-10>,
        "collaborative": <0-10>,
        "detail_oriented": <0-10>
      }},
      "is_main_character": <true if this figure matches the student_role, otherwise false>
    }}
  ]

Output ONLY a valid JSON object. Do not include any extra commentary.

CASE STUDY CONTENT:
{combined_content}
"""
    
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a JSON generator for business case study analysis. Focus on creating comprehensive, detailed descriptions that give students complete context without needing the original document. Include specific details, numbers, dates, financial information, market dynamics, and concrete examples. Make descriptions thorough and informative."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=12000,
                temperature=0.2,
            )
        )
        
        generated_text = response.choices[0].message.content
        
        # Extract JSON from response
        match = re.search(r'({[\s\S]*})', generated_text)
        if match:
            json_str = match.group(1)
            result = json.loads(json_str)
            
            # Validate that key_figures exist
            if "key_figures" not in result or not result["key_figures"]:
                debug_log("[WARNING] No key_figures found in AI response, adding fallback personas")
                result["key_figures"] = [
                    {
                        "name": "Business Manager",
                        "role": "Manager",
                        "correlation": "Key stakeholder in the business scenario",
                        "background": "Experienced business professional involved in the case study.",
                        "primary_goals": ["Achieve business objectives", "Make informed decisions", "Drive results"],
                        "personality_traits": {
                            "analytical": 7,
                            "creative": 5,
                            "assertive": 6,
                            "collaborative": 7,
                            "detail_oriented": 8
                        },
                        "is_main_character": False
                    }
                ]
            
            debug_log(f"[SUCCESS] Persona extraction returned {len(result.get('key_figures', []))} personas")
            return result
        else:
            debug_log("[WARNING] No JSON found in persona extraction response")
            return _create_fallback_personas(title)
            
    except Exception as e:
        debug_log(f"[ERROR] Persona extraction failed: {str(e)}")
        return _create_fallback_personas(title)

async def generate_scenes_optimized(combined_content: str, title: str, key_figures: list = None, session_id: str = None) -> list:
    """
    Generate four validated interactive scenes for a business case study using AI and return them as a JSON-like list.
    
    This function requests scene generation from the AI, enforces strict validation rules on the returned scenes (each scene must be a dict, include 2–4 persona names in `personas_involved`, and the same main protagonist must appear in every scene), and falls back to a deterministic set of scenes if generation or validation fails. Validation rejects scenes with missing or invalid `personas_involved`, fewer than 2 or more than 4 personas, non-dictionary scenes, or scenes missing the main protagonist. If all generated scenes pass validation and there are at least four, the AI result is returned; otherwise a fallback scene set is returned.
    
    Parameters:
        combined_content (str): Truncated case-study content used to provide context to the AI prompt.
        title (str): Case-study title included in the prompt.
        key_figures (list, optional): List of key-figure dicts (each expected to contain a 'name' key). When provided, only names from this list will be allowed in `personas_involved`.
        session_id (str, optional): Optional session identifier for logging/tracing; not used to change function semantics.
    
    Returns:
        list: A list of scene dictionaries (each containing keys such as 'title', 'description', 'personas_involved', 'user_goal', 'goal', 'success_metric', and 'sequence_order'). If AI generation fails or strict validation does not pass, returns a deterministic fallback list of scenes.
    """
    debug_log("[AI] Starting scene generation...")
    
    # Extract key figure names for the prompt
    key_figure_names = []
    if key_figures:
        key_figure_names = [figure.get('name', '') for figure in key_figures if figure.get('name')]
        debug_log(f"[AI] Using {len(key_figure_names)} key figures for scene generation: {key_figure_names}")
    else:
        debug_log("[WARNING] No key figures provided to scene generation - this may cause issues")
    
    prompt = f"""Create exactly 4 interactive scenes for this business case study. Output ONLY a JSON array of scenes.

CASE CONTEXT:
Title: {title}
Content: {combined_content[:2000]}...

AVAILABLE KEY FIGURES (ONLY USE THESE IN PERSONAS_INVOLVED):
{', '.join(key_figure_names) if key_figure_names else 'No key figures provided - extract from content'}

Create 4 scenes following this progression:
1. Crisis Assessment/Initial Briefing
2. Investigation/Analysis Phase  
3. Solution Development
4. Implementation/Approval

CRITICAL REQUIREMENTS FOR SCENE-PERSONA RELATIONSHIPS:
- Each scene MUST have a "personas_involved" field with 2-4 actual persona names
- The personas_involved field is REQUIRED and must contain ONLY names from the AVAILABLE KEY FIGURES list above
- Do NOT leave personas_involved empty or use placeholder names
- Do NOT include case study authors, researchers, or anyone not in the AVAILABLE KEY FIGURES list
- Do NOT create new persona names - ONLY use the exact names from the AVAILABLE KEY FIGURES list
- Only include characters who would logically be present in that specific scene
- Each scene should have different personas_involved based on the scene context
- If you cannot find enough characters from the AVAILABLE KEY FIGURES list for a scene, use fewer personas rather than creating new ones

MANDATORY SCENE-SPECIFIC PERSONA ASSIGNMENT RULES:
You MUST follow these rules exactly - failure to do so will break the simulation:

1. Crisis Assessment/Initial Briefing (Scene 1):
   - MANDATORY: Include the main protagonist/CEO (e.g., "Ng'ang'a Wanjohi")
   - MANDATORY: Include 1-2 key advisors or close associates who would be present for initial discussions
   - ONLY include internal team members or trusted advisors mentioned in the case study
   - DO NOT include external stakeholders or investors in this scene

2. Investigation/Analysis Phase (Scene 2):
   - MANDATORY: Include the main protagonist
   - MANDATORY: Include research partners, analysts, or consultants mentioned in the case
   - MANDATORY: Include external experts or advisors who help with market analysis
   - MAY include potential partners or stakeholders being evaluated
   - DO NOT include investors or decision-makers who aren't involved in research

3. Solution Development (Scene 3):
   - MANDATORY: Include the main protagonist
   - MANDATORY: Include academic advisors, professors, or strategic consultants mentioned in the case
   - MANDATORY: Include key team members involved in strategy development
   - ONLY include people who help formulate the business strategy
   - DO NOT include investors or board members who aren't involved in strategy development

4. Implementation/Approval (Scene 4):
   - MANDATORY: Include the main protagonist
   - MANDATORY: Include investors, board members, or decision-makers mentioned in the case
   - MANDATORY: Include key stakeholders who need to approve the plan
   - ONLY include people who have authority to approve or fund the initiative
   - DO NOT include research partners or consultants who aren't decision-makers

STRICT ACCURACY REQUIREMENTS:
- Read the case study content carefully to identify which characters from the AVAILABLE KEY FIGURES list are mentioned in each phase
- Assign personas based on their actual involvement in the story, not assumptions
- If a character from the AVAILABLE KEY FIGURES list is only mentioned briefly, they should only appear in relevant scenes
- Ensure persona names match exactly as they appear in the AVAILABLE KEY FIGURES list
- Double-check that each persona assignment makes logical sense for that scene's context
- Each scene MUST have at least 2 personas and at most 4 personas (from the AVAILABLE KEY FIGURES list)
- The main protagonist MUST appear in ALL scenes (if they are in the AVAILABLE KEY FIGURES list)
- NO persona should appear in more than 3 scenes (except the main protagonist)
- If you cannot find enough characters from the AVAILABLE KEY FIGURES list for a scene, DO NOT make up names
- If a scene has fewer than 2 personas from the AVAILABLE KEY FIGURES list, mark it as INVALID and skip it

Each scene MUST have:
- title: Short descriptive name
- description: 2-3 sentences with vivid setting details for image generation
- personas_involved: Array of 2-4 actual persona names from the AVAILABLE KEY FIGURES list (REQUIRED, do not create new personas, ONLY USE THE EXACT NAMES FROM THE AVAILABLE KEY FIGURES LIST ABOVE)
- user_goal: Specific objective the student must achieve
- sequence_order: 1, 2, 3, or 4
- goal: Write a short, general summary of what the user should aim to accomplish in this scene
- success_metric: A clear, measurable way to determine if the student has accomplished the specific goal

Output format - ONLY this JSON array (NOTE THAT THE NUMBER OF PERSONAS IN EACH SCENE WILL VARY AND THIS IS JUST A SAMPLE OF HOW TO FORMAT, THERE MAY BE MORE OR LESS PERSOONAS IN EACH SCENE COMPARED TO THESE EXAMPLES):
[
  {{
    "title": "Crisis Assessment/Initial Briefing",
    "description": "Detailed setting description with visual elements...",
    "personas_involved": ["person1", "person2"],
    "user_goal": "Specific actionable goal",
    "goal": "General summary of what to accomplish",
    "success_metric": "Specific, measurable criteria for success",
    "sequence_order": 1
  }},
  {{
    "title": "Investigation/Analysis Phase",
    "description": "Detailed setting description with visual elements...",
    "personas_involved": ["person1", "person3],
    "user_goal": "Specific actionable goal",
    "goal": "General summary of what to accomplish",
    "success_metric": "Specific, measurable criteria for success",
    "sequence_order": 2
  }},
  {{
    "title": "Solution Development",
    "description": "Detailed setting description with visual elements...",
    "personas_involved": ["person1", "person4", "person5", "person6"],
    "user_goal": "Specific actionable goal",
    "goal": "General summary of what to accomplish",
    "success_metric": "Specific, measurable criteria for success",
    "sequence_order": 3
  }},
  {{
    "title": "Implementation/Approval",
    "description": "Detailed setting description with visual elements...",
    "personas_involved": ["person1", "person2"],
    "user_goal": "Specific actionable goal",
    "goal": "General summary of what to accomplish",
    "success_metric": "Specific, measurable criteria for success",
    "sequence_order": 4
  }}
]

CRITICAL FINAL REMINDER:
- personas_involved is REQUIRED and must contain real character names from the case study content
- Each scene MUST have EXACTLY 2-4 personas - NO EXCEPTIONS
- The main protagonist MUST appear in ALL scenes
- Other characters should only appear in scenes where they are actually involved
- Double-check that persona names match exactly as they appear in the case study
- If you cannot find enough characters for a scene, DO NOT create the scene
- This is essential for the simulation to work properly - incorrect persona assignments will break the @ mention functionality
- FAILURE TO FOLLOW THESE RULES WILL RESULT IN A BROKEN SIMULATION"""
    
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You generate JSON arrays of scenes. Output ONLY valid JSON array, no extra text."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2048,
                temperature=0.3,
            )
        )
        
        scenes_text = response.choices[0].message.content.strip()
        debug_log(f"[AI] Scenes AI response: {scenes_text[:200]}...")
        
        # Extract JSON array from response
        json_match = re.search(r'(\[[\s\S]*\])', scenes_text)
        if json_match:
            scenes_json = json_match.group(1)
            scenes = json.loads(scenes_json)
            
            # STRICT validation that each scene has personas_involved
            validated_scenes = []
            main_protagonist = None
            
            debug_log(f"[VALIDATION] Starting validation of {len(scenes)} scenes...")
            
            for i, scene in enumerate(scenes):
                if not isinstance(scene, dict):
                    debug_log(f"[ERROR] Scene {i+1} is not a dictionary, skipping")
                    continue
                    
                scene_title = scene.get('title', f'Scene {i+1}')
                
                if 'personas_involved' not in scene or not scene['personas_involved']:
                    debug_log(f"[ERROR] Scene {i+1} '{scene_title}' missing personas_involved field")
                    continue
                    
                if not isinstance(scene['personas_involved'], list) or len(scene['personas_involved']) == 0:
                    debug_log(f"[ERROR] Scene {i+1} '{scene_title}' has empty personas_involved")
                    continue
                
                persona_count = len(scene['personas_involved'])
                debug_log(f"[VALIDATION] Scene {i+1} '{scene_title}' has {persona_count} personas: {scene['personas_involved']}")
                
                # STRICT validation: Must have 2-4 personas
                if persona_count < 2:
                    debug_log(f"[ERROR] Scene {i+1} '{scene_title}' has only {persona_count} personas (minimum 2 required)")
                    debug_log(f"[ERROR] This scene will be REJECTED - simulation requires 2+ personas per scene")
                    continue
                    
                if persona_count > 4:
                    debug_log(f"[ERROR] Scene {i+1} '{scene_title}' has {persona_count} personas (maximum 4 allowed)")
                    debug_log(f"[ERROR] This scene will be REJECTED - simulation requires max 4 personas per scene")
                    continue
                
                # Identify main protagonist (should be the same across all scenes)
                if main_protagonist is None:
                    main_protagonist = scene['personas_involved'][0]  # Assume first persona is main protagonist
                    debug_log(f"[VALIDATION] Main protagonist identified as: '{main_protagonist}'")
                
                # Check if main protagonist is in this scene
                if main_protagonist not in scene['personas_involved']:
                    debug_log(f"[ERROR] Scene {i+1} '{scene_title}' missing main protagonist '{main_protagonist}'")
                    debug_log(f"[ERROR] This scene will be REJECTED - main protagonist must be in all scenes")
                    continue
                    
                validated_scenes.append(scene)
                debug_log(f"[VALIDATED] ✅ Scene {i+1}: {scene_title} - personas: {scene['personas_involved']}")
            
            debug_log(f"[VALIDATION] Validation complete: {len(validated_scenes)}/{len(scenes)} scenes passed")
            
            if len(validated_scenes) == len(scenes) and len(validated_scenes) >= 4:
                debug_log(f"[SUCCESS] Generated {len(scenes)} scenes with valid personas_involved")
                debug_log(f"[SUCCESS] Main protagonist '{main_protagonist}' appears in all scenes")
                return scenes
            else:
                debug_log(f"[ERROR] Only {len(validated_scenes)}/{len(scenes)} scenes passed strict validation")
                debug_log(f"[ERROR] This will break the simulation - using fallback scenes")
                debug_log(f"[ERROR] Validated scenes: {[s.get('title', 'Unknown') for s in validated_scenes]}")
                return _create_fallback_scenes()
        else:
            debug_log("[WARNING] No JSON array found in scenes response")
            return _create_fallback_scenes()
            
    except Exception as e:
        debug_log(f"[ERROR] Scene generation failed: {str(e)}")
        return _create_fallback_scenes()

async def generate_learning_outcomes_optimized(combined_content: str, title: str, session_id: str = None) -> list:
    """Generate learning outcomes using OpenAI with high-quality prompts"""
    debug_log("[AI] Starting learning outcomes generation...")
    
    prompt = f"""Generate exactly 5 learning outcomes for this business case study. Output ONLY a JSON array of learning outcomes.

CASE CONTEXT:
Title: {title}
Content: {combined_content[:1500]}...

Create 5 learning outcomes that are:
- Specific and measurable
- Relevant to business education
- Aligned with the case study content
- Progressive in complexity

Output format - ONLY this JSON array:
[
  "1. <Outcome 1>",
  "2. <Outcome 2>",
  "3. <Outcome 3>",
  "4. <Outcome 4>",
  "5. <Outcome 5>"
]
"""
    
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You generate JSON arrays of learning outcomes. Output ONLY valid JSON array, no extra text."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1024,
                temperature=0.2,
            )
        )
        
        outcomes_text = response.choices[0].message.content.strip()
        debug_log(f"[AI] Learning outcomes AI response: {outcomes_text[:200]}...")
        
        # Extract JSON array from response
        json_match = re.search(r'(\[[\s\S]*\])', outcomes_text)
        if json_match:
            outcomes_json = json_match.group(1)
            outcomes = json.loads(outcomes_json)
            debug_log(f"[SUCCESS] Generated {len(outcomes)} learning outcomes")
            return outcomes
        else:
            debug_log("[WARNING] No JSON array found in learning outcomes response")
            return _create_fallback_learning_outcomes()
            
    except Exception as e:
        debug_log(f"[ERROR] Learning outcomes generation failed: {str(e)}")
        return _create_fallback_learning_outcomes()

def _create_fallback_personas(title: str) -> dict:
    """Create fallback personas when AI processing fails"""
    return {
        "title": title or "Business Case Study",
        "description": "Business case study scenario requiring strategic analysis and decision-making.",
        "student_role": "Business Manager",
        "key_figures": [
            {
                "name": "Senior Executive",
                "role": "Executive Leader",
                "correlation": "Key decision maker in the business scenario",
                "background": "Experienced leader responsible for strategic decisions and team coordination.",
                "primary_goals": ["Drive business growth", "Manage team effectively", "Deliver results"],
                "personality_traits": {
                    "analytical": 8,
                    "creative": 6,
                    "assertive": 7,
                    "collaborative": 8,
                    "detail_oriented": 7
                },
                "is_main_character": False
            },
            {
                "name": "Operations Manager",
                "role": "Operations Lead",
                "correlation": "Manages operational aspects of the business scenario",
                "background": "Detail-oriented professional focused on execution and process improvement.",
                "primary_goals": ["Ensure operational efficiency", "Optimize processes", "Meet deadlines"],
                "personality_traits": {
                    "analytical": 9,
                    "creative": 4,
                    "assertive": 6,
                    "collaborative": 7,
                    "detail_oriented": 9
                },
                "is_main_character": False
            }
        ]
    }

def _create_fallback_scenes() -> list:
    """Create fallback scenes when AI processing fails"""
    return [
        {
            "title": "Initial Assessment",
            "description": "A professional boardroom meeting where key stakeholders gather to discuss the business situation.",
            "personas_involved": ["Senior Executive", "Operations Manager"],
            "user_goal": "Understand the current business situation and identify key challenges",
            "goal": "Assess the situation",
            "success_metric": "Successfully identify the main business challenges",
            "sequence_order": 1
        },
        {
            "title": "Analysis Phase",
            "description": "A focused analysis session with data review and stakeholder interviews.",
            "personas_involved": ["Operations Manager", "Senior Executive"],
            "user_goal": "Gather and analyze relevant business data",
            "goal": "Analyze available information",
            "success_metric": "Complete comprehensive analysis of business metrics",
            "sequence_order": 2
        },
        {
            "title": "Solution Development",
            "description": "A collaborative strategy session to develop potential solutions.",
            "personas_involved": ["Senior Executive", "Operations Manager"],
            "user_goal": "Develop viable solutions to address identified challenges",
            "goal": "Create actionable solutions",
            "success_metric": "Present well-structured solution recommendations",
            "sequence_order": 3
        },
        {
            "title": "Implementation Planning",
            "description": "A final meeting to approve solutions and plan implementation steps.",
            "personas_involved": ["Senior Executive", "Operations Manager"],
            "user_goal": "Secure approval and plan implementation of chosen solution",
            "goal": "Get implementation approval",
            "success_metric": "Gain stakeholder approval for implementation plan",
            "sequence_order": 4
        }
    ]

def _create_fallback_learning_outcomes() -> list:
    """Create fallback learning outcomes when AI processing fails"""
    return [
        "1. Analyze business situations and identify key challenges",
        "2. Develop strategic solutions to complex problems",
        "3. Apply business frameworks to real-world scenarios",
        "4. Make data-driven decisions under uncertainty",
        "5. Communicate recommendations effectively to stakeholders"
    ]

async def generate_scene_image(scene_description: str, scene_title: str, scenario_id: int = 0) -> str:
    """Generate an image for a scene using OpenAI's DALL-E API"""
    debug_log(f"[IMAGE] Generating image for scene: {scene_title}")
    start_time = time.time()
    
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        # Create an optimized prompt for image generation
        image_prompt = f"Professional business illustration: {scene_title}. {scene_description[:100]}. Clean, modern corporate style, educational use."
        
        # Use executor for blocking OpenAI call
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.images.generate(
                model="dall-e-3",
                prompt=image_prompt[:400],  # Truncate to stay within limits
                size="1024x1024",
                quality="standard",
                n=1,
            )
        )
        
        image_url = response.data[0].url
        generation_time = time.time() - start_time
        debug_log(f"[IMAGE] Generated image for '{scene_title}' in {generation_time:.2f}s")
        
        return image_url
        
    except Exception as e:
        debug_log(f"[ERROR] Image generation failed for scene '{scene_title}': {str(e)}")
        return ""  # Return empty string on failure

async def process_with_ai_optimized_with_updates_from_preprocessed(preprocessed: dict, context_text: str = "", session_id: str = None) -> dict:
    """
    Orchestrates the optimized AI pipeline on preprocessed content, producing personas, validated scenes (with generated images), and learning outcomes while sending incremental progress updates.
    
    Parameters:
        preprocessed (dict): Preprocessed input containing at least "title" and "cleaned_content".
        context_text (str): Optional authoritative context to prepend to the main content.
        session_id (str): Optional session identifier used to send real-time field updates.
    
    Returns:
        result (dict): Composed AI result with keys:
            - title (str): Final title (AI-updated if available).
            - description (str): Short description or excerpt of the content.
            - student_role (str): Recommended student role for the scenario.
            - key_figures (list): Extracted key figures metadata.
            - personas (list): Extracted personas.
            - scenes (list): Exactly four scene objects (validated); each scene may include "title", "description", "personas_involved", and "image_url".
            - learning_outcomes (list): Exactly five learning outcome entries.
    """
    debug_log("[OPTIMIZED] Starting optimized AI processing pipeline with real-time updates")
    start_time = time.time()
    
    try:
        title = preprocessed["title"]
        cleaned_content = preprocessed["cleaned_content"]
        
        # Prepare combined content
        if context_text.strip():
            combined_content = f"""
IMPORTANT CONTEXT FILES (most authoritative, follow these first):
{context_text}

MAIN CASE STUDY CONTENT:
{cleaned_content}
"""
        else:
            combined_content = cleaned_content
        
        # Send description update
        if session_id:
            progress_manager.send_field_update(session_id, "description", cleaned_content[:500] + "...", "Extracted document description")
        
        # Step 2: Sequential AI calls (personas first, then scenes with personas, then learning outcomes)
        debug_log("[OPTIMIZED] Starting sequential AI processing...")
        
        # Step 1: Extract personas and key figures first
        debug_log("[OPTIMIZED] Step 1: Extracting personas and key figures...")
        personas_result = await extract_personas_and_key_figures_optimized(combined_content, title, session_id)
        
        # Step 2: Generate scenes using the extracted key figures
        debug_log("[OPTIMIZED] Step 2: Generating scenes with key figures...")
        key_figures = personas_result.get('key_figures', [])
        scenes_result = await generate_scenes_optimized(combined_content, title, key_figures, session_id)
        
        # Step 3: Generate learning outcomes (can run in parallel with other tasks)
        debug_log("[OPTIMIZED] Step 3: Generating learning outcomes...")
        learning_outcomes_result = await generate_learning_outcomes_optimized(combined_content, title, session_id)
        
        # Generate images for scenes
        if scenes_result:
            debug_log(f"[IMAGE] Starting image generation for {len(scenes_result)} scenes")
            image_tasks = []
            for i, scene in enumerate(scenes_result):
                if isinstance(scene, dict) and "description" in scene and "title" in scene:
                    task = generate_scene_image(scene["description"], scene["title"], 0)
                    image_tasks.append(task)
                else:
                    # Create a simple async function that returns empty string
                    async def empty_task():
                        return ""
                    image_tasks.append(empty_task())
            
            # Wait for all image generations to complete
            image_urls = await asyncio.gather(*image_tasks, return_exceptions=True)
            
            # Update scenes with image URLs
            for i, scene in enumerate(scenes_result):
                if isinstance(scene, dict):
                    scene["image_url"] = image_urls[i] if i < len(image_urls) and not isinstance(image_urls[i], Exception) else ""
                    debug_log(f"[IMAGE] Scene {i+1}: {scene.get('title', 'Untitled')} - Image: {'Generated' if scene['image_url'] else 'Failed'}")
        
        # Combine all results
        final_result = {
            "title": personas_result.get("title", title),  # Use AI-generated title
            "description": personas_result.get("description", cleaned_content[:500] + "..."),  # Use AI-generated description
            "student_role": personas_result.get("student_role", "Business Manager"),
            "key_figures": personas_result.get("key_figures", []),
            "personas": personas_result.get("personas", []),
            "scenes": scenes_result,
            "learning_outcomes": learning_outcomes_result
        }
        
        processing_time = time.time() - start_time
        debug_log(f"[OPTIMIZED] Processing completed in {processing_time:.2f}s")
        
        return final_result
        
    except Exception as e:
        debug_log(f"[ERROR] AI processing failed: {str(e)}")
        raise

async def process_with_ai_optimized_from_preprocessed(preprocessed: dict, context_text: str = "") -> dict:
    """
    Orchestrates the optimized AI pipeline to produce personas, scenes, and learning outcomes from preprocessed content.
    
    Runs a sequential pipeline that (1) extracts personas and key figures, (2) generates four validated scenes using those key figures, and (3) generates five learning outcomes. If contextual text is provided it is prepended (as higher priority) to the main cleaned content before AI calls. The result aggregates AI-derived title, description, student_role, key_figures, personas, scenes, and learning_outcomes.
    
    Parameters:
        preprocessed (dict): Preprocessed content dictionary expected to contain:
            - "title" (str): extracted or fallback title for the case study.
            - "cleaned_content" (str): normalized/plain text content to feed the AI pipeline.
        context_text (str): Optional additional authoritative context to include before the main content.
    
    Returns:
        dict: Aggregated AI output with keys:
            - "title" (str): AI-generated or fallback title.
            - "description" (str): AI-generated description (or snippet of cleaned content).
            - "student_role" (str): Suggested student role.
            - "key_figures" (list): Extracted key figures metadata.
            - "personas" (list): Extracted personas.
            - "scenes" (list): Generated scenes (validated or fallback).
            - "learning_outcomes" (list): Generated learning outcomes.
    """
    debug_log("[OPTIMIZED] Starting optimized AI processing pipeline")
    start_time = time.time()
    
    try:
        title = preprocessed["title"]
        cleaned_content = preprocessed["cleaned_content"]
        
        # Prepare combined content
        if context_text.strip():
            combined_content = f"""
IMPORTANT CONTEXT FILES (most authoritative, follow these first):
{context_text}

MAIN CASE STUDY CONTENT:
{cleaned_content}
"""
        else:
            combined_content = cleaned_content
        
        # Step 2: Sequential AI calls (personas first, then scenes with personas, then learning outcomes)
        debug_log("[OPTIMIZED] Starting sequential AI processing...")
        
        # Step 1: Extract personas and key figures first
        debug_log("[OPTIMIZED] Step 1: Extracting personas and key figures...")
        personas_result = await extract_personas_and_key_figures_optimized(combined_content, title)
        
        # Step 2: Generate scenes using the extracted key figures
        debug_log("[OPTIMIZED] Step 2: Generating scenes with key figures...")
        key_figures = personas_result.get('key_figures', [])
        scenes_result = await generate_scenes_optimized(combined_content, title, key_figures)
        
        # Step 3: Generate learning outcomes
        debug_log("[OPTIMIZED] Step 3: Generating learning outcomes...")
        learning_outcomes_result = await generate_learning_outcomes_optimized(combined_content, title)
        
        # Combine all results
        final_result = {
            "title": personas_result.get("title", title),  # Use AI-generated title
            "description": personas_result.get("description", cleaned_content[:500] + "..."),  # Use AI-generated description
            "student_role": personas_result.get("student_role", "Business Manager"),
            "key_figures": personas_result.get("key_figures", []),
            "personas": personas_result.get("personas", []),
            "scenes": scenes_result,
            "learning_outcomes": learning_outcomes_result
        }
        
        processing_time = time.time() - start_time
        debug_log(f"[OPTIMIZED] Processing completed in {processing_time:.2f}s")
        
        return final_result
        
    except Exception as e:
        debug_log(f"[ERROR] AI processing failed: {str(e)}")
        raise

async def process_with_ai_optimized_with_updates(parsed_content: str, context_text: str = "", session_id: str = None) -> dict:
    """AI processing with real-time field updates - DEPRECATED: Use process_with_ai_optimized_with_updates_from_preprocessed instead"""
    # Preprocess content first
    preprocessed = await asyncio.get_event_loop().run_in_executor(
        CPU_EXECUTOR, preprocess_case_study_content, parsed_content
    )
    
    # Call the new function with preprocessed content
    return await process_with_ai_optimized_with_updates_from_preprocessed(preprocessed, context_text, session_id)
