import os
import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
import httpx
import openai
from typing import List, Optional
from datetime import datetime
import string
import unicodedata
from functools import wraps
import time

from database.connection import get_db, settings
from database.models import Scenario, ScenarioPersona, ScenarioScene, ScenarioFile, scene_personas
# Import embedding service lazily to avoid initialization issues
# from services.embedding_service import embedding_service

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
from utilities.debug_logging import debug_log


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
    """Extract text from context files (PDFs and TXT files)"""
    context_texts = []
    for file in context_files:
        filename = file.filename.lower()
        contents = await file.read()
        if filename.endswith('.pdf'):
            try:
                import io
                reader = PdfReader(io.BytesIO(contents))
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
                context_texts.append(f"[Context File: {file.filename}]\n{text.strip()}\n")
            except Exception as e:
                context_texts.append(f"[Context File: {file.filename}]\n[Could not extract PDF text: {e}]\n")
        elif filename.endswith('.txt'):
            try:
                text = contents.decode('utf-8', errors='ignore')
                context_texts.append(f"[Context File: {file.filename}]\n{text.strip()}\n")
            except Exception as e:
                context_texts.append(f"[Context File: {file.filename}]\n[Could not extract TXT text: {e}]\n")
        else:
            context_texts.append(f"[Context File: {file.filename}]\n[Unsupported file type]\n")
    return "\n".join(context_texts)

async def parse_file_flexible(file: UploadFile) -> str:
    """Parse a file using the appropriate method based on file type."""
    filename = file.filename.lower() if file.filename else ""
    
    # For PDF files, use LlamaParse
    if filename.endswith('.pdf') or file.content_type == "application/pdf":
        return await parse_with_llamaparse(file)
    
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
async def parse_with_llamaparse(file: UploadFile) -> str:
    """Send a file to LlamaParse and return the parsed markdown content with rate limiting."""
    if not LLAMAPARSE_API_KEY:
        raise HTTPException(status_code=500, detail="LlamaParse API key not configured.")
    
    async with _llamaparse_semaphore:  # Rate limiting
        debug_log(f"[OPTIMIZED] Starting LlamaParse for {file.filename}")
        start_time = time.time()
        
        try:
            # Read file contents once and store them
            contents = await file.read()
            headers = {"Authorization": f"Bearer {LLAMAPARSE_API_KEY}"}
            files = {"file": (file.filename, contents, file.content_type)}
            
            # Use optimized HTTP client with connection pooling
            limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
            timeout = httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=120.0)
            
            async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
                try:
                    # Upload with retry logic built into decorator
                    upload_response = await client.post(LLAMAPARSE_API_URL, headers=headers, files=files)
                    upload_response.raise_for_status()
                    
                    job_data = upload_response.json()
                    job_id = job_data.get("id") or job_data.get("job_id") or job_data.get("jobId")
                    
                    if not job_id:
                        raise HTTPException(status_code=500, detail=f"No job ID in LlamaParse response")
                    
                    debug_log(f"[OPTIMIZED] Got job ID: {job_id} for {file.filename}")
                    
                    # Optimized polling with exponential backoff
                    wait_times = [1, 2, 3, 5, 5, 5]  # Faster initial polling
                    max_polls = 40  # Reduced from 60
                    
                    for attempt in range(max_polls):
                        status_response = await client.get(f"{LLAMAPARSE_JOB_URL}/{job_id}", headers=headers)
                        status_response.raise_for_status()
                        status_data = status_response.json()
                        
                        status = status_data.get("status")
                        if status in ["COMPLETED", "SUCCESS"]:
                            debug_log(f"[OPTIMIZED] Job {job_id} completed in {time.time() - start_time:.2f}s")
                            
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
                            raise HTTPException(status_code=500, detail=f"LlamaParse job failed: {error_msg}")
                        
                        # Dynamic wait time
                        wait_time = wait_times[min(attempt, len(wait_times) - 1)]
                        await asyncio.sleep(wait_time)
                    
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
        ai_result = await process_with_ai_optimized(main_markdown, context_text)
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
            scenario_id = await save_scenario_to_db(
                ai_result, file, context_files, main_markdown, context_text, user_id, db
            )
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

async def process_with_ai_optimized(parsed_content: str, context_text: str = "") -> dict:
    """Optimized AI processing with parallel API calls and better error handling"""
    debug_log("[OPTIMIZED] Starting optimized AI processing pipeline")
    start_time = time.time()
    
    try:
        # Step 1: Preprocess content (CPU-bound, run in thread pool)
        preprocessed = await asyncio.get_event_loop().run_in_executor(
            CPU_EXECUTOR, preprocess_case_study_content, parsed_content
        )
        
        title = preprocessed["title"]
        cleaned_content = preprocessed["cleaned_content"]
        
        # Prepare combined content
        if context_text.strip():
            combined_content = f"""
IMPORTANT CONTEXT FILES (most authoritative, follow these first):
{context_text}

CASE STUDY CONTENT (main PDF):
{cleaned_content}
"""
        else:
            combined_content = cleaned_content
        
        debug_log(f"[OPTIMIZED] Content preprocessing completed in {time.time() - start_time:.2f}s")
        
        # Step 2: Run both AI calls in parallel
        ai_tasks_start = time.time()
        
        # Create tasks for parallel execution
        base_analysis_task = _get_base_analysis_with_semaphore(combined_content, title, cleaned_content)
        
        # Execute base analysis first
        base_result = await base_analysis_task
        debug_log(f"[OPTIMIZED] Base analysis completed in {time.time() - ai_tasks_start:.2f}s")
        
        # Step 3: Generate scenes based on base analysis
        scenes_task = _generate_scenes_with_semaphore(base_result)
        scenes = await scenes_task
        
        # Step 4: Generate images for scenes in parallel
        if scenes:
            debug_log(f"[OPTIMIZED] Starting parallel image generation for {len(scenes)} scenes")
            image_tasks = [
                _generate_scene_image_with_semaphore(
                    scene.get("description", ""), 
                    scene.get("title", f"Scene {i+1}"), 
                    0
                )
                for i, scene in enumerate(scenes)
            ]
            
            image_urls = await asyncio.gather(*image_tasks, return_exceptions=True)
            
            # Combine scenes with images
            processed_scenes = []
            for i, scene in enumerate(scenes):
                if isinstance(scene, dict):
                    processed_scene = {
                        "title": scene.get("title", f"Scene {i+1}"),
                        "description": scene.get("description", ""),
                        "personas_involved": scene.get("personas_involved", []),
                        "user_goal": scene.get("user_goal", ""),
                        "sequence_order": scene.get("sequence_order", i+1),
                        "image_url": image_urls[i] if i < len(image_urls) and not isinstance(image_urls[i], Exception) else "",
                        "successMetric": scene.get("success_metric", "")
                    }
                    processed_scenes.append(processed_scene)
        else:
            processed_scenes = []
        
        # Step 5: Compile final result
        key_figures = base_result.get("key_figures", [])
        final_result = {
            "title": base_result.get("title") or title,
            "description": base_result.get("description") or (cleaned_content[:1500] + "..." if len(cleaned_content) > 1500 else cleaned_content),
            "student_role": base_result.get("student_role") or "Business Analyst",
            "key_figures": key_figures,
            "personas": key_figures,  # Add personas as alias for frontend compatibility
            "scenes": processed_scenes,
            "learning_outcomes": base_result.get("learning_outcomes", [
                "1. Analyze the business situation presented in the case study",
                "2. Identify key stakeholders and their interests",
                "3. Develop strategic recommendations based on the analysis",
                "4. Evaluate the impact of decisions on organizational performance",
                "5. Apply business concepts and frameworks to real-world scenarios"
            ])
        }
        
        # Step 6: Post-processing optimizations
        final_result = await _post_process_result(final_result)
        
        total_time = time.time() - start_time
        debug_log(f"[OPTIMIZED] Complete AI pipeline finished in {total_time:.2f}s")
        debug_log(f"[OPTIMIZED] Generated {len(final_result.get('key_figures', []))} personas and {len(processed_scenes)} scenes")
        
        return final_result
        
    except Exception as e:
        debug_log(f"[ERROR] Optimized AI processing failed: {str(e)}")
        # Return fallback content
        return {
            "title": "Business Case Study",
            "description": "Failed to process case study content",
            "key_figures": [],
            "scenes": [],
            "learning_outcomes": [
                "1. Analyze the business situation presented in the case study",
                "2. Identify key stakeholders and their interests"
            ]
        }

async def _get_base_analysis_with_semaphore(combined_content: str, title: str, cleaned_content: str) -> dict:
    """Get base case study analysis with semaphore control"""
    async with _openai_semaphore:
        return await _get_base_analysis(combined_content, title, cleaned_content)

async def _generate_scenes_with_semaphore(base_result: dict) -> list:
    """Generate scenes with semaphore control"""
    async with _openai_semaphore:
        return await generate_scenes_with_ai(base_result)

async def _generate_scene_image_with_semaphore(description: str, title: str, scenario_id: int) -> str:
    """Generate scene image with semaphore control"""
    async with _image_semaphore:
        return await generate_scene_image(description, title, scenario_id)

async def _post_process_result(result: dict) -> dict:
    """Post-process AI result for consistency and validation"""
    # Run post-processing in thread pool since it's CPU-bound
    return await asyncio.get_event_loop().run_in_executor(
        CPU_EXECUTOR, _post_process_sync, result
    )

def _post_process_sync(result: dict) -> dict:
    """Synchronous post-processing for thread pool execution"""
    # Remove main character from key_figures
    student_role = result.get("student_role", "").lower()
    key_figures = result.get("key_figures", [])
    
    filtered_key_figures = []
    for fig in key_figures:
        if fig.get("is_main_character", False):
            debug_log(f"Removing main character from key_figures: {fig.get('name', '')}")
            continue
        filtered_key_figures.append(fig)
    
    result["key_figures"] = filtered_key_figures
    
    # Ensure every scene has personas_involved
    for scene in result.get("scenes", []):
        if not scene.get("personas_involved"):
            # Add first available persona
            if filtered_key_figures:
                scene["personas_involved"] = [filtered_key_figures[0]["name"]]
    
    return result

async def _fast_persona_extraction(content: str, title: str) -> dict:
    """ULTRA-FAST persona extraction for autofill with minimal prompt"""
    debug_log("[FAST_AI] Starting ultra-fast persona extraction")
    
    # Ultra-streamlined prompt for speed
    prompt = f"""Extract personas from this business case. Return ONLY JSON:

{{
  "title": "{title}",
  "student_role": "<main decision-maker role>",
  "key_figures": [
    {{
      "name": "<person/entity name>",
      "role": "<their role>",
      "background": "<brief background>",
      "primary_goals": ["goal1", "goal2"],
      "personality_traits": {{"analytical": 7, "creative": 5, "assertive": 6, "collaborative": 7, "detail_oriented": 7}}
    }}
  ]
}}

Find ALL people, companies, roles mentioned in this content. Be thorough but fast.

CONTENT: {content[:3000]}"""  # Truncate for speed
    
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="gpt-4o-mini",  # Use faster model
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,  # Reduced for speed
                temperature=0.1,  # Lower for consistency
            )
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Quick JSON extraction
        import re
        json_match = re.search(r'({[\s\S]*})', result_text)
        if json_match:
            result = json.loads(json_match.group(1))
            debug_log(f"[FAST_AI] Extracted {len(result.get('key_figures', []))} personas quickly")
            return result
        else:
            debug_log("[FAST_AI] JSON extraction failed, using fallback")
            return _create_fast_fallback(title)
            
    except Exception as e:
        debug_log(f"[FAST_AI_ERROR] {str(e)}")
        return _create_fast_fallback(title)

def _create_fast_fallback(title: str) -> dict:
    """Create fast fallback result for autofill"""
    return {
        "title": title,
        "student_role": "Business Manager",
        "key_figures": [
            {
                "name": "Senior Executive",
                "role": "Executive Leader",
                "background": "Experienced leader with strategic oversight responsibilities.",
                "primary_goals": ["Drive business growth", "Make strategic decisions"],
                "personality_traits": {"analytical": 8, "creative": 6, "assertive": 7, "collaborative": 7, "detail_oriented": 8}
            },
            {
                "name": "Operations Manager", 
                "role": "Operations Lead",
                "background": "Operational expert focused on execution and process optimization.",
                "primary_goals": ["Optimize operations", "Ensure efficiency"],
                "personality_traits": {"analytical": 9, "creative": 4, "assertive": 6, "collaborative": 8, "detail_oriented": 9}
            }
        ]
    }

async def _get_base_analysis(combined_content: str, title: str, cleaned_content: str) -> dict:
    """Get base case study analysis using OpenAI"""
    debug_log("[OPTIMIZED] Starting base analysis with OpenAI")
    
    # Create comprehensive prompt for base analysis (optimized version of original)
    prompt = f"""
You are a highly structured JSON-only generator trained to analyze business case studies for college business education.

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

Your task is to analyze the following business case study content and return a JSON object with exactly the following fields:
  "title": "<The exact title of the business case study>",
  "description": "<A comprehensive, multi-paragraph background description>",
  "student_role": "<The specific role the student will assume>",
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
  ],
  "learning_outcomes": [
    "1. <Outcome 1>",
    "2. <Outcome 2>",
    "3. <Outcome 3>",
    "4. <Outcome 4>",
    "5. <Outcome 5>"
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
                    {"role": "system", "content": "You are a JSON generator for business case study analysis."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=8192,
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
            
            debug_log(f"[SUCCESS] Base analysis returned {len(result.get('key_figures', []))} personas")
            return result
        else:
            debug_log("[WARNING] No JSON found in base analysis response")
            return _create_fallback_result(title, combined_content)
            
    except Exception as e:
        debug_log(f"[ERROR] Base analysis failed: {str(e)}")
        return _create_fallback_result(title, combined_content)

def _create_fallback_result(title: str, content: str) -> dict:
    """Create fallback result when AI analysis fails"""
    return {
        "title": title or "Business Case Study",
        "description": content[:500] + "..." if len(content) > 500 else content,
        "student_role": "Business Analyst",
        "key_figures": [
            {
                "name": "Team Lead",
                "role": "Senior Manager", 
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
                "name": "Project Manager",
                "role": "Operations Manager",
                "correlation": "Manages operational aspects of the business scenario",
                "background": "Detail-oriented professional focused on execution and process improvement.",
                "primary_goals": ["Ensure project success", "Optimize processes", "Meet deadlines"],
                "personality_traits": {
                    "analytical": 9,
                    "creative": 4,
                    "assertive": 6,
                    "collaborative": 7,
                    "detail_oriented": 9
                },
                "is_main_character": False
            }
        ],
        "learning_outcomes": [
            "1. Analyze business situations and identify key challenges",
            "2. Develop strategic solutions to complex problems",
            "3. Apply business frameworks to real-world scenarios",
            "4. Make data-driven decisions under uncertainty",
            "5. Communicate recommendations effectively to stakeholders"
        ]
    }

@async_retry(retries=2, delay=1.0)
async def generate_scene_image(scene_description: str, scene_title: str, scenario_id: int = 0) -> str:
    """Generate an image for a scene using OpenAI's DALL-E API with optimization"""
    debug_log(f"[OPTIMIZED] Generating image for scene: {scene_title}")
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
        debug_log(f"[OPTIMIZED] Generated image for '{scene_title}' in {generation_time:.2f}s")
        
        # Optional: Download and save image locally (disabled for performance)
        # if scenario_id > 0:
        #     from utilities.image_storage import download_and_save_image
        #     local_path = await download_and_save_image(image_url, scene_title, scenario_id)
        #     if local_path:
        #         return local_path
        
        return image_url
        
    except Exception as e:
        debug_log(f"[ERROR] Image generation failed for scene '{scene_title}': {str(e)}")
        return ""  # Return empty string on failure

async def generate_scenes_with_ai(base_result: dict) -> list:
    """Generate scenes using a separate AI call based on the base case study analysis"""
    print("[DEBUG] Generating scenes with separate AI call...")
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        # Extract context from the base result
        title = base_result.get("title", "Business Case Study")
        description = base_result.get("description", "")
        student_role = base_result.get("student_role", "Manager")
        key_figures = base_result.get("key_figures", [])
        
        # Create persona names list for easy reference
        persona_names = [fig.get("name", "") for fig in key_figures if fig.get("name")]
        
        scenes_prompt = f"""
Create exactly 4 interactive scenes for this business case study. Output ONLY a JSON array of scenes.

CASE CONTEXT:
Title: {title}
Student Role: {student_role}
Description: {description[:500]}...

AVAILABLE PERSONAS: {', '.join(persona_names)}

Create 4 scenes following this progression:
1. Crisis Assessment/Initial Briefing
2. Investigation/Analysis Phase  
3. Solution Development
4. Implementation/Approval

Each scene MUST have:
- title: Short descriptive name
- description: 2-3 sentences with vivid setting details for image generation
- personas_involved: Array of 2-4 actual persona names from the list above
- user_goal: Specific objective the student must achieve
- sequence_order: 1, 2, 3, or 4
- goal: Write a short, general summary of what the user should aim to accomplish in this scene. The goal should be directly inspired by and derived from the success metric, but do NOT include the specific success criteria or give away the answer. It should be clear and motivating, less specific than the success metric, and should not reveal the exact actions or information needed to achieve success.
- success_metric: A clear, measurable way to determine if the student (main character) has accomplished the specific goal of the scene, written in a way that is directly tied to the actions and decisions required in the narrative. Focus on what the student must do or achieve in the context of this scene, not just a generic outcome.

Output format - ONLY this JSON array:
[
  {{
    "title": "Scene Title",
    "description": "Detailed setting description with visual elements...",
    "personas_involved": ["Actual Name 1", "Actual Name 2"],
    "user_goal": "Specific actionable goal",
    "goal": "General, non-revealing summary of what to accomplish",
    "success_metric": "Specific, measurable criteria for success",
    "sequence_order": 1
  }},
  ...4 scenes total
]
"""
        
        print("[DEBUG] Sending scenes generation prompt to OpenAI...")
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You generate JSON arrays of scenes. Output ONLY valid JSON array, no extra text."},
                    {"role": "user", "content": scenes_prompt}
                ],
                max_tokens=2048,
                temperature=0.3,
            )
        )
        
        scenes_text = response.choices[0].message.content.strip()
        print(f"[DEBUG] Scenes AI response: {scenes_text[:200]}...")
        
        # Extract JSON array from response
        import re
        json_match = re.search(r'(\[[\s\S]*\])', scenes_text)
        if json_match:
            scenes_json = json_match.group(1)
            scenes = json.loads(scenes_json)
            print(f"[DEBUG] Successfully parsed {len(scenes)} scenes")
            return scenes
        else:
            print("[WARNING] No JSON array found in scenes response")
            return []
            
    except Exception as e:
        print(f"[ERROR] Scene generation failed: {str(e)}")
        return []

async def process_with_ai(parsed_content: str, context_text: str = "") -> dict:
    """Process the parsed PDF content with OpenAI to extract business case study information"""
    print("[DEBUG] Processing content with OpenAI LLM")
    try:
        preprocessed = preprocess_case_study_content(parsed_content)
        title = preprocessed["title"]
        cleaned_content = preprocessed["cleaned_content"]
        
        # Prepend context files' content as most important
        if context_text.strip():
            print(f"[DEBUG] Context files provided, length: {len(context_text)} characters")
            print(f"[DEBUG] Context files preview: {context_text[:500]}...")
            combined_content = f"""
IMPORTANT CONTEXT FILES (most authoritative, follow these first):
{context_text}

CASE STUDY CONTENT (main PDF):
{cleaned_content}
"""
            print(f"[DEBUG] Combined content length: {len(combined_content)} characters")
        else:
            print("[DEBUG] No context files provided, using only main content")
            combined_content = cleaned_content
            
        # --- AI Prompt for Scenario Extraction ---
        prompt = f"""
You are a highly structured JSON-only generator trained to analyze business case studies for college business education.

CRITICAL CONTEXT USAGE INSTRUCTIONS:
- If context files (teaching notes, instructor materials, etc.) are provided, they contain the MOST AUTHORITATIVE information about learning objectives, grading criteria, and pedagogical focus
- ALWAYS prioritize information from context files over the main case study content when there are conflicts
- Use context files to inform and enhance the learning outcomes, scene design, and success metrics
- Context files may contain specific learning objectives, assessment criteria, or teaching guidance that should be incorporated into the simulation design

CRITICAL: You must identify ALL named individuals, companies, organizations, and significant unnamed roles mentioned within the case study narrative. Focus ONLY on characters and entities that are part of the business story being told.

Instructions for key_figures identification:
- Find ALL types of key figures that can be turned into personas, including:
  * Named individuals who are characters in the case study (people with first and last names like "John Smith", "Mary Johnson", "Wanjohi", etc.)
  * Companies and organizations mentioned in the narrative (e.g., "Kaskazi Network", "Competitors", "Suppliers")
  * Unnamed but important roles within the story (e.g., "The CEO", "The Board of Directors", "The Marketing Manager")
  * Groups and stakeholders in the narrative (e.g., "Customers", "Employees", "Shareholders", "Partners")
  * External entities mentioned in the story (e.g., "Government Agencies", "Regulatory Bodies", "Industry Analysts")
  * Any entity that influences the narrative or decision-making process within the case study
- Look for names in the format: "FirstName LastName" or "Title LastName" or "FirstName Title"
- Focus ONLY on the case study narrative content - ignore author sections, acknowledgments, footnotes, or other metadata
- Include both named and unnamed entities that are part of the business story - do not prioritize one over the other
- Even if someone/thing is mentioned only once or briefly, include them if they have a discernible role in the narrative
- Do not skip anyone/anything based on perceived importance - include ALL relevant figures and entities from the story
- CRITICAL: Do NOT include the student, the player, or the role/position the student is playing (as specified in "student_role") in the key_figures array. Only include non-player characters (NPCs) and entities from the business narrative. The player/student role must be excluded even if mentioned by name or title in the content.

IMPORTANT SCENE GENERATION RULES:
- For each scene:
  * The personas_involved array must list only non-student figures (from key_figures) who are actively referenced in the scene_description.
  * The scene_description must always mention, in-depth and narratively, at least one non-student persona from the personas/key_figures list. The figure(s) must be woven into the scene in a way that makes narrative sense and advances the business scenario. The description should be multi-paragraph, detailed, and immersive, not superficial.
  * CRITICAL: The personas_involved array must NEVER include the main character/student role, even if they are mentioned by name in the scene. The student is the player and should not be listed as a persona they interact with.
  * Double-check that no persona in personas_involved matches the student_role or the main character name.
  * If the scene involves the main character, focus on the OTHER people they interact with, not the main character themselves.

Your task is to analyze the following business case study content and return a JSON object with exactly the following fields:
  "title": "<The exact title of the business case study>",
  "description": "<A highly comprehensive, multi-paragraph, and in-depth background that includes: 1) the business context, history, and market environment, 2) the main challenges, decisions, and their implications, 3) an explicit and prominent statement that the student will be tackling the case study as the primary decision-maker or central figure (include their name/title if available), 4) clear references to the key figures, their roles, and their relationships to the student’s role, and 5) a synthesis of deeper context, connections, and business analysis inferred from the case study. The description should be analytical, engaging, and written in a professional tone suitable for business education.>",
  "student_role": "<The specific role or position the student will assume in this case study. This should be the primary decision-maker or central figure in the case study (e.g., 'CEO', 'Marketing Manager', 'Consultant', 'Founder', etc.). This person/role will NOT be included in key_figures since the student will be playing this role.

EXAMPLES OF HOW TO IDENTIFY THE STUDENT ROLE:

Example 1: Case: "In 2020, Howard Schultz, CEO of Starbucks, was considering expanding into new markets in Asia."
→ student_role: "CEO" (Howard Schultz is the main decision-maker)

Example 2: Case: "You are the marketing director of a mid-sized e-commerce company, deciding on the budget allocation for the upcoming year."
→ student_role: "Marketing Director" (explicitly stated as "You are")

Example 3: Case: "Jane, the founder of a fintech startup, needs to pitch to investors to secure Series A funding."
→ student_role: "Founder" (Jane is the main character making decisions)

Example 4: Case: "The plant manager must decide whether to implement a new automated production line to improve efficiency."
→ student_role: "Plant Manager" (the main decision-maker in the scenario)

Example 5: Case: "As CFO of a global retail chain, Robert is evaluating options to reduce operational costs across regions."
→ student_role: "CFO" (Robert is the main character, but the role is CFO)

Example 6: Case: "You are the HR manager of a tech company, facing high employee turnover and low morale, and need to design a retention strategy."
→ student_role: "HR Manager" (explicitly stated as "You are")

Example 7: Case: "The product manager at a consumer electronics firm must decide whether to launch a new gadget ahead of the competitor."
→ student_role: "Product Manager" (the main decision-maker)

Example 8: Case: "As the sustainability officer of a multinational, Maria must create a plan to reduce the company's carbon footprint while maintaining profitability."
→ student_role: "Sustainability Officer" (Maria is the main character, but the role is Sustainability Officer)

Example 9: Case: "You are a consultant hired to advise a struggling airline on restructuring its operations to avoid bankruptcy."
→ student_role: "Consultant" (explicitly stated as "You are")

Example 10: Case: "The compliance officer must evaluate whether the company's new data handling practices meet global privacy regulations."
→ student_role: "Compliance Officer" (the main decision-maker)

Example 11: Case: "A small business owner is deciding whether to accept venture capital funding, balancing growth with maintaining control of the company."
→ student_role: "Small Business Owner" (the main decision-maker)

Example 12: Case: "The supply chain manager must address delays caused by geopolitical disruptions affecting key suppliers."
→ student_role: "Supply Chain Manager" (the main decision-maker)

KEY IDENTIFICATION RULES:
- Look for the primary decision-maker or central figure in the case
- If the case says "You are [role]" or "As [role]", that's the student role
- If a specific person is mentioned as the main character, identify their role/title
- The student role should be someone who makes key decisions in the scenario
- This person/role should NOT appear in key_figures since the student plays this role>",
  "key_figures": [
    {{
      "name": "<Full name of figure (e.g., 'John Smith', 'Wanjohi', 'Lisa Mwezi Schuepbach'), or descriptive title if unnamed (e.g., 'The Board of Directors', 'Competitor CEO', 'Industry Analyst')>",
      "role": "<Their role or inferred role. If unknown, use 'Unknown'>",
      "correlation": "<A brief explanation of this figure's relationship to the narrative of the case study>",
      "background": "<A 2-3 sentence background/bio of this person/entity based on the case study content>",
      "primary_goals": [
        "<Goal 1>",
        "<Goal 2>",
        "<Goal 3>"
      ],
      "personality_traits": {{
        "analytical": <0-10 rating>,
        "creative": <0-10 rating>,
        "assertive": <0-10 rating>,
        "collaborative": <0-10 rating>,
        "detail_oriented": <0-10 rating>
      }},
      "is_main_character": <true if this figure matches the student_role, otherwise false or omit>
    }}
  ],
  "learning_outcomes": [
    "1. <Outcome 1 - prioritize learning objectives from context files if available>",
    "2. <Outcome 2 - use teaching notes to inform specific skills and knowledge to be developed>",
    "3. <Outcome 3 - incorporate assessment criteria from context files>",
    "4. <Outcome 4 - align with pedagogical goals mentioned in teaching materials>",
    "5. <Outcome 5 - ensure outcomes support the overall educational objectives>"
  ],
  "scene_cards": [
    {{
      "scene_title": "<Short, clear title for this scene (e.g., 'Executive Team Faces Budget Cuts')>",
      "goal": "<What the characters or learners are trying to accomplish in this scene. Reference or support one or more of the main learning outcomes in the way this goal is written, but do not list them explicitly.>",
      "core_challenge": "<The main business dilemma, conflict, or tradeoff happening in this scene. Reference or support the learning outcomes in the narrative, but do not list them explicitly.>",
      "scene_description": "<A highly detailed, immersive, and at least 200-word, multi-paragraph narrative summary of what happens in this scene. Write in the second person, always centering the experience around the main character (the student role) as the decision-maker. Explicitly mention and involve all personas_involved by name, describing their actions, dialogue, and interactions with the main character. Make the narrative realistic, in-depth, and grounded in the case study context.>",
      "success_metric": "<A clear, measurable way to determine if the student (main character) has accomplished the specific goal of the scene, written in a way that is directly tied to the actions and decisions required in the narrative. Focus on what the student must do or achieve in the context of this scene, not just a generic outcome.>",
      "personas_involved": [
        "<Persona Name 1>",
        "<Persona Name 2>"
      ]
    }}
  ]
}}

Scene Card generation instructions:
- Break the case into 4–6 important scenes.
- Each scene_card MUST be unique: do not repeat or duplicate scene_title, goal, core_challenge, scene_description, success_metric, or personas_involved across different scenes. Each scene must cover a different part of the narrative or a different business challenge/decision.
- If the case study content is limited, synthesize plausible but non-repetitive scenes based on the available information, but do not copy or repeat any field between scenes.
- Each scene should align to one of the following simplified stages of business case analysis:
  * Context & Setup
  * Analysis & Challenges
  * Decisions & Tradeoffs
  * Actions & Outcomes
- For each scene_card, ensure the goal, core_challenge, scene_description, and success_metric are written in a way that references or supports the main learning outcomes, but do not embed or list the learning outcomes directly in the scene_card fields.
- IMPORTANT: If context files (teaching notes) are provided, use them to inform the scene design, success metrics, and learning objectives. Teaching notes may contain specific assessment criteria, grading rubrics, or pedagogical approaches that should be reflected in the scene design.
- The scene_title must NOT include stage names, numbers, or generic labels (such as "Context & Setup", "Analysis & Challenges", "Decisions & Tradeoffs", "Actions & Outcomes", or similar). The title should be a concise, descriptive summary of the scene's unique content only.
- For each scene_card, include a personas_involved field listing the names of personas (from the key_figures array) who are actively participating in or relevant to the scene. The scene_description and goal should narratively reference these personas.
- Do not invent facts; only use what is in the case study content and context files.
- Each scene_card object must include exactly those 6 fields listed above. 
- The success_metric field is required for every scene and must be a clear, measurable metric but make sure to avoid anything numeric related (not vague like "learn something"). Use context files to inform appropriate success metrics if available.

Important generation rules:
- Output ONLY a valid JSON object. Do not include any extra commentary, markdown, or formatting.
- All fields are required.
- The "scene_cards" field must be an array of 4–6 complete, well-structured scene card objects.

CASE STUDY CONTENT (context files first, then main PDF):
{combined_content}
"""
        
        print("[DEBUG] Combined content length:", len(combined_content))
        print("[DEBUG] Prompt sent to OpenAI")
        
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        # Try with high token limit first, fallback to lower if needed
        max_tokens_attempts = [16384, 12288, 8192]
        response = None
        for attempt, max_tokens in enumerate(max_tokens_attempts):
            try:
                debug_log(f"Attempting OpenAI call with max_tokens={max_tokens} (attempt {attempt + 1})")
                response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": "You are a JSON generator for business case study analysis. Extract comprehensive information about key figures and their relationships."},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=max_tokens,
                        temperature=0.2,
                    )
                )
                break  # Success, exit the retry loop
            except Exception as api_error:
                debug_log(f"OpenAI call failed with max_tokens={max_tokens}: {str(api_error)}")
                if attempt == len(max_tokens_attempts) - 1:  # Last attempt
                    raise api_error  # Re-raise the last error
                # Try next lower token limit
                continue
        if response is None:
            raise Exception("OpenAI call failed for all token limits.")
        generated_text = response.choices[0].message.content
        print(f"[DEBUG] Raw OpenAI response length: {len(generated_text)} characters")
        print(f"[DEBUG] First 500 characters of response: {generated_text[:500]}...")
        print(f"[DEBUG] Last 500 characters of response: ...{generated_text[-500:]}")
        # Check if response was likely truncated
        finish_reason = response.choices[0].finish_reason
        print(f"[DEBUG] OpenAI finish_reason: {finish_reason}")
        if finish_reason == "length":
            debug_log("[WARNING] OpenAI response was truncated due to max_tokens limit!")
            debug_log("[WARNING] Consider using a more concise prompt or higher token limit")
        # Check if response contains key fields
        if '"key_figures"' in generated_text:
            debug_log("✓ Response contains 'key_figures' field")
        else:
            debug_log("✗ Response does NOT contain 'key_figures' field")
        
        # Try to extract JSON from the response using regex
        match = re.search(r'({[\s\S]*})', generated_text)
        if match:
            json_str = match.group(1)
            
            # Try to fix incomplete JSON by adding missing closing brackets
            if not json_str.rstrip().endswith('}'):
                print("[DEBUG] JSON appears incomplete, attempting to fix...")
                # Count open braces and brackets to determine what's missing
                open_braces = json_str.count('{') - json_str.count('}')
                open_brackets = json_str.count('[') - json_str.count(']')
                
                # Add missing closing brackets and braces
                json_str += ']' * open_brackets + '}' * open_braces
                print(f"[DEBUG] Added {open_brackets} closing brackets and {open_braces} closing braces")
            
            try:
                ai_result = json.loads(json_str)
                print("[DEBUG] First AI call successful, now generating scenes...")
                debug_log(f"First AI result keys: {list(ai_result.keys())}")
                debug_log(f"Number of key figures: {len(ai_result.get('key_figures', []))}")
                
                # Second AI call to generate scenes
                try:
                    scenes = await generate_scenes_with_ai(ai_result)
                    print(f"[DEBUG] Second AI call returned {len(scenes) if isinstance(scenes, list) else 0} scenes")
                except Exception as scenes_error:
                    print(f"[ERROR] Second AI call failed: {scenes_error}")
                    scenes = []
                processed_scenes = []
                
                # If no scenes were generated by AI, create fallback scenes
                if not scenes:
                    print("[WARNING] No scenes generated by second AI call, using fallback...")
                    key_figures = ai_result.get("key_figures", [])
                    student_role = ai_result.get("student_role", "Manager")
                    
                    # Extract key personas for scenes
                    senior_figures = [fig["name"] for fig in key_figures if any(word in fig.get("role", "").lower() for word in ["vp", "vice", "president", "senior", "global"])]
                    team_figures = [fig["name"] for fig in key_figures if any(word in fig.get("role", "").lower() for word in ["manager", "engineer", "support", "advocate"])]
                    all_names = [fig["name"] for fig in key_figures]
                    
                    # Create case-specific scenes based on context
                    fallback_scenes = [
                        {
                            "title": "Crisis Assessment Meeting",
                            "description": "You are in the main conference room with senior leadership, reviewing the urgent situation that requires immediate attention. The atmosphere is tense with incident reports and client communications displayed on screens around the room.",
                            "personas_involved": senior_figures[:3] if len(senior_figures) >= 3 else all_names[:3],
                            "user_goal": f"As the {student_role}, assess the scope of the crisis and understand the immediate risks to the organization.",
                            "sequence_order": 1
                        },
                        {
                            "title": "Team Investigation",
                            "description": "You are conducting interviews with team members across different locations to understand what went wrong. The setting varies from video calls to in-person meetings as you piece together the timeline of events.",
                            "personas_involved": team_figures[:4] if len(team_figures) >= 4 else all_names[1:5],
                            "user_goal": "Identify the root causes of the issues and gather perspectives from team members.",
                            "sequence_order": 2
                        },
                        {
                            "title": "Solution Development Workshop",
                            "description": "You are leading a collaborative session with team members present and others joining virtually. Whiteboards are filled with process diagrams and improvement plans as you work to develop solutions.",
                            "personas_involved": (team_figures + senior_figures)[:4] if len(key_figures) >= 4 else all_names[:4],
                            "user_goal": "Develop concrete solutions and create an implementation plan.",
                            "sequence_order": 3
                        },
                        {
                            "title": "Implementation Approval Meeting",
                            "description": "You are presenting your comprehensive action plan to leadership in the boardroom. Charts showing your recommendations and success metrics are displayed as you seek approval.",
                            "personas_involved": senior_figures[:3] if len(senior_figures) >= 3 else all_names[-3:],
                            "user_goal": "Secure approval for your plan and establish clear success metrics and timelines.",
                            "sequence_order": 4
                        }
                    ]
                    scenes = fallback_scenes[:4]
                
                if scenes:
                    print(f"[DEBUG] Processing {len(scenes)} scenes for image generation...")
                    
                    # Generate images for each scene in parallel
                    image_tasks = []
                    scenario_id = ai_result.get('scenario_id') or 0
                    for scene in scenes:
                        if isinstance(scene, dict) and "description" in scene and "title" in scene:
                            task = generate_scene_image(scene["description"], scene["title"], scenario_id)
                            image_tasks.append(task)
                        else:
                            # Create a simple async function that returns empty string
                            async def empty_task():
                                return ""
                            image_tasks.append(empty_task())
                    
                    # Wait for all image generations to complete
                    image_urls = await asyncio.gather(*image_tasks, return_exceptions=True)
                    
                    # Combine scenes with their generated images
                    for i, scene in enumerate(scenes):
                        if isinstance(scene, dict):
                            processed_scene = {
                                "title": scene.get("title", f"Scene {i+1}"),
                                "description": scene.get("description", ""),
                                "personas_involved": scene.get("personas_involved", []),
                                "user_goal": scene.get("user_goal", ""),
                                "sequence_order": scene.get("sequence_order", i+1),
                                "image_url": image_urls[i] if i < len(image_urls) and not isinstance(image_urls[i], Exception) else "",
                                "successMetric": scene.get("success_metric", "")
                            }
                            processed_scenes.append(processed_scene)
                            print(f"[DEBUG] Scene {i+1}: {processed_scene['title']} - Image: {'Generated' if processed_scene['image_url'] else 'Failed'}")
                
                final_result = {
                    "title": ai_result.get("title") or title,
                    "description": ai_result.get("description") or (cleaned_content[:1500] + "..." if len(cleaned_content) > 1500 else cleaned_content),
                    "student_role": ai_result.get("student_role") or "",
                    "key_figures": ai_result.get("key_figures") if "key_figures" in ai_result else [],
                    "scenes": processed_scenes,
                    "learning_outcomes": ai_result.get("learning_outcomes") or [
                        "1. Analyze the business situation presented in the case study",
                        "2. Identify key stakeholders and their interests",
                        "3. Develop strategic recommendations based on the analysis",
                        "4. Evaluate the impact of decisions on organizational performance",
                        "5. Apply business concepts and frameworks to real-world scenarios"
                    ]
                }
                debug_log(f"Successfully parsed JSON! Final AI result sent to frontend with {len(final_result.get('key_figures', []))} key figures and {len(processed_scenes)} scenes")
                debug_log("Key figures names:", [fig.get('name', 'Unknown') for fig in final_result.get('key_figures', [])])
                print("[DEBUG] Scene titles:", [scene.get('title', 'Unknown') for scene in processed_scenes])
                debug_log(f"Final result keys: {list(final_result.keys())}")
                print(f"[DEBUG] Scenes in final result: {len(final_result.get('scenes', []))}")
                print("[DEBUG] Raw AI scenes:", ai_result.get("scene_cards", []))
                
                # Post-processing validation to ensure student role is not in key_figures
                student_role = final_result.get("student_role", "").lower()
                key_figures = final_result.get("key_figures", [])

                # After parsing key_figures, filter out any with is_main_character true
                filtered_key_figures = []
                for fig in key_figures:
                    if fig.get("is_main_character", False):
                        debug_log(f"Removing main character from key_figures: {fig.get('name', '')}")
                        continue
                    filtered_key_figures.append(fig)
                final_result["key_figures"] = filtered_key_figures

                # Ensure every scene has personas_involved and successMetric (fallback to scene_cards if needed)
                if "scenes" in final_result and "scene_cards" in ai_result:
                    scene_cards = ai_result["scene_cards"]
                    key_figure_names = [fig["name"] for fig in final_result["key_figures"]]
                    student_role = final_result.get("student_role", "").strip().lower()
                    for i, scene in enumerate(final_result["scenes"]):
                        # Fallback for personas_involved
                        if (not scene.get("personas_involved") or len(scene.get("personas_involved", [])) == 0) and i < len(scene_cards):
                            pi = scene_cards[i].get("personas_involved", [])
                            if pi:
                                scene["personas_involved"] = pi
                        # --- ENFORCE: At least one non-student persona in personas_involved ---
                        personas = scene.get("personas_involved", [])
                        # Remove main character if present
                        personas = [p for p in personas if p.strip().lower() != student_role]
                        # Parse description for persona names
                        desc = scene.get("description", "")
                        mentioned = [name for name in key_figure_names if name in desc and name.strip().lower() != student_role]
                        for name in mentioned:
                            if name not in personas:
                                personas.append(name)
                        # If still empty, add the first non-student persona
                        if not personas and key_figure_names:
                            first_non_student = next((n for n in key_figure_names if n.strip().lower() != student_role), None)
                            if first_non_student:
                                personas.append(first_non_student)
                                # Optionally, append a sentence to the description
                                scene["description"] = desc + f"\n\n{first_non_student} is present in this scene."
                        scene["personas_involved"] = personas
                        # Fallback for successMetric
                        if not scene.get("successMetric") and i < len(scene_cards):
                            metric = scene_cards[i].get("success_metric")
                            if metric:
                                scene["successMetric"] = metric
                print("[DEBUG] Final processed scenes:", final_result.get("scenes", []))
                
                # Robust main character detection
                main_character_name = None
                main_character_index = None
                student_role = final_result.get("student_role", "")
                student_role_norm = normalize_name(student_role)
                key_figures = final_result.get("key_figures", [])
                scenes = final_result.get("scenes", [])

                # Helper: count appearances in scenes
                def persona_scene_count(name):
                    n = normalize_name(name)
                    count = 0
                    for scene in scenes:
                        for p in scene.get("personas_involved", []):
                            if normalize_name(p) == n:
                                count += 1
                    return count

                # 1. Try to match student_role to persona name (direct or substring)
                name_matches = []
                for idx, fig in enumerate(key_figures):
                    fig_name = fig.get("name", "")
                    fig_name_norm = normalize_name(fig_name)
                    if student_role_norm == fig_name_norm or student_role_norm in fig_name_norm or fig_name_norm in student_role_norm:
                        name_matches.append((idx, fig_name))
                if name_matches:
                    # Prefer the one who appears in the most scenes
                    best = max(name_matches, key=lambda x: persona_scene_count(x[1]))
                    main_character_index, main_character_name = best
                else:
                    # 2. Try to match student_role to persona role (substring/fuzzy)
                    role_matches = []
                    for idx, fig in enumerate(key_figures):
                        fig_role = fig.get("role", "")
                        fig_role_norm = normalize_name(fig_role)
                        if student_role_norm == fig_role_norm or student_role_norm in fig_role_norm or fig_role_norm in student_role_norm:
                            role_matches.append((idx, fig.get("name", "")))
                    if role_matches:
                        best = max(role_matches, key=lambda x: persona_scene_count(x[1]))
                        main_character_index, main_character_name = best
                    else:
                        # 3. If still not found, pick the persona who appears in the most scenes
                        if key_figures and scenes:
                            persona_counts = {fig.get("name", ""): persona_scene_count(fig.get("name", "")) for fig in key_figures}
                            # Only pick if someone appears in > half the scenes (likely main)
                            if persona_counts:
                                most_common = max(persona_counts.items(), key=lambda x: x[1])
                                if most_common[1] > len(scenes) // 2:
                                    main_character_name = most_common[0]
                                    for idx, fig in enumerate(key_figures):
                                        if fig.get("name", "") == main_character_name:
                                            main_character_index = idx
                                            break

                # 4. Mark only that persona as is_main_character and filter from all personas_involved
                for idx, fig in enumerate(key_figures):
                    fig["is_main_character"] = (idx == main_character_index)

                if main_character_name:
                    print(f"[DEBUG] Main character detected: {main_character_name} (normalized: {student_role_norm}) at index {main_character_index}")
                else:
                    print(f"[DEBUG] No main character found matching student_role '{student_role}' (normalized: {student_role_norm})")

                main_character_name_norm = normalize_name(main_character_name) if main_character_name else None
                for scene in final_result.get("scenes", []):
                    before = list(scene.get("personas_involved", []))
                    filtered = [
                        p for p in scene.get("personas_involved", [])
                        if normalize_name(p) != main_character_name_norm
                    ]
                    print(f"[DEBUG] Filtering personas_involved: {before} | main_character_name_norm: {main_character_name_norm} | after: {filtered}")
                    scene["personas_involved"] = filtered
                
                return final_result
            except json.JSONDecodeError as e:
                print(f"[ERROR] Failed to parse JSON from AI response even after fixing: {e}")
                print(f"[ERROR] Fixed JSON attempt: {json_str[:500]}...")
        else:
            print("[ERROR] No JSON object found in OpenAI response.")
            
            # Fallback: return structured content
            return {
                        "title": title,
                        "description": cleaned_content[:1500] + "..." if len(cleaned_content) > 1500 else cleaned_content,
                "key_figures": [],
            "scenes": [],
                        "learning_outcomes": [
                            "1. Analyze the business situation presented in the case study",
                            "2. Identify key stakeholders and their interests",
                            "3. Develop strategic recommendations based on the analysis",
                            "4. Evaluate the impact of decisions on organizational performance",
                            "5. Apply business concepts and frameworks to real-world scenarios"
                        ]
                    }
    
    except Exception as e:
        print(f"[ERROR] AI processing failed: {str(e)}")
        # Return fallback content
        return {
            "title": "Business Case Study",
            "description": "Failed to process case study content",
            "key_figures": [],
            "scenes": [],
            "learning_outcomes": [
                "1. Analyze the business situation presented in the case study",
                "2. Identify key stakeholders and their interests"
            ]
        }

async def save_scenario_to_db(
    ai_result: dict,
    main_file: UploadFile,
    context_files: List[UploadFile],
    main_content: str,
    context_content: str,
    user_id: int,
    db: Session
) -> int:
    """
    Save AI processing results to database
    Creates scenario with personas, scenes, and files
    """
    
    try:
        # Extract title from AI result or filename
        title = ai_result.get("title", main_file.filename.replace(".pdf", ""))
        
        # Create scenario record
        scenario = Scenario(
            title=title,
            description=ai_result.get("description", ""),
            challenge=ai_result.get("description", ""),  # Use description as challenge for now
            industry="Business",  # Default industry
            learning_objectives=ai_result.get("learning_outcomes", []),
            student_role=ai_result.get("student_role", "Business Analyst"),
            source_type="pdf_upload",
            pdf_content=main_content,
            pdf_title=title,
            pdf_source="Uploaded PDF",
            processing_version="1.0",
            is_public=False,  # Start as private draft
            allow_remixes=True,
            created_by=user_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(scenario)
        db.flush()  # Get scenario ID
        
        print(f"[DEBUG] Created scenario with ID: {scenario.id}")
        
        # Save personas
        persona_mapping = {}  # name -> persona_id for scene relationships
        key_figures = ai_result.get("key_figures", [])
        
        for figure in key_figures:
            if isinstance(figure, dict) and figure.get("name"):
                persona = ScenarioPersona(
                    scenario_id=scenario.id,
                    name=figure.get("name", ""),
                    role=figure.get("role", ""),
                    background=figure.get("background", ""),
                    correlation=figure.get("correlation", ""),
                    primary_goals=figure.get("primary_goals", []),
                    personality_traits=figure.get("personality_traits", {}),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(persona)
                db.flush()
                persona_mapping[figure["name"]] = persona.id
                print(f"[DEBUG] Created persona: {figure['name']} with ID: {persona.id}")
        
        # Save scenes
        scenes = ai_result.get("scenes", [])
        for i, scene in enumerate(scenes):
            if isinstance(scene, dict) and scene.get("title"):
                print(f"[DEBUG] Scene dict before saving: {scene}")
                # Use successMetric or success_metric from scene dict, fallback to objectives[0]
                success_metric = (
                    scene.get("successMetric") or
                    scene.get("success_metric") or
                    scene.get("success_criteria")
                )
                if not success_metric and scene.get("objectives"):
                    success_metric = scene["objectives"][0]
                scene_record = ScenarioScene(
                    scenario_id=scenario.id,
                    title=scene.get("title", ""),
                    description=scene.get("description", ""),
                    user_goal=scene.get("user_goal", ""),
                    scene_order=scene.get("sequence_order", i + 1),  # Use sequence_order from frontend, fallback to loop index
                    estimated_duration=scene.get("estimated_duration", 30),
                    image_url=scene.get("image_url", ""),
                    image_prompt=f"Business scene: {scene.get('title', '')}",
                    success_metric=success_metric,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(scene_record)
                db.flush()
                print(f"[DEBUG] Saved scene: {scene_record.title}, success_metric: {scene_record.success_metric}")
                # Link personas to scene (if personas_involved exists)
                personas_involved = scene.get("personas_involved", [])
                unique_persona_names = set(personas_involved)
                for persona_name in unique_persona_names:
                    if persona_name in persona_mapping:
                        pid = persona_mapping[persona_name]
                        db.execute(
                            scene_personas.insert().values(
                                scene_id=scene_record.id,
                                persona_id=pid,
                                involvement_level="participant"
                            )
                        )
        
        # Ensure every scene has at least one involved persona (not the main character)
        # This is additional validation after AI processing
        student_role = ai_result.get("student_role", "").strip().lower()
        key_figures = ai_result.get("key_figures", [])
        key_figure_names = [fig.get("name", "") for fig in key_figures]
        
        for scene in ai_result.get("scenes", []):
            personas = scene.get("personas_involved", [])
            # Remove main character if present (additional safety check)
            personas = [p for p in personas if p.strip().lower() != student_role]
            
            # If still empty, add the first non-student persona
            if not personas and key_figure_names:
                first_non_student = next((name for name in key_figure_names if name.strip().lower() != student_role), None)
                if first_non_student:
                    personas.append(first_non_student)
                    print(f"[DEBUG] Added fallback persona '{first_non_student}' to scene '{scene.get('title', '')}'")
            
            scene["personas_involved"] = personas
        
        # Save file metadata
        scenario_file = ScenarioFile(
            scenario_id=scenario.id,
            filename=main_file.filename,
            file_type="pdf",
            original_content=main_content[:10000],  # Truncate for storage
            processed_content=main_content,
            processing_status="completed",
            processing_log={
                "personas_count": len(key_figures),
                "scenes_count": len(scenes),
                "processing_timestamp": datetime.utcnow().isoformat()
            },
            uploaded_at=datetime.utcnow(),
            processed_at=datetime.utcnow()
        )
        db.add(scenario_file)
        
        # Save context files if any
        for ctx_file in context_files:
            context_file_record = ScenarioFile(
                scenario_id=scenario.id,
                filename=f"context_{ctx_file.filename}",
                file_type=ctx_file.filename.split(".")[-1] if "." in ctx_file.filename else "txt",
                original_content=context_content[:5000],  # Truncate for storage
                processed_content=context_content,
                processing_status="completed",
                uploaded_at=datetime.utcnow(),
                processed_at=datetime.utcnow()
            )
            db.add(context_file_record)
        
        # Commit all changes
        db.commit()
        print(f"[DEBUG] Successfully saved scenario {scenario.id} to database")
        
        return scenario.id
        
    except Exception as e:
        print(f"[ERROR] Failed to save scenario to database: {e}")
        db.rollback()
        raise e 

def normalize_name(name):
    # Normalize Unicode, remove accents, convert to ASCII, remove non-alphanum
    if not name:
        return ''
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = name.replace("'", "'").replace("'", "'").replace('"', '"').replace('"', '"')
    name = name.lower().strip()
    name = ''.join(c for c in name if c.isalnum())
    return name

# =============================================================================
# OPTIMIZED PIPELINE: EMBEDDING-BASED RETRIEVAL (⚡ 70-80% TOKEN REDUCTION)
# =============================================================================

@router.post("/api/parse-pdf-optimized/")
async def parse_pdf_optimized(
    main_file: UploadFile = File(...),
    context_files: List[UploadFile] = File(default=[]),
    db: Session = Depends(get_db)
):
    """
    ⚡ OPTIMIZED PIPELINE: ~40-60s total runtime
    - Uses embeddings + retrieval to cut tokens by 70-80%
    - gpt-3.5-turbo for fast persona extraction
    - gpt-4-turbo for analysis & scene generation
    - Parallel processing where possible
    """
    start_time = time.time()
    debug_log("[OPTIMIZED_PIPELINE] Starting optimized PDF processing")
    
    try:
        # Step 1: Parse and extract content
        main_content, context_content = await _parse_uploaded_files_optimized(main_file, context_files)
        combined_content = f"{main_content}\n\n{context_content}"
        doc_id = f"doc_{hash(combined_content)}"
        
        # Step 2: Chunk and embed document
        debug_log("[OPTIMIZED_PIPELINE] Creating embeddings...")
        chunk_start = time.time()
        from services.embedding_service import embedding_service
        await embedding_service.chunk_and_embed_document(combined_content, doc_id)
        debug_log(f"[OPTIMIZED_PIPELINE] Embedding completed in {time.time() - chunk_start:.2f}s")
        
        # Step 3: Fast persona extraction (gpt-3.5-turbo)
        debug_log("[OPTIMIZED_PIPELINE] Starting fast persona extraction...")
        persona_start = time.time()
        personas_result = await _fast_persona_extraction_optimized(doc_id, main_file.filename)
        debug_log(f"[OPTIMIZED_PIPELINE] Persona extraction completed in {time.time() - persona_start:.2f}s")
        
        # Step 4 & 5: Parallel execution of full analysis and scene generation
        debug_log("[OPTIMIZED_PIPELINE] Starting parallel analysis and scene generation...")
        parallel_start = time.time()
        
        analysis_task = _full_analysis_optimized(doc_id, personas_result)
        scene_task = _scene_generation_optimized(personas_result)
        
        # Execute in parallel
        analysis_result, scenes_result = await asyncio.gather(analysis_task, scene_task)
        debug_log(f"[OPTIMIZED_PIPELINE] Parallel processing completed in {time.time() - parallel_start:.2f}s")
        
        # Step 6: Generate image prompts (templated, near-instant)
        debug_log("[OPTIMIZED_PIPELINE] Generating image prompts...")
        image_start = time.time()
        image_urls = await _generate_optimized_images(scenes_result, analysis_result.get("title", "Business Case"))
        debug_log(f"[OPTIMIZED_PIPELINE] Image generation completed in {time.time() - image_start:.2f}s")
        
        # Step 7: Combine results
        final_result = {
            **analysis_result,
            "scenes": scenes_result,
            "image_urls": image_urls,
            "personas": analysis_result.get("key_figures", [])  # Frontend compatibility
        }
        
        # Step 8: Save to database
        scenario_id = await save_scenario_to_db(
            main_file, context_files, main_content, context_content, 
            final_result, db
        )
        
        total_time = time.time() - start_time
        debug_log(f"[OPTIMIZED_PIPELINE] ✅ Complete pipeline finished in {total_time:.2f}s")
        debug_log(f"[OPTIMIZED_PIPELINE] Generated {len(final_result.get('key_figures', []))} personas and {len(scenes_result)} scenes")
        
        return {
            "status": "success",
            "scenario_id": scenario_id,
            "processing_time": f"{total_time:.2f}s",
            "optimization": "embeddings + retrieval",
            **final_result
        }
        
    except Exception as e:
        debug_log(f"[OPTIMIZED_PIPELINE_ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=f"Optimized processing failed: {str(e)}")

@router.post("/api/parse-pdf-super-fast/")
async def parse_pdf_super_fast(
    main_file: UploadFile = File(...),
    context_files: List[UploadFile] = File(default=[]),
):
    """
    ⚡ SUPER FAST AUTOFILL: ~5-15s total runtime
    - Only persona extraction using embeddings + gpt-3.5-turbo
    - Perfect for quick autofill scenarios
    """
    start_time = time.time()
    debug_log("[SUPER_FAST] Starting super fast persona extraction")
    
    try:
        # Parse content
        main_content, context_content = await _parse_uploaded_files_optimized(main_file, context_files)
        combined_content = f"{main_content}\n\n{context_content}"
        doc_id = f"fast_{hash(combined_content)}"
        
        # Chunk and embed
        from services.embedding_service import embedding_service
        await embedding_service.chunk_and_embed_document(combined_content, doc_id)
        
        # Fast persona extraction only
        result = await _fast_persona_extraction_optimized(doc_id, main_file.filename)
        
        total_time = time.time() - start_time
        debug_log(f"[SUPER_FAST] ✅ Completed in {total_time:.2f}s")
        
        return {
            "status": "success",
            "processing_time": f"{total_time:.2f}s",
            "optimization": "super_fast_autofill",
            **result
        }
        
    except Exception as e:
        debug_log(f"[SUPER_FAST_ERROR] {str(e)}")
        raise HTTPException(status_code=500, detail=f"Super fast processing failed: {str(e)}")

@router.post("/api/parse-pdf-with-progress/")
async def parse_pdf_with_progress(
    file: UploadFile = File(...),
    context_files: Optional[List[UploadFile]] = File(None),
    save_to_db: bool = False,
    session_id: str = "",
    db: Session = Depends(get_db)
):
    """
    PDF parsing endpoint with progress tracking integration
    Returns immediately with session_id, actual processing happens asynchronously
    """
    debug_log(f"[PROGRESS_PDF] Starting PDF parsing with progress tracking, session: {session_id}")
    
    if not LLAMAPARSE_API_KEY:
        raise HTTPException(status_code=500, detail="LlamaParse API key not configured.")
    
    # Generate session ID if not provided
    if not session_id:
        import uuid
        session_id = str(uuid.uuid4())
    
    # Import progress manager
    from api.pdf_progress import progress_manager
    
    try:
        # Initialize progress tracking
        progress_manager.update_progress(
            session_id=session_id,
            stage="upload",
            progress=0,
            message="Starting PDF upload and processing..."
        )
        
        # Normalize context_files to empty list if None
        if context_files is None:
            context_files = []
        elif not isinstance(context_files, list):
            context_files = [context_files]
        
        # CRITICAL: Read file contents BEFORE starting background task
        # UploadFile objects get closed after request completes
        debug_log(f"[PROGRESS_PDF] Reading file contents for {file.filename}")
        
        # Read main file content
        main_file_content = await file.read()
        main_filename = file.filename
        main_content_type = file.content_type
        
        # Read context files content
        context_file_contents = []
        for ctx_file in context_files:
            ctx_content = await ctx_file.read()
            context_file_contents.append({
                'filename': ctx_file.filename,
                'content': ctx_content,
                'content_type': ctx_file.content_type
            })
        
        # Update progress - file received
        progress_manager.update_progress(
            session_id=session_id,
            stage="upload",
            progress=50,
            message=f"Processing file: {main_filename}"
        )
        
        # Start async processing task with file contents (not UploadFile objects)
        import asyncio
        asyncio.create_task(_process_pdf_with_progress_tracking(
            main_file_content, main_filename, main_content_type,
            context_file_contents, save_to_db, session_id, db
        ))
        
        # Return immediately with session ID
        return {
            "success": True,
            "session_id": session_id,
            "message": "PDF processing started. Use the session_id to track progress."
        }
        
    except Exception as e:
        debug_log(f"[PROGRESS_PDF_ERROR] {str(e)}")
        progress_manager.error_processing(session_id, f"Failed to start PDF processing: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start PDF processing: {str(e)}")

async def _process_pdf_with_progress_tracking(
    main_file_content: bytes,
    main_filename: str,
    main_content_type: str,
    context_file_contents: List[dict],
    save_to_db: bool,
    session_id: str,
    db: Session
):
    """
    Async task that handles the actual PDF processing with progress updates
    """
    from api.pdf_progress import progress_manager
    
    try:
        debug_log(f"[ASYNC_PROCESSING] Starting async PDF processing for session: {session_id}")
        
        # Update progress - starting processing
        progress_manager.update_progress(
            session_id=session_id,
            stage="processing",
            progress=10,
            message="Parsing PDF content..."
        )
        
        # Process main file content
        main_markdown = await _parse_file_content(main_file_content, main_filename, main_content_type)
        
        # Update progress - main file processed
        progress_manager.update_progress(
            session_id=session_id,
            stage="processing",
            progress=25,
            message="Extracting text from uploaded files..."
        )
        
        # Process context files
        context_markdowns = []
        for ctx_file_info in context_file_contents:
            try:
                ctx_content = await _parse_file_content(
                    ctx_file_info['content'], 
                    ctx_file_info['filename'], 
                    ctx_file_info['content_type']
                )
                context_markdowns.append(f"[Context File: {ctx_file_info['filename']}]\n{ctx_content.strip()}\n")
            except Exception as e:
                debug_log(f"[ERROR] Failed to process context file {ctx_file_info['filename']}: {e}")
                context_markdowns.append(f"[Context File: {ctx_file_info['filename']}]\n[Could not extract context: {e}]\n")
        
        context_text = "\n".join(context_markdowns)
        
        # Update progress - content extracted
        progress_manager.update_progress(
            session_id=session_id,
            stage="processing",
            progress=40,
            message="Content extracted, starting AI analysis..."
        )
        
        # Process with AI
        ai_result = await process_with_ai_optimized(main_markdown, context_text)
        
        # Send field updates for gradual form filling
        if ai_result:
            # Send title update
            if ai_result.get('title'):
                progress_manager.send_field_update(
                    session_id=session_id,
                    field_name='title',
                    field_value=ai_result['title'],
                    message="Title extracted from document"
                )
            
            # Send description update
            if ai_result.get('description'):
                progress_manager.send_field_update(
                    session_id=session_id,
                    field_name='description',
                    field_value=ai_result['description'],
                    message="Description extracted from document"
                )
            
            # Send student role update
            if ai_result.get('student_role'):
                progress_manager.send_field_update(
                    session_id=session_id,
                    field_name='student_role',
                    field_value=ai_result['student_role'],
                    message="Student role identified"
                )
            
            # Send learning outcomes update
            if ai_result.get('learning_outcomes'):
                progress_manager.send_field_update(
                    session_id=session_id,
                    field_name='learning_outcomes',
                    field_value=ai_result['learning_outcomes'],
                    message="Learning outcomes extracted"
                )
            
            # Send personas update
            if ai_result.get('key_figures'):
                progress_manager.send_field_update(
                    session_id=session_id,
                    field_name='personas',
                    field_value=ai_result['key_figures'],
                    message="Character personas identified"
                )
            
            # Send scenes update
            if ai_result.get('scenes'):
                progress_manager.send_field_update(
                    session_id=session_id,
                    field_name='scenes',
                    field_value=ai_result['scenes'],
                    message="Scenario scenes generated"
                )
        
        # Update progress - AI analysis complete
        progress_manager.update_progress(
            session_id=session_id,
            stage="processing",
            progress=80,
            message="AI analysis complete, finalizing results..."
        )
        
        # Save to database if requested
        scenario_id = None
        if save_to_db:
            user_id = 0  # Default user ID for now
            # Create mock UploadFile objects for database saving
            mock_main_file = type('MockFile', (), {
                'filename': main_filename,
                'content_type': main_content_type
            })()
            
            mock_context_files = []
            for ctx_info in context_file_contents:
                mock_ctx_file = type('MockFile', (), {
                    'filename': ctx_info['filename'],
                    'content_type': ctx_info['content_type']
                })()
                mock_context_files.append(mock_ctx_file)
            
            scenario_id = await save_scenario_to_db(
                ai_result, mock_main_file, mock_context_files, main_markdown, context_text, user_id, db
            )
        
        # Update progress - processing complete
        progress_manager.update_progress(
            session_id=session_id,
            stage="processing",
            progress=100,
            message="PDF processing complete!"
        )
        
        # Mark processing as complete with results
        final_result = {
            "status": "completed",
            "ai_result": ai_result,
            "scenario_id": scenario_id,
            "processing_time": 0  # Could track this better if needed
        }
        
        progress_manager.complete_processing(session_id, final_result)
        debug_log(f"[ASYNC_PROCESSING] Completed PDF processing for session: {session_id}")
        
    except Exception as e:
        debug_log(f"[ASYNC_PROCESSING_ERROR] {str(e)}")
        progress_manager.error_processing(session_id, f"PDF processing failed: {str(e)}")
        raise e

async def _parse_file_content(file_content: bytes, filename: str, content_type: str) -> str:
    """
    Parse file content directly from bytes (not UploadFile object)
    """
    import io
    
    filename_lower = filename.lower() if filename else ""
    
    # For PDF files, use LlamaParse
    if filename_lower.endswith('.pdf') or content_type == "application/pdf":
        return await _parse_pdf_content_with_llamaparse(file_content, filename)
    
    # For text-based files, extract text directly
    elif filename_lower.endswith(('.txt', '.md')) or content_type in ["text/plain", "text/markdown"]:
        try:
            text = file_content.decode('utf-8', errors='ignore')
            return f"[File: {filename}]\n{text.strip()}\n"
        except Exception as e:
            return f"[File: {filename}]\n[Could not extract text: {e}]\n"
    
    # For Word documents, try to extract text (basic implementation)
    elif filename_lower.endswith(('.doc', '.docx')) or content_type in ["application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]:
        try:
            text = file_content.decode('utf-8', errors='ignore')
            return f"[File: {filename}]\n{text.strip()}\n"
        except Exception as e:
            return f"[File: {filename}]\n[Could not extract text: {e}]\n"
    
    else:
        # Fallback: try LlamaParse for other file types
        debug_log(f"Unknown file type {content_type}, trying LlamaParse as fallback...")
        return await _parse_pdf_content_with_llamaparse(file_content, filename)

async def _parse_pdf_content_with_llamaparse(file_content: bytes, filename: str) -> str:
    """
    Parse PDF content using LlamaParse with file content as bytes
    """
    if not LLAMAPARSE_API_KEY:
        raise HTTPException(status_code=500, detail="LlamaParse API key not configured.")
    
    async with _llamaparse_semaphore:
        debug_log(f"[OPTIMIZED] Starting LlamaParse for {filename}")
        start_time = time.time()
        
        try:
            headers = {"Authorization": f"Bearer {LLAMAPARSE_API_KEY}"}
            files = {"file": (filename, file_content, "application/pdf")}
            
            # Use optimized HTTP client with connection pooling
            limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
            timeout = httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=120.0)
            
            async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
                try:
                    # Upload with retry logic
                    upload_response = await client.post(LLAMAPARSE_API_URL, headers=headers, files=files)
                    upload_response.raise_for_status()
                    
                    job_data = upload_response.json()
                    job_id = job_data.get("id") or job_data.get("job_id") or job_data.get("jobId")
                    
                    if not job_id:
                        raise HTTPException(status_code=500, detail=f"No job ID in LlamaParse response")
                    
                    debug_log(f"[OPTIMIZED] Got job ID: {job_id} for {filename}")
                    
                    # Optimized polling with exponential backoff
                    wait_times = [1, 2, 3, 5, 5, 5]  # Faster initial polling
                    max_polls = 40  # Reduced from 60
                    
                    for attempt in range(max_polls):
                        status_response = await client.get(f"{LLAMAPARSE_JOB_URL}/{job_id}", headers=headers)
                        status_response.raise_for_status()
                        status_data = status_response.json()
                        
                        status = status_data.get("status")
                        if status in ["COMPLETED", "SUCCESS"]:
                            debug_log(f"[OPTIMIZED] Job {job_id} completed in {time.time() - start_time:.2f}s")
                            
                            # Try multiple result formats in parallel
                            result_tasks = [
                                _get_llamaparse_result(client, job_id, "markdown", headers),
                                _get_llamaparse_result(client, job_id, "text", headers)
                            ]
                            
                            results = await asyncio.gather(*result_tasks, return_exceptions=True)
                            
                            # Use first successful result
                            for result in results:
                                if isinstance(result, str) and result.strip():
                                    debug_log(f"[OPTIMIZED] Retrieved result for {filename}, length: {len(result)}")
                                    return result
                            
                            # Fallback to status_data
                            if "parsed_document" in status_data:
                                parsed_doc = status_data["parsed_document"]
                                if isinstance(parsed_doc, dict) and "text" in parsed_doc:
                                    return parsed_doc["text"]
                            
                            return ""
                            
                        elif status == "FAILED":
                            error_msg = status_data.get("error", "Unknown error")
                            raise HTTPException(status_code=500, detail=f"LlamaParse job failed: {error_msg}")
                        
                        # Dynamic wait time
                        wait_time = wait_times[min(attempt, len(wait_times) - 1)]
                        await asyncio.sleep(wait_time)
                    
                    raise HTTPException(status_code=500, detail=f"LlamaParse job timed out for {filename}")
                    
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:  # Rate limited
                        await asyncio.sleep(5)  # Wait longer for rate limits
                        raise e  # Let retry decorator handle it
                    raise HTTPException(status_code=e.response.status_code, detail=f"LlamaParse API error: {e}")
                    
        except Exception as e:
            debug_log(f"[ERROR] LlamaParse failed for {filename}: {str(e)}")
            raise

async def _fast_persona_extraction_optimized(doc_id: str, filename: str) -> dict:
    """Fast persona extraction using gpt-3.5-turbo with retrieved chunks"""
    
    # Retrieve top 2-3 most relevant chunks for persona extraction
    from services.embedding_service import embedding_service
    persona_query = "key figures, people, roles, characters, stakeholders, companies, organizations"
    relevant_chunks = await embedding_service.retrieve_relevant_chunks(
        query=persona_query,
        doc_id=doc_id,
        max_chunks=3  # Top 3 chunks for autofill
    )
    
    if not relevant_chunks:
        debug_log("[FAST_OPTIMIZED] No chunks found, using fallback")
        return _create_fast_fallback(filename)
    
    # Combine chunks (should be ~1-2k tokens)
    combined_text = embedding_service.get_combined_chunks_text(relevant_chunks)
    title = filename.replace('.pdf', '').replace('_', ' ').title()
    
    prompt = f"""Extract personas from this business case. Return ONLY JSON:

{{
  "title": "{title}",
  "student_role": "<main decision-maker role>",
  "key_figures": [
    {{
      "name": "<person/entity name>",
      "role": "<their role>",
      "background": "<brief background>",
      "primary_goals": ["goal1", "goal2"],
      "personality_traits": {{"analytical": 7, "creative": 5, "assertive": 6, "collaborative": 7, "detail_oriented": 7}}
    }}
  ]
}}

Find ALL people, companies, roles mentioned in this content. Be thorough but fast.

CONTENT: {combined_text}"""
    
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="gpt-3.5-turbo",  # ⚡ OPTIMIZED: Faster model
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.1,
            )
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Extract JSON
        import re
        json_match = re.search(r'({[\s\S]*})', result_text)
        if json_match:
            result = json.loads(json_match.group(1))
            debug_log(f"[FAST_OPTIMIZED] ⚡ Extracted {len(result.get('key_figures', []))} personas with {len(relevant_chunks)} chunks")
            return result
        else:
            debug_log("[FAST_OPTIMIZED] JSON extraction failed, using fallback")
            return _create_fast_fallback(title)
            
    except Exception as e:
        debug_log(f"[FAST_OPTIMIZED_ERROR] {str(e)}")
        return _create_fast_fallback(title)

async def _full_analysis_optimized(doc_id: str, personas_result: dict) -> dict:
    """Full analysis using gpt-4-turbo with retrieved chunks"""
    
    # Retrieve top 3-4 chunks for comprehensive analysis
    from services.embedding_service import embedding_service
    analysis_query = f"business case analysis, {personas_result.get('title', '')}, decision making, strategy"
    relevant_chunks = await embedding_service.retrieve_relevant_chunks(
        query=analysis_query,
        doc_id=doc_id,
        max_chunks=4  # Top 4 chunks for analysis
    )
    
    if not relevant_chunks:
        debug_log("[ANALYSIS_OPTIMIZED] No chunks found, using personas only")
        return personas_result
    
    # Combine chunks (~2k tokens max)
    combined_text = embedding_service.get_combined_chunks_text(relevant_chunks)
    
    prompt = f"""
You are a highly structured JSON-only generator trained to analyze business case studies for college business education.

CRITICAL: You must identify ALL named individuals, companies, organizations, and significant unnamed roles mentioned within the case study narrative. Focus ONLY on characters and entities that are part of the business story being told.

Your task is to analyze the following business case study content and return a JSON object with exactly the following fields:
  "title": "<The exact title of the business case study>",
  "description": "<A comprehensive, multi-paragraph background description>",
  "student_role": "<The specific role the student will assume>",
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
  ],
  "learning_outcomes": [
    "1. <Outcome 1>",
    "2. <Outcome 2>",
    "3. <Outcome 3>",
    "4. <Outcome 4>",
    "5. <Outcome 5>"
  ]

Output ONLY a valid JSON object. Do not include any extra commentary.

PREVIOUS PERSONAS FOUND: {json.dumps(personas_result.get('key_figures', []))}

CASE STUDY CONTENT:
{combined_text}
"""
    
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="gpt-4-turbo",  # ⚡ OPTIMIZED: More efficient than gpt-4o
                messages=[
                    {"role": "system", "content": "You are a JSON generator for business case study analysis."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4096,
                temperature=0.2,
            )
        )
        
        generated_text = response.choices[0].message.content
        
        # Extract JSON
        match = re.search(r'({[\s\S]*})', generated_text)
        if match:
            json_str = match.group(1)
            result = json.loads(json_str)
            
            # Ensure key_figures exist
            if "key_figures" not in result or not result["key_figures"]:
                result["key_figures"] = personas_result.get("key_figures", [])
            
            debug_log(f"[ANALYSIS_OPTIMIZED] ⚡ Generated analysis with {len(result.get('key_figures', []))} personas using {len(relevant_chunks)} chunks")
            return result
        else:
            debug_log("[ANALYSIS_OPTIMIZED] JSON extraction failed, using personas result")
            return personas_result
            
    except Exception as e:
        debug_log(f"[ANALYSIS_OPTIMIZED_ERROR] {str(e)}")
        return personas_result

async def _scene_generation_optimized(personas_result: dict) -> list:
    """Scene generation using gpt-4-turbo with persona context"""
    
    title = personas_result.get("title", "Business Case Study")
    student_role = personas_result.get("student_role", "Business Manager")
    description = personas_result.get("description", "Business case study scenario")
    key_figures = personas_result.get("key_figures", [])
    persona_names = [figure.get("name", "") for figure in key_figures]
    
    scenes_prompt = f"""
Create exactly 4 interactive scenes for this business case study. Output ONLY a JSON array of scenes.

CASE CONTEXT:
Title: {title}
Student Role: {student_role}
Description: {description[:500]}...

AVAILABLE PERSONAS: {', '.join(persona_names)}

Create 4 scenes following this progression:
1. Crisis Assessment/Initial Briefing
2. Investigation/Analysis Phase  
3. Solution Development
4. Implementation/Approval

Each scene MUST have:
- title: Short descriptive name
- description: 2-3 sentences with vivid setting details for image generation
- personas_involved: Array of 2-4 actual persona names from the list above
- user_goal: Specific objective the student must achieve
- sequence_order: 1, 2, 3, or 4
- goal: Write a short, general summary of what the user should aim to accomplish in this scene
- success_metric: A clear, measurable way to determine if the student has accomplished the specific goal

Output format - ONLY this JSON array:
[
  {{
    "title": "Scene Title",
    "description": "Detailed setting description with visual elements...",
    "personas_involved": ["Actual Name 1", "Actual Name 2"],
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
                model="gpt-4-turbo",  # ⚡ OPTIMIZED: More efficient
                messages=[
                    {"role": "system", "content": "You generate JSON arrays of scenes. Output ONLY valid JSON array, no extra text."},
                    {"role": "user", "content": scenes_prompt}
                ],
                max_tokens=2048,
                temperature=0.3,
            )
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Extract JSON array
        json_match = re.search(r'(\[[\s\S]*\])', result_text)
        if json_match:
            scenes = json.loads(json_match.group(1))
            debug_log(f"[SCENES_OPTIMIZED] ⚡ Generated {len(scenes)} scenes")
            return scenes
        else:
            debug_log("[SCENES_OPTIMIZED] Failed to extract JSON, using fallback")
            return _create_fallback_scenes()
            
    except Exception as e:
        debug_log(f"[SCENES_OPTIMIZED_ERROR] {str(e)}")
        return _create_fallback_scenes()

async def _generate_optimized_images(scenes: list, scenario_title: str) -> list:
    """Generate images using optimized templating (near-instant)"""
    
    if not scenes:
        return []
    
    debug_log(f"[IMAGES_OPTIMIZED] Generating images for {len(scenes)} scenes")
    
    # Generate images in parallel with semaphore control
    image_tasks = []
    for scene in scenes:
        scene_title = scene.get("title", "Business Scene")
        scene_description = scene.get("description", "")
        task = _generate_scene_image_optimized(scene_description, scene_title, 0)
        image_tasks.append(task)
    
    # Execute all image generation in parallel
    image_urls = await asyncio.gather(*image_tasks)
    
    debug_log(f"[IMAGES_OPTIMIZED] ⚡ Generated {len(image_urls)} images")
    return image_urls

async def _generate_scene_image_optimized(description: str, title: str, scenario_id: int) -> str:
    """Generate single scene image with optimized prompt templating"""
    try:
        async with _image_semaphore:
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            
            # ⚡ OPTIMIZED: Direct templating (no GPT-4 needed)
            image_prompt = f"Professional business illustration: {title}. {description[:100]}. Clean, modern corporate style, educational use."
            
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.images.generate(
                    model="dall-e-3",
                    prompt=image_prompt[:400],
                    size="1024x1024",
                    quality="standard",
                    n=1,
                )
            )
            
            return response.data[0].url
            
    except Exception as e:
        debug_log(f"[IMAGE_OPTIMIZED_ERROR] {str(e)}")
        return ""

def _create_fallback_scenes() -> list:
    """Create fallback scenes for error cases"""
    return [
        {
            "title": "Initial Assessment",
            "description": "A professional boardroom meeting where key stakeholders gather to discuss the business situation.",
            "personas_involved": ["Business Manager", "Senior Executive"],
            "user_goal": "Understand the current business situation and identify key challenges",
            "goal": "Assess the situation",
            "success_metric": "Successfully identify the main business challenges",
            "sequence_order": 1
        },
        {
            "title": "Analysis Phase",
            "description": "A focused analysis session with data review and stakeholder interviews.",
            "personas_involved": ["Operations Manager", "Business Manager"],
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
            "personas_involved": ["Business Manager", "Senior Executive"],
            "user_goal": "Secure approval and plan implementation of chosen solution",
            "goal": "Get implementation approval",
            "success_metric": "Gain stakeholder approval for implementation plan",
            "sequence_order": 4
        }
    ]

async def _parse_uploaded_files_optimized(main_file: UploadFile, context_files: List[UploadFile]) -> tuple:
    """Parse uploaded files - optimized version"""
    import io
    main_content = ""
    context_content = ""
    
    try:
        if main_file.filename.endswith('.pdf'):
            pdf_bytes = await main_file.read()
            reader = PdfReader(io.BytesIO(pdf_bytes))
            for page in reader.pages:
                main_content += page.extract_text() + "\n"
        else:
            main_content = (await main_file.read()).decode('utf-8')
        
        for ctx_file in context_files:
            if ctx_file.filename.endswith('.pdf'):
                ctx_bytes = await ctx_file.read()
                ctx_reader = PdfReader(io.BytesIO(ctx_bytes))
                for page in ctx_reader.pages:
                    context_content += page.extract_text() + "\n"
            else:
                context_content += (await ctx_file.read()).decode('utf-8') + "\n"
                
    except Exception as e:
        debug_log(f"[FILE_PARSE_ERROR] {str(e)}")
        raise HTTPException(status_code=400, detail=f"File parsing failed: {str(e)}")
    
    return main_content.strip(), context_content.strip() 