import hashlib
import os
import tempfile
import asyncio
import json
import re
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form
from sqlalchemy.orm import Session
import httpx
import openai
from typing import List, Optional
from datetime import datetime
import unicodedata
from functools import wraps
import time

# LlamaIndex LlamaParse plugin for PDF parsing
from llama_parse import LlamaParse
from llama_index.core import SimpleDirectoryReader

from database.connection import get_db, settings
from database.models import Scenario, ScenarioPersona, ScenarioScene, ScenarioFile, scene_personas
from services.embedding_service import embedding_service
from .image_generation import generate_scenes_with_images


# =============================================================================
# IMAGE GENERATION: ENABLED
# =============================================================================
# Image generation is currently enabled and will generate DALL-E images for each scene.
# This will consume API credits (~$0.16-0.24 per PDF for 4-6 images).
# 
# Image generation functionality has been moved to api.image_generation module.
# To disable image generation to reduce costs:
# 1. Comment out the call to generate_scenes_with_images() in process_with_ai_optimized_with_updates_from_preprocessed()
# 2. Add empty image_urls to scenes as needed
# =============================================================================

LLAMAPARSE_API_KEY = settings.llamaparse_api_key
OPENAI_API_KEY = settings.openai_api_key
from utilities.secure_logging import secure_print_api_key_status
from utilities.debug_logging import debug_log
from utilities.rate_limiter import async_retry
from .pdf_progress import progress_manager

secure_print_api_key_status("LLAMAPARSE_API_KEY", LLAMAPARSE_API_KEY)
secure_print_api_key_status("OPENAI_API_KEY", OPENAI_API_KEY)

# Validate LlamaParse API key configuration
def validate_llamaparse_config():
    """Validate LlamaParse configuration and provide helpful error messages"""
    if not LLAMAPARSE_API_KEY:
        debug_log("[ERROR] LLAMAPARSE_API_KEY is not configured")
        return False, "LlamaParse API key is not configured. Please set LLAMAPARSE_API_KEY environment variable."
    
    if len(LLAMAPARSE_API_KEY) < 20:
        debug_log("[ERROR] LLAMAPARSE_API_KEY appears to be too short")
        return False, "LlamaParse API key appears to be invalid (too short). Please check your API key."
    
    if not LLAMAPARSE_API_KEY.startswith(('llx-', 'll-')):
        debug_log("[WARNING] LLAMAPARSE_API_KEY doesn't start with expected prefix")
        # This is just a warning, not an error, as API key formats might change
    
    debug_log(f"[SUCCESS] LlamaParse API key configured (length: {len(LLAMAPARSE_API_KEY)})")
    return True, "LlamaParse API key is properly configured"

# Validate configuration on startup
_is_valid, _config_message = validate_llamaparse_config()
if not _is_valid:
    debug_log(f"[CONFIG_ERROR] {_config_message}")
else:
    debug_log(f"[CONFIG_SUCCESS] {_config_message}")

router = APIRouter()

# Performance optimization constants
MAX_CONCURRENT_LLAMAPARSE = 3  # Limit concurrent LlamaParse requests
MAX_CONCURRENT_OPENAI = 2      # Limit concurrent OpenAI requests

# Thread pool for CPU-bound operations
CPU_EXECUTOR = ThreadPoolExecutor(max_workers=4)

# LlamaParse API URLs no longer needed - using LlamaIndex plugin instead

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
    
    # Read file contents once to avoid "read of closed file" errors
    try:
        # Reset file position to beginning in case it was already read
        if hasattr(file.file, 'seek'):
            file.file.seek(0)
        file_contents = await file.read()
        file_size = len(file_contents)
        debug_log(f"[FILE_PROCESSING] File: {file.filename}, size: {file_size} bytes")
        
        if file_size == 0:
            raise HTTPException(status_code=400, detail="File is empty.")
            
    except Exception as e:
        debug_log(f"[FILE_PROCESSING] Could not read file: {e}")
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")
    
    # For PDF files, use LlamaParse
    if filename.endswith('.pdf') or file.content_type == "application/pdf":
        return await parse_with_llamaparse_contents(file_contents, file.filename, file.content_type, session_id)
    
    # For text-based files, extract text directly
    elif filename.endswith(('.txt', '.md')) or file.content_type in ["text/plain", "text/markdown"]:
        return await extract_text_from_contents(file_contents, file.filename)
    
    # For Word documents, try to extract text (basic implementation)
    elif filename.endswith(('.doc', '.docx')) or file.content_type in ["application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
        return await extract_text_from_contents(file_contents, file.filename)
    
    else:
        # Fallback: try LlamaParse for other file types
        debug_log(f"Unknown file type {file.content_type}, trying LlamaParse as fallback...")
        return await parse_with_llamaparse_contents(file_contents, file.filename, file.content_type, session_id)

async def parse_file_flexible_from_contents(file_contents: bytes, filename: str, content_type: str, session_id: str = None) -> str:
    """Parse file contents that have already been read to avoid file stream issues."""
    filename_lower = filename.lower() if filename else ""
    
    debug_log(f"[FILE_PROCESSING] File: {filename}, size: {len(file_contents)} bytes")
    
    if len(file_contents) == 0:
        raise HTTPException(status_code=400, detail="File is empty.")
    
    # For PDF files, use LlamaParse
    if filename_lower.endswith('.pdf') or content_type == "application/pdf":
        return await parse_with_llamaparse_contents(file_contents, filename, content_type, session_id)
    
    # For text-based files, extract text directly
    elif filename_lower.endswith(('.txt', '.md')) or content_type in ["text/plain", "text/markdown"]:
        return await extract_text_from_contents(file_contents, filename)
    
    # For Word documents, try to extract text (basic implementation)
    elif filename_lower.endswith(('.doc', '.docx')) or content_type in ["application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
        return await extract_text_from_contents(file_contents, filename)
    
    else:
        # Fallback: try LlamaParse for other file types
        debug_log(f"Unknown file type {content_type}, trying LlamaParse as fallback...")
        return await parse_with_llamaparse_contents(file_contents, filename, content_type, session_id)


async def extract_text_from_file(file: UploadFile) -> str:
    """Extract text from text-based files (TXT, MD, etc.)"""
    try:
        contents = await file.read()
        text = contents.decode('utf-8', errors='ignore')
        return f"[File: {file.filename}]\n{text.strip()}\n"
    except Exception as e:
        return f"[File: {file.filename}]\n[Could not extract text: {e}]\n"

async def extract_text_from_contents(file_contents: bytes, filename: str) -> str:
    """Extract text from file contents (TXT, MD, etc.)"""
    try:
        text = file_contents.decode('utf-8', errors='ignore')
        return f"[File: {filename}]\n{text.strip()}\n"
    except Exception as e:
        return f"[File: {filename}]\n[Could not extract text: {e}]\n"


# Global semaphore for LlamaParse requests
_llamaparse_semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLAMAPARSE)

# Initialize LlamaParse with the plugin
def get_llamaparse_parser():
    """Get LlamaParse parser instance with proper configuration"""
    return LlamaParse(
        api_key=LLAMAPARSE_API_KEY,
        result_type="markdown",  # Get markdown output
        verbose=True,
        language="en"
    )

@async_retry(retries=3, delay=2.0)
async def parse_with_llamaparse_contents(file_contents: bytes, filename: str, content_type: str, session_id: str = None) -> str:
    """Parse file contents using LlamaIndex LlamaParse plugin"""
    debug_log(f"[LLAMAPARSE] Processing file with LlamaIndex plugin: {filename}, content_type: {content_type}")
    
    file_size = len(file_contents)
    debug_log(f"[LLAMAPARSE] File size: {file_size} bytes")
    
    if file_size == 0:
        raise HTTPException(status_code=400, detail="File is empty.")
    
    if not LLAMAPARSE_API_KEY:
        debug_log("[ERROR] LlamaParse API key not configured")
        raise HTTPException(status_code=500, detail="LlamaParse API key not configured.")
    
    # Validate file before processing
    if not validate_llamaparse_config()[0]:
        debug_log("[ERROR] LlamaParse configuration validation failed")
        raise HTTPException(status_code=500, detail="LlamaParse configuration validation failed.")
    
    
    async with _llamaparse_semaphore:  # Rate limiting
        try:
            # Update progress if session_id provided
            if session_id:
                progress_manager.update_progress(session_id, "upload", 10, "Preparing file for LlamaParse...")
            
            # Create temporary file for LlamaIndex LlamaParse plugin
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as temp_file:
                temp_file.write(file_contents)
                temp_file_path = temp_file.name
            
            try:
                # Update progress
                if session_id:
                    progress_manager.update_progress(session_id, "processing", 20, "Parsing with LlamaParse...")
                
                # Use LlamaIndex LlamaParse plugin
                parser = get_llamaparse_parser()
                
                # Parse the file using the plugin
                documents = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: parser.load_data(temp_file_path)
                )
                
                # Update progress
                if session_id:
                    progress_manager.update_progress(session_id, "processing", 90, "Processing results...")
                
                # Extract text from documents
                if documents and len(documents) > 0:
                    # Combine all document text
                    combined_text = "\n\n".join([doc.text for doc in documents])
                    debug_log(f"[LLAMAPARSE] Successfully parsed {filename}, extracted {len(combined_text)} characters")
                    
                    if session_id:
                        progress_manager.update_progress(session_id, "processing", 100, "Parsing complete!")
                    
                    return combined_text
                else:
                    debug_log(f"[LLAMAPARSE] No documents returned for {filename}")
                    if session_id:
                        progress_manager.error_processing(session_id, "No content extracted from PDF")
                    raise HTTPException(status_code=500, detail="No content could be extracted from the PDF")
                    
            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    debug_log(f"[LLAMAPARSE] Warning: Could not delete temp file {temp_file_path}: {e}")
                    
        except Exception as e:
            debug_log(f"[LLAMAPARSE] LlamaParse failed: {e}")
            if session_id:
                progress_manager.error_processing(session_id, f"PDF parsing failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"PDF parsing failed: {str(e)}")

# Old parse_with_llamaparse_from_contents function removed - now using LlamaIndex plugin

async def parse_with_llamaparse(file: UploadFile, session_id: str = None) -> str:
    """Send a file to LlamaParse using LlamaIndex plugin and return the parsed markdown content."""
    
    debug_log(f"[LLAMAPARSE] Processing file with LlamaIndex plugin: {file.filename}, content_type: {file.content_type}")
    
    # Read file content once to avoid "read of closed file" errors
    try:
        file_contents = await file.read()
        file_size = len(file_contents)
        debug_log(f"[LLAMAPARSE] File size: {file_size} bytes")
        
        if file_size == 0:
            raise HTTPException(status_code=400, detail="File is empty.")
            
    except Exception as e:
        debug_log(f"[LLAMAPARSE] Could not read file: {e}")
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")
    
    if not LLAMAPARSE_API_KEY:
        debug_log("[ERROR] LlamaParse API key not configured")
        raise HTTPException(status_code=500, detail="LlamaParse API key not configured.")
    
    # Validate file before processing
    if not file.filename:
        raise HTTPException(status_code=400, detail="File must have a filename.")
    
    debug_log(f"[LLAMAPARSE] Processing file: {file.filename}, size: {file_size} bytes")
    
    # Use the LlamaIndex plugin implementation
    return await parse_with_llamaparse_contents(file_contents, file.filename, file.content_type, session_id)

# Helper functions for LlamaIndex LlamaParse plugin (no longer needed with direct API calls)

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
        debug_log(f"[FAST_AUTOFILL] LlamaParse returned content length: {len(main_markdown)}")
        debug_log(f"[FAST_AUTOFILL] Content preview: {main_markdown[:200]}...")
        debug_log(f"[FAST_AUTOFILL] Content ends with: ...{main_markdown[-200:]}")
        
        # 2. Quick preprocessing
        preprocessed = preprocess_case_study_content(main_markdown)
        title = preprocessed["title"]
        content = preprocessed["cleaned_content"]
        debug_log(f"[FAST_AUTOFILL] After preprocessing - title: {title}")
        debug_log(f"[FAST_AUTOFILL] After preprocessing - content length: {len(content)}")
        debug_log(f"[FAST_AUTOFILL] After preprocessing - content preview: {content[:200]}...")
        
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

@router.get("/api/llamaparse-health/")
async def llamaparse_health_check():
    """Health check endpoint for LlamaParse configuration"""
    try:
        # Check API key configuration
        if not LLAMAPARSE_API_KEY:
            return {
                "status": "error",
                "message": "LLAMAPARSE_API_KEY is not configured",
                "details": "Please set the LLAMAPARSE_API_KEY environment variable in Railway"
            }
        
        if len(LLAMAPARSE_API_KEY) < 20:
            return {
                "status": "error", 
                "message": "LLAMAPARSE_API_KEY appears to be invalid",
                "details": f"API key length: {len(LLAMAPARSE_API_KEY)} characters (expected: 20+)"
            }
        
        # Test API connection
        headers = {"Authorization": f"Bearer {LLAMAPARSE_API_KEY}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # Try to reach the API endpoint
                response = await client.get("https://api.cloud.llamaindex.ai/health", headers=headers)
                return {
                    "status": "healthy",
                    "message": "LlamaParse API is reachable",
                    "api_key_length": len(LLAMAPARSE_API_KEY),
                    "api_response_status": response.status_code
                }
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    return {
                        "status": "error",
                        "message": "Invalid API key - authentication failed",
                        "details": "Please check your LLAMAPARSE_API_KEY"
                    }
                else:
                    return {
                        "status": "error",
                        "message": f"API request failed (status: {e.response.status_code})",
                        "details": str(e)
                    }
            except Exception as e:
                return {
                    "status": "error",
                    "message": "Cannot connect to LlamaParse API",
                    "details": str(e)
                }
                
    except Exception as e:
        return {
            "status": "error",
            "message": "Health check failed",
            "details": str(e)
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
        
        # Read all file contents upfront to avoid "read of closed file" errors
        debug_log("[PROGRESS] Reading all file contents before parallel processing...")
        file_contents_map = {}
        
        # Read main file contents
        try:
            main_contents = await file.read()
            file_contents_map["main_file"] = {
                "contents": main_contents,
                "filename": file.filename,
                "content_type": file.content_type
            }
            debug_log(f"[PROGRESS] Main file read: {file.filename}, {len(main_contents)} bytes")
        except Exception as e:
            debug_log(f"[PROGRESS] Failed to read main file: {e}")
            raise HTTPException(status_code=400, detail=f"Could not read main file: {e}")
        
        # Read context file contents
        for i, ctx_file in enumerate(context_files):
            try:
                ctx_contents = await ctx_file.read()
                file_contents_map[f"context_{i}"] = {
                    "contents": ctx_contents,
                    "filename": ctx_file.filename,
                    "content_type": ctx_file.content_type
                }
                debug_log(f"[PROGRESS] Context file read: {ctx_file.filename}, {len(ctx_contents)} bytes")
            except Exception as e:
                debug_log(f"[PROGRESS] Failed to read context file {ctx_file.filename}: {e}")
                # Continue with other files, but log the error
                file_contents_map[f"context_{i}"] = {
                    "contents": b"",
                    "filename": ctx_file.filename,
                    "content_type": ctx_file.content_type,
                    "error": str(e)
                }
        
        # Create semaphore for file processing to avoid overwhelming the system
        file_semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLAMAPARSE)
        
        async def process_file_contents_with_semaphore(file_data, name):
            async with file_semaphore:
                if "error" in file_data:
                    return f"[File: {file_data['filename']}]\n[Could not read file: {file_data['error']}]\n"
                return await parse_file_flexible_from_contents(
                    file_data["contents"], 
                    file_data["filename"], 
                    file_data["content_type"], 
                    session_id
                )
        
        # Create tasks for all files (main PDF + context files)
        tasks = []
        
        # Add main file task (highest priority)
        main_task = process_file_contents_with_semaphore(file_contents_map["main_file"], "main_file")
        tasks.append(("main_file", main_task))
        
        # Add context file tasks
        for i, ctx_file in enumerate(context_files):
            ctx_task = process_file_contents_with_semaphore(file_contents_map[f"context_{i}"], f"context_{i}")
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
    import uuid
    
    # Generate session ID if not provided
    if not session_id:
        session_id = str(uuid.uuid4())
        debug_log(f"[DEBUG] Generated new session_id: {session_id}")
    
    # Initialize progress tracking immediately and synchronously
    debug_log(f"[PROGRESS] Initializing progress tracking for session: {session_id}")
    progress_manager.update_progress(session_id, "upload", 0, "Starting file processing...")
    debug_log(f"[PROGRESS] Session initialized, checking if exists: {session_id in progress_manager.progress_data}")
    
    # CRITICAL: Ensure session is immediately available for polling
    # Store in both memory and Redis synchronously before returning
    session_data = progress_manager.progress_data.get(session_id, {})
    debug_log(f"[PROGRESS] Session data to store: {session_data}")
    
    # Store in Redis immediately if available
    if progress_manager.use_redis:
        try:
            progress_manager._store_progress_data(session_id, session_data)
            debug_log(f"[PROGRESS] Session stored in Redis: {session_id}")
        except Exception as e:
            debug_log(f"[PROGRESS] Failed to store session in Redis: {e}")
    
    # Ensure session exists in memory for immediate polling
    if session_id not in progress_manager.progress_data:
        progress_manager.progress_data[session_id] = session_data
        debug_log(f"[PROGRESS] Session added to memory: {session_id}")
    
    # Final verification that session is available
    debug_log(f"[PROGRESS] Final check - session in memory: {session_id in progress_manager.progress_data}")
    if progress_manager.use_redis:
        stored_data = progress_manager._get_progress_data(session_id)
        debug_log(f"[PROGRESS] Final check - session in Redis: {stored_data is not None}")
    
    # Start the actual parsing in the background
    import asyncio
    asyncio.create_task(parse_pdf_with_progress(file, context_files, save_to_db, session_id, db))
    
    # Return immediately with session ID so frontend can start polling
    return {
        "session_id": session_id,
        "status": "started",
        "message": "PDF parsing started, use session_id to track progress"
    }

@router.post("/api/parse-pdf/")
async def parse_pdf(
    file: UploadFile = File(...),
    context_files: Optional[List[UploadFile]] = File(None),
    save_to_db: bool = False,  # Changed to False - don't auto-save
    db: Session = Depends(get_db)
):
    """Main endpoint: Parse PDF and context files, then process with AI"""
    debug_log("/api/parse-pdf/ endpoint hit")
    
    # Debug file information at the very beginning
    try:
        file_contents = await file.read()
        md5_hash = hashlib.md5(file_contents).hexdigest()
        
        debug_log(f"[PARSE_PDF] ========== FILE DEBUG INFO ==========")
        debug_log(f"[PARSE_PDF] Filename: {file.filename}")
        debug_log(f"[PARSE_PDF] Content-Type: {file.content_type}")
        debug_log(f"[PARSE_PDF] File size: {len(file_contents)} bytes")
        debug_log(f"[PARSE_PDF] MD5 Hash: {md5_hash}")
        debug_log(f"[PARSE_PDF] First 20 bytes: {file_contents[:20]}")
        debug_log(f"[PARSE_PDF] Last 20 bytes: {file_contents[-20:]}")
        debug_log(f"[PARSE_PDF] Environment: {os.environ.get('NODE_ENV', 'unknown')}")
        debug_log(f"[PARSE_PDF] =========================================")
        
        # Reset file position for later processing
        if hasattr(file.file, 'seek'):
            file.file.seek(0)
            
    except Exception as e:
        debug_log(f"[PARSE_PDF] Error reading file for debug: {e}")
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")
    
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
        
        # Read all file contents upfront to avoid "read of closed file" errors
        debug_log("[OPTIMIZED] Reading all file contents before parallel processing...")
        file_contents_map = {}
        
        # Read main file contents
        try:
            main_contents = await file.read()
            file_contents_map["main_file"] = {
                "contents": main_contents,
                "filename": file.filename,
                "content_type": file.content_type
            }
            debug_log(f"[OPTIMIZED] Main file read: {file.filename}, {len(main_contents)} bytes")
        except Exception as e:
            debug_log(f"[OPTIMIZED] Failed to read main file: {e}")
            raise HTTPException(status_code=400, detail=f"Could not read main file: {e}")
        
        # Read context file contents
        for i, ctx_file in enumerate(context_files):
            try:
                ctx_contents = await ctx_file.read()
                file_contents_map[f"context_{i}"] = {
                    "contents": ctx_contents,
                    "filename": ctx_file.filename,
                    "content_type": ctx_file.content_type
                }
                debug_log(f"[OPTIMIZED] Context file read: {ctx_file.filename}, {len(ctx_contents)} bytes")
            except Exception as e:
                debug_log(f"[OPTIMIZED] Failed to read context file {ctx_file.filename}: {e}")
                # Continue with other files, but log the error
                file_contents_map[f"context_{i}"] = {
                    "contents": b"",
                    "filename": ctx_file.filename,
                    "content_type": ctx_file.content_type,
                    "error": str(e)
                }
        
        # Create semaphore for file processing to avoid overwhelming the system
        file_semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLAMAPARSE)
        
        async def process_file_contents_with_semaphore(file_data, name):
            async with file_semaphore:
                if "error" in file_data:
                    return f"[File: {file_data['filename']}]\n[Could not read file: {file_data['error']}]\n"
                return await parse_file_flexible_from_contents(
                    file_data["contents"], 
                    file_data["filename"], 
                    file_data["content_type"]
                )
        
        # Create tasks for all files (main PDF + context files)
        tasks = []
        
        # Add main file task (highest priority)
        main_task = process_file_contents_with_semaphore(file_contents_map["main_file"], "main_file")
        tasks.append(("main_file", main_task))
        
        # Add context file tasks
        for i, ctx_file in enumerate(context_files):
            ctx_task = process_file_contents_with_semaphore(file_contents_map[f"context_{i}"], f"context_{i}")
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

async def _fast_persona_extraction(content: str, title: str) -> dict:
    """Fast persona extraction with minimal AI call for autofill"""
    debug_log("[FAST_AI] Starting fast persona extraction...")
    
    prompt = f"""You are a JSON generator for business case study analysis. Extract key information quickly.

STUDENT ROLE IDENTIFICATION:
For the "student_role" field, determine what role the student should assume in this simulation. This could be:
- A specific character from the case study (e.g., "The CEO", "The Marketing Manager", "The Founder")
- A business role/position (e.g., "Business Analyst", "Consultant", "Strategic Advisor", "Investment Analyst")
- A stakeholder role (e.g., "Board Member", "Investor", "Customer Representative")
- A decision-maker role (e.g., "Project Manager", "Operations Director", "Financial Controller")

PRIORITY: Look for the MAIN CHARACTER or PROTAGONIST of the case study first. If there's a clear main character who is the central figure making decisions, the student should play that character.

Look for clues in the case study such as:
- The main character's name and title (e.g., "John Smith, CEO of...")
- "You are [character name]" or "You play the role of [character]"
- "As [character name], you must..."
- "Students are asked to step into the shoes of [character]"
- "You are asked to..." or "Students are tasked with..."
- "As a [role], you must..."
- "Your role is to..."
- "You have been hired as..."
- "You are the [position] and must decide..."

If there's a clear main character/protagonist, use their name and title (e.g., "John Smith (CEO of Company Name)").
If no specific character is mentioned, default to "Business Analyst" as it's a common role for case study analysis.

CRITICAL CONTENT REQUIREMENT: You MUST base your analysis ONLY on the actual content provided. Do NOT make up or hallucinate information that is not explicitly stated in the content. If the content appears to be corrupted or contains placeholder text, still attempt to extract any meaningful information that is present.

Return JSON with:
{{
  "title": "<exact title - if not available, create a meaningful business case title>",
  "description": "<A comprehensive, detailed background description (5-7 paragraphs) covering: business context, challenges, stakeholders, financial details, market dynamics, and decision implications. Include specific numbers, dates, and examples. If content is limited, create a realistic business scenario.>",
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
    """Extract personas and key figures using OpenAI with high-quality prompts"""
    debug_log("[AI] Starting persona extraction...")
    
    # Validate content before processing
    if not combined_content or combined_content.strip() == "":
        debug_log("[AI] ERROR: Content is empty, cannot extract personas")
        return {
            "personas": [],
            "key_figures": [],
            "student_role": "Business Analyst"
        }
    
    # Log content preview for debugging
    content_preview = combined_content[:500] + "..." if len(combined_content) > 500 else combined_content
    debug_log(f"[AI] Content preview: {content_preview}")
    debug_log(f"[AI] Content length: {len(combined_content)} characters")
    debug_log(f"[AI] Content starts with: {combined_content[:100]}")
    debug_log(f"[AI] Content ends with: {combined_content[-100:]}")
    
    prompt = f"""You are a highly structured JSON-only generator trained to analyze business case studies for college business education.

CRITICAL: You must identify ALL named individuals, companies, organizations, and significant unnamed roles mentioned within the case study narrative. Focus ONLY on characters and entities that are part of the business story being told.

Instructions for key_figures identification:
- Find ALL types of key figures that can be turned into personas, including:
  * Named individuals who are characters in the case study (people with first and last names like "John Smith", "Mary Johnson", "Sarah Wilson", etc.)
  * Companies and organizations mentioned in the narrative (e.g., "Kaskazi Network", "Competitors", "Suppliers")
  * Unnamed but important roles within the story (e.g., "The CEO", "The Board of Directors", "The Marketing Manager")
  * Groups and stakeholders in the narrative (e.g., "Customers", "Employees", "Shareholders", "Partners")
  * External entities mentioned in the story (e.g., "Government Agencies", "Regulatory Bodies", "Industry Analysts")
  * Any entity that influences the narrative or decision-making process within the case study
- Include both named and unnamed entities that are part of the business story
- Even if someone/thing is mentioned only once or briefly, include them if they have a discernible role in the narrative

⚠️ CRITICAL EXCLUSION RULE ⚠️
DO NOT include the student role character in the key_figures array. This means:
- If the student will play "John Smith (CEO)", do NOT create a key_figure for "John Smith", "Mr. John Smith", or any variation
- If the student role is "Business Analyst", do NOT create a key_figure for "Business Analyst" or similar
- The student role character is the PROTAGONIST that the student will control - they interact WITH the key_figures, not as one of them
- Mark "is_main_character": true ONLY for the figure that matches the student_role (this helps us filter them out)
- Remember: key_figures are NPCs (non-player characters) that the student will interact with during the simulation

STUDENT ROLE IDENTIFICATION:
For the "student_role" field, determine what role the student should assume in this simulation. This could be:
- A specific character from the case study (e.g., "The CEO", "The Marketing Manager", "The Founder")
- A business role/position (e.g., "Business Analyst", "Consultant", "Strategic Advisor", "Investment Analyst")
- A stakeholder role (e.g., "Board Member", "Investor", "Customer Representative")
- A decision-maker role (e.g., "Project Manager", "Operations Director", "Financial Controller")

PRIORITY: Look for the MAIN CHARACTER or PROTAGONIST of the case study first. If there's a clear main character who is the central figure making decisions, the student should play that character.

Look for clues in the case study such as:
- The main character's name and title (e.g., "John Smith, CEO of...")
- "You are [character name]" or "You play the role of [character]"
- "As [character name], you must..."
- "Students are asked to step into the shoes of [character]"
- "You are asked to..." or "Students are tasked with..."
- "As a [role], you must..."
- "Your role is to..."
- "You have been hired as..."
- "You are the [position] and must decide..."

If there's a clear main character/protagonist, use their name and title (e.g., "John Smith (CEO of Company Name)").
If no specific character is mentioned, default to "Business Analyst" as it's a common role for case study analysis.

CRITICAL CONTENT REQUIREMENT: You MUST base your analysis ONLY on the actual content provided. Do NOT make up or hallucinate information that is not explicitly stated in the content. If the content appears to be corrupted or contains placeholder text, still attempt to extract any meaningful information that is present.

Your task is to analyze the following business case study content and return a JSON object with exactly the following fields:
  "title": "<The exact title of the business case study - if not available, create a meaningful business case title>",
  "description": "<A comprehensive, detailed background description that provides students with complete context. This shouldn't be too long just like 2-4 paragraphs covering: 1) The business/organizational context, current situation, and market environment, 2) Key challenges, problems, opportunities, and competitive landscape, 3) Relevant background information, stakeholders, constraints, and historical context, 4) The specific scenario, crisis, or decision point that students need to address, 5) Financial context, market dynamics, and business model details, 6) Key relationships, partnerships, and external factors, 7) The implications and stakes of the decisions to be made. Include specific details, numbers, dates, and concrete examples from the case study. Students should understand the full situation, context, and complexity without needing to read the original document.>",
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
            
            # Filter out the student role from key_figures
            student_role = result.get("student_role", "").lower()
            if student_role and "key_figures" in result:
                debug_log(f"[FILTER] Filtering out student role '{student_role}' from key_figures")
                original_count = len(result["key_figures"])
                
                filtered_figures = []
                for figure in result["key_figures"]:
                    figure_name = (figure.get("name") or "").lower()
                    figure_role = (figure.get("role") or "").lower()
                    
                    # Check if this figure matches the student role
                    is_student_role = False
                    
                    # Extract name from student_role if it's in format "Name (Title)"
                    student_role_parts = re.match(r'([^(]+)(?:\s*\(([^)]+)\))?', student_role)
                    if student_role_parts:
                        student_name = student_role_parts.group(1).strip().lower()
                        student_title = (student_role_parts.group(2) or "").strip().lower()
                        
                        # Check if figure name matches student name or student title
                        if student_name and (student_name in figure_name or figure_name in student_name):
                            is_student_role = True
                            debug_log(f"[FILTER] Filtering out '{figure.get('name')}' - matches student name '{student_name}'")
                        elif student_title and (student_title in figure_role or figure_role in student_title):
                            is_student_role = True
                            debug_log(f"[FILTER] Filtering out '{figure.get('name')}' - role '{figure_role}' matches student title '{student_title}'")
                    
                    # Check for exact or partial matches with student_role
                    if student_role in figure_name or figure_name in student_role:
                        is_student_role = True
                        debug_log(f"[FILTER] Filtering out '{figure.get('name')}' - name matches student_role")
                    elif student_role in figure_role or figure_role in student_role:
                        is_student_role = True
                        debug_log(f"[FILTER] Filtering out '{figure.get('name')}' - role matches student_role")
                    
                    # Check is_main_character flag
                    if figure.get("is_main_character"):
                        is_student_role = True
                        debug_log(f"[FILTER] Filtering out '{figure.get('name')}' - marked as main character")
                    
                    if not is_student_role:
                        filtered_figures.append(figure)
                
                result["key_figures"] = filtered_figures
                debug_log(f"[FILTER] Filtered {original_count} -> {len(filtered_figures)} personas (removed {original_count - len(filtered_figures)} matching student role)")
            
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

async def generate_scenes_optimized(combined_content: str, title: str, session_id: str = None, personas_result: dict = None) -> list:
    """Generate scenes using OpenAI with high-quality prompts"""
    debug_log("[AI] Starting scene generation...")
    
    # Validate content before processing
    if not combined_content or combined_content.strip() == "":
        debug_log("[AI] ERROR: Content is empty, cannot generate scenes")
        return []
    
    # Log content preview for debugging
    content_preview = combined_content[:500] + "..." if len(combined_content) > 500 else combined_content
    debug_log(f"[AI] Scene generation - Content preview: {content_preview}")
    debug_log(f"[AI] Scene generation - Content length: {len(combined_content)} characters")
    
    # Get available personas for scene generation
    available_personas = []
    student_role = ""
    if personas_result and personas_result.get("key_figures"):
        available_personas = [persona.get("name", "") for persona in personas_result["key_figures"] if persona.get("name")]
    if personas_result and personas_result.get("student_role"):
        student_role = personas_result.get("student_role")
    
    debug_log(f"[AI] Available personas for scenes: {available_personas}")
    debug_log(f"[AI] Student role: {student_role}")
    
    prompt = f"""Create exactly 4 interactive scenes for this business case study. Output ONLY a JSON array of scenes.

CASE CONTEXT:
Title: {title}
Content: {combined_content[:2000]}...

STUDENT ROLE: {student_role if student_role else "Business Analyst"}
The student will play as: {student_role if student_role else "Business Analyst"}

AVAILABLE PERSONAS (use ONLY these names in personas_involved):
{', '.join(available_personas) if available_personas else "No specific personas identified - use generic roles like 'CEO', 'Manager', 'Analyst', etc."}

⚠️ CRITICAL: DO NOT include the student role character in personas_involved arrays ⚠️
- The student plays as "{student_role if student_role else "Business Analyst"}"
- Do NOT add this character name to any personas_involved list
- Do NOT add any variations like "Mr./Mrs./Ms. [student name]" to personas_involved
- Do NOT mention the student character in scene descriptions as if they are another persona
- The student character interacts WITH the personas, they are not one of the personas themselves
- Only include NPCs (non-player characters) from the AVAILABLE PERSONAS list above

Create 4 scenes following this progression:
1. Crisis Assessment/Initial Briefing
2. Investigation/Analysis Phase  
3. Solution Development
4. Implementation/Approval

Each scene MUST have:
- title: Short descriptive name
- description: 2-3 sentences with vivid setting details for image generation. DO NOT mention the student role character in the description.
- personas_involved: Array of 2-4 persona names from the AVAILABLE PERSONAS list above (use exact names, NO variations with titles like Mr./Mrs.)
- user_goal: Specific objective the student must achieve
- sequence_order: 1, 2, 3, or 4
- goal: Write a short, general summary of what the user should aim to accomplish in this scene
- success_metric: A clear, measurable way to determine if the student has accomplished the specific goal

Output format - ONLY this JSON array:
[
  {{
    "title": "Scene Title",
    "description": "Detailed setting description with visual elements...",
    "personas_involved": ["Persona Name 1", "Persona Name 2"],
    "user_goal": "Specific actionable goal",
    "goal": "General summary of what to accomplish",
    "success_metric": "Specific, measurable criteria for success",
    "sequence_order": 1
  }},
  ...4 scenes total
]
"""
    
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
            debug_log(f"[SUCCESS] Generated {len(scenes)} scenes")
            
            # Post-process: Filter out student role from personas_involved in each scene
            if student_role:
                debug_log(f"[FILTER] Post-processing scenes to remove student role: {student_role}")
                
                def normalize_name_for_comparison(name):
                    """Normalize name for comparison by removing titles and non-alphabetic chars"""
                    if not name:
                        return ""
                    normalized = name.strip()
                    # Remove title prefixes
                    normalized = re.sub(r'^(Mr\.|Mrs\.|Ms\.|Miss|Dr\.|Prof\.|Professor)\s+', '', normalized, flags=re.IGNORECASE)
                    # Remove all non-alphabetic characters
                    normalized = re.sub(r'[^a-zA-Z]', '', normalized).lower()
                    return normalized
                
                # Extract just the name part from student role (before any parentheses)
                student_name = student_role.split('(')[0].strip()
                student_name_normalized = normalize_name_for_comparison(student_name)
                debug_log(f"[FILTER] Student name normalized: {student_name_normalized}")
                
                for scene in scenes:
                    if "personas_involved" in scene and isinstance(scene["personas_involved"], list):
                        original_personas = scene["personas_involved"]
                        filtered_personas = []
                        
                        for persona in original_personas:
                            persona_normalized = normalize_name_for_comparison(persona)
                            if persona_normalized != student_name_normalized:
                                filtered_personas.append(persona)
                            else:
                                debug_log(f"[FILTER] Removed '{persona}' from scene '{scene.get('title')}' - matches student role")
                        
                        scene["personas_involved"] = filtered_personas
                        if len(original_personas) != len(filtered_personas):
                            debug_log(f"[FILTER] Scene '{scene.get('title')}': {len(original_personas)} -> {len(filtered_personas)} personas")
            
            return scenes
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

# Image generation moved to api.image_generation module

async def process_with_ai_optimized_with_updates_from_preprocessed(preprocessed: dict, context_text: str = "", session_id: str = None) -> dict:
    """AI processing with real-time field updates using preprocessed content"""
    debug_log("[OPTIMIZED] Starting optimized AI processing pipeline with real-time updates")
    start_time = time.time()
    
    try:
        title = preprocessed["title"]
        cleaned_content = preprocessed["cleaned_content"]
        
        debug_log(f"[AI] Preprocessed title: {title}")
        debug_log(f"[AI] Preprocessed content length: {len(cleaned_content)}")
        debug_log(f"[AI] Context text length: {len(context_text)}")
        
        # Prepare combined content
        if context_text.strip():
            combined_content = f"""
IMPORTANT CONTEXT FILES (most authoritative, follow these first):
{context_text}

MAIN CASE STUDY CONTENT:
{cleaned_content}
"""
            debug_log(f"[AI] Combined content with context files - Context length: {len(context_text)}, Main content length: {len(cleaned_content)}")
            debug_log(f"[AI] Context preview: {context_text[:300]}...")
        else:
            combined_content = cleaned_content
            debug_log(f"[AI] Using only main content - Length: {len(cleaned_content)}")
        
        debug_log(f"[AI] Final combined content length: {len(combined_content)}")
        debug_log(f"[AI] Combined content preview: {combined_content[:500]}...")
        debug_log(f"[AI] Combined content ends with: {combined_content[-200]}...")
        
        # Send description update
        if session_id:
            progress_manager.send_field_update(session_id, "description", cleaned_content[:500] + "...", "Extracted document description")
        
        # Step 2: Sequential AI calls to ensure personas are available for scene generation
        debug_log("[OPTIMIZED] Starting sequential AI processing...")
        
        # First: Extract personas and key figures
        debug_log("[AI] Step 1: Extracting personas and key figures...")
        personas_result = await extract_personas_and_key_figures_optimized(combined_content, title, session_id)
        
        # Second: Generate learning outcomes (can be done in parallel with scenes)
        debug_log("[AI] Step 2: Generating learning outcomes...")
        learning_outcomes_task = generate_learning_outcomes_optimized(combined_content, title, session_id)
        
        # Third: Generate scenes with persona information
        debug_log("[AI] Step 3: Generating scenes with persona context...")
        scenes_result = await generate_scenes_optimized(combined_content, title, session_id, personas_result)
        
        # Wait for learning outcomes
        learning_outcomes_result = await learning_outcomes_task
        
        # Generate images for scenes using the image generation module
        if scenes_result:
            scenes_result = await generate_scenes_with_images(scenes_result, session_id)
        else:
            debug_log("[IMAGE] No scenes to generate images for")
        
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
    """Optimized AI processing using preprocessed content"""
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
        
        # Step 2: Parallel AI calls for different components
        debug_log("[OPTIMIZED] Starting parallel AI processing...")
        
        # Create tasks for parallel execution
        tasks = []
        
        # Task 1: Extract personas and key figures
        tasks.append(extract_personas_and_key_figures_optimized(combined_content, title))
        
        # Task 2: Generate scenes
        tasks.append(generate_scenes_optimized(combined_content, title))
        
        # Task 3: Generate learning outcomes
        tasks.append(generate_learning_outcomes_optimized(combined_content, title))
        
        # Execute all tasks in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        personas_result = results[0] if not isinstance(results[0], Exception) else {}
        scenes_result = results[1] if not isinstance(results[1], Exception) else []
        learning_outcomes_result = results[2] if not isinstance(results[2], Exception) else []
        
        # Handle any exceptions
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                debug_log(f"[ERROR] Task {i} failed: {result}")
        
        debug_log(f"[AI] Personas result: {personas_result}")
        debug_log(f"[AI] Scenes result: {scenes_result}")
        debug_log(f"[AI] Learning outcomes result: {learning_outcomes_result}")
        
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

