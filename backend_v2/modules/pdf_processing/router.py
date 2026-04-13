"""
FastAPI router for PDF processing endpoints.
Extracted from api/parse_pdf.py and api/pdf_progress.py
"""
import asyncio
import uuid
import httpx
import logging
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form
from sqlalchemy.orm import Session

from common.config import get_settings
from common.db.core import get_db, SessionLocal
from common.db.models import User
from app.dependencies import get_current_user_optional
from .pipeline import get_pipeline
from .progress_service import progress_manager

settings = get_settings()

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/parse-pdf-fast-autofill")
async def parse_pdf_fast_autofill(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    FAST endpoint specifically for autofill - returns only personas, no images or scenes.
    Creates simulation immediately and saves data when processing completes.
    """
    logger.info("[ENDPOINT] Starting fast autofill processing...")
    
    if not settings.llamaparse_api_key:
        raise HTTPException(status_code=500, detail="LlamaParse API key not configured.")
    
    try:
        # Create pipeline and process
        pipeline = get_pipeline(db, current_user)
        result = await pipeline.process_fast_autofill(file)
        
        return result
        
    except Exception as e:
        logger.error(f"[ENDPOINT] Fast autofill failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Autofill processing failed: {str(e)}")


@router.get("/llamaparse-health/")
async def llamaparse_health_check():
    """Health check endpoint for LlamaParse configuration"""
    try:
        # Check API key configuration
        if not settings.llamaparse_api_key:
            return {
                "status": "error",
                "message": "LLAMAPARSE_API_KEY is not configured",
                "details": "Please set the LLAMAPARSE_API_KEY environment variable in Railway"
            }
        
        if len(settings.llamaparse_api_key) < 20:
            return {
                "status": "error", 
                "message": "LLAMAPARSE_API_KEY appears to be invalid",
                "details": f"API key length: {len(settings.llamaparse_api_key)} characters (expected: 20+)"
            }
        
        # Test API connection
        headers = {"Authorization": f"Bearer {settings.llamaparse_api_key}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # Try to reach the API endpoint
                response = await client.get("https://api.cloud.llamaindex.ai/health", headers=headers)
                
                # Check status code manually (HTTPStatusError requires raise_for_status())
                if response.status_code == 401:
                    return {
                        "status": "error",
                        "message": "Invalid API key - authentication failed",
                        "details": "Please check your LLAMAPARSE_API_KEY"
                    }
                
                if response.status_code >= 400:
                    return {
                        "status": "error",
                        "message": f"API request failed (status: {response.status_code})",
                        "details": response.text
                    }
                
                # Success
                return {
                    "status": "healthy",
                    "message": "LlamaParse API is reachable",
                    "api_key_length": len(settings.llamaparse_api_key),
                    "api_response_status": response.status_code
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


@router.get("/get-default-personas/")
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


@router.post("/parse-pdf-with-progress")
async def parse_pdf_with_progress_route(
    file: UploadFile = File(...),
    context_files: Optional[List[UploadFile]] = File(None),
    save_to_db: bool = Form(False),
    session_id: str = Form(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Parse PDF with real-time progress tracking via WebSocket"""
    
    # Generate session ID if not provided
    if not session_id:
        session_id = str(uuid.uuid4())
        logger.info(f"[ENDPOINT] Generated new session_id: {session_id}")
    
    # Initialize progress tracking immediately
    logger.info(f"[ENDPOINT] Initializing progress tracking for session: {session_id}")
    progress_manager.update_progress(session_id, "upload", 0, "Starting file processing...")
    
    # Start processing in the background with its own DB session
    async def run_parsing():
        """Background task for PDF processing - creates its own DB session"""
        task_db = SessionLocal()
        try:
            # Load user if needed (use current_user.id to avoid detached instance)
            task_user = None
            if current_user:
                task_user = task_db.query(User).filter(User.id == current_user.id).first()
            
            # Create pipeline with task's own DB session
            pipeline = get_pipeline(task_db, task_user)
            await pipeline.process_full_with_progress(file, session_id, context_files)
        except HTTPException as e:
            logger.error(f"[ENDPOINT] HTTPException in background task: {e.status_code} - {e.detail}")
            if session_id:
                progress_manager.error_processing(session_id, f"{e.detail}")
        except Exception as e:
            logger.error(f"[ENDPOINT] Exception in background task: {e}")
            if session_id:
                progress_manager.error_processing(session_id, f"PDF parsing failed: {str(e)}")
        finally:
            task_db.close()
    
    # Store task reference to prevent garbage collection
    background_task = asyncio.create_task(run_parsing())
    
    # Return immediately with session ID
    return {
        "session_id": session_id,
        "status": "started",
        "message": "PDF parsing started, use session_id to track progress"
    }


@router.post("/parse-pdf")
async def parse_pdf(
    file: UploadFile = File(...),
    context_files: Optional[List[UploadFile]] = File(None),
    save_to_db: bool = False,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Main endpoint: Parse PDF and context files, then process with AI"""
    logger.info("[ENDPOINT] /api/parse-pdf/ endpoint hit")
    
    if not settings.llamaparse_api_key:
        raise HTTPException(status_code=500, detail="LlamaParse API key not configured.")
    
    # Support PDF, TXT, and other text-based files
    supported_types = ["application/pdf", "text/plain", "text/markdown", "application/msword", 
                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]
    if file.content_type not in supported_types and not (file.filename and file.filename.lower().endswith(('.pdf', '.txt', '.md', '.doc', '.docx'))):
        raise HTTPException(status_code=400, detail="Only PDF, TXT, MD, DOC, and DOCX files are supported.")
    
    try:
        pipeline = get_pipeline(db, current_user)
        result = await pipeline.process_full(file, context_files)
        
        return result
            
    except Exception as e:
        logger.error(f"[ENDPOINT] PDF parsing failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to parse PDF: {str(e)}")


# Progress tracking endpoints (extracted from original pdf_progress.py)
@router.get("/pdf-progress/{session_id}")
async def get_progress_status(session_id: str):
    """Get current progress status for a session"""
    logger.info(f"[ENDPOINT] Getting progress for session: {session_id}")
    
    # Use the progress manager to get status
    progress_data = progress_manager.get_progress_status(session_id)
    
    if progress_data is None:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return progress_data


@router.post("/pdf-progress/{session_id}/reset")
async def reset_progress(session_id: str):
    """Reset progress for a session"""
    progress_manager.reset_progress(session_id)
    return {"message": "Progress reset successfully"}
