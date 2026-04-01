"""
Simulation Router.

HTTP endpoints for simulation operations.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session

from common.db.core import get_db
from app.dependencies import get_current_user
from common.db.models import User
from modules.simulation.service import SimulationService
from common.exceptions import NotFoundError, ForbiddenError
from modules.simulation.schemas.dto import (
    SimulationStartRequest, SimulationStartResponse,
    SimulationChatRequest, SimulationChatResponse,
    UserProgressResponse, SimulationSceneResponse,
    SaveMessageRequest, CodeExecutionRequest, CodeExecutionResponse
)
from common.services.simulation_queue_service import (
    enqueue_simulation_request,
    enqueue_grading_request,
    get_job_status,
    get_job_result
)
from common.utils.queue_decision import should_use_queue
import logging


router = APIRouter(prefix="/api/simulation", tags=["Simulation"])
logger = logging.getLogger(__name__)


@router.post("/start", response_model=SimulationStartResponse)
async def start_simulation(
    request: SimulationStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start a new simulation or resume existing one."""
    service = SimulationService(db)
    try:
        result = await service.start_simulation(current_user.id, request.simulation_id)
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        logger.exception("Failed to start simulation", extra={"user_id": current_user.id, "simulation_id": request.simulation_id})
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/linear-chat-stream")
async def linear_chat_stream(
    request: SimulationChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Handle orchestrated chat interactions with streaming responses.
    
    Under heavy load, requests are queued and processed asynchronously.
    Client should poll /job/{job_id}/status for completion.
    """
    # Generate unique session_id for tracking this request
    session_id = str(uuid.uuid4())
    
    # Special case: "begin" commands should always process directly
    # to ensure students can start simulations even under heavy load
    trimmed_message = request.message.strip().lower()
    is_begin_command = trimmed_message == "begin" and len(request.message.strip().split()) == 1
    
    if is_begin_command:
        logger.info(
            f"[SIMULATION_ROUTER] Processing 'begin' command directly (bypassing queue) "
            f"for user_id={current_user.id}, session_id={session_id}"
        )
        use_queue = False
    else:
        # Check if we should use queue
        use_queue = await should_use_queue()
    
    if use_queue:
        # Enqueue the request
        try:
            job_id = await enqueue_simulation_request(
                user_id=current_user.id,
                user_progress_id=request.user_progress_id,
                message=request.message,
                scene_id=request.scene_id,
                session_id=session_id
            )
            
            logger.info(
                f"[SIMULATION_ROUTER] Enqueued simulation request: job_id={job_id}, "
                f"user_id={current_user.id}, user_progress_id={request.user_progress_id}, "
                f"session_id={session_id}"
            )
            
            # Return job ID immediately
            return JSONResponse(
                status_code=202,  # Accepted
                content={
                    "job_id": job_id,
                    "session_id": session_id,
                    "status": "queued",
                    "message": "Request queued for processing. Poll /api/simulation/job/{job_id}/status for updates."
                }
            )
        except Exception as e:
            logger.error(
                f"[SIMULATION_ROUTER] Failed to enqueue simulation request: {e}, "
                f"session_id={session_id}, user_id={current_user.id}, "
                f"user_progress_id={request.user_progress_id}",
                exc_info=True
            )
            # Fallback to direct processing on queue error
            use_queue = False
    
    # Direct processing (existing behavior)
    if not use_queue:
        logger.info(
            f"[SIMULATION_ROUTER] Processing simulation request directly: "
            f"user_id={current_user.id}, user_progress_id={request.user_progress_id}, "
            f"session_id={session_id}"
        )
        service = SimulationService(db)
        
        async def generate_stream():
            import json
            try:
                async for chunk in service.stream_chat_message(
                    current_user.id,
                    request.user_progress_id,
                    request.message,
                    request.scene_id
                ):
                    yield chunk
            except NotImplementedError:
                logger.error(
                    f"[SIMULATION_ROUTER] Streaming not implemented: session_id={session_id}, "
                    f"user_id={current_user.id}, user_progress_id={request.user_progress_id}"
                )
                yield f"data: {json.dumps({'error': 'Streaming requires ChatOrchestrator implementation'})}\n\n"
            except Exception as e:
                logger.exception(
                    f"[SIMULATION_ROUTER] Streaming chat message failed: session_id={session_id}, "
                    f"user_id={current_user.id}, user_progress_id={request.user_progress_id}, "
                    f"scene_id={request.scene_id}",
                    exc_info=True
                )
                yield f"data: {json.dumps({'error': 'Internal server error'})}\n\n"
        
        return StreamingResponse(
            generate_stream(), 
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
                "Content-Type": "text/event-stream",
                "X-Session-Id": session_id  # Include session_id in response headers for tracking
            }
        )


@router.post("/linear-chat", response_model=SimulationChatResponse)
async def linear_chat(
    request: SimulationChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Handle orchestrated chat interactions (non-streaming, for SUBMIT_FOR_GRADING)."""
    service = SimulationService(db)
    try:
        return await service.process_chat_message(
            current_user.id,
            request.user_progress_id,
            request.message,
            request.scene_id
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception:
        logger.exception("Failed to process chat message", extra={"user_id": current_user.id, "user_progress_id": request.user_progress_id, "scene_id": request.scene_id})
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/scenes/{scene_id}", response_model=SimulationSceneResponse)
async def get_scene_by_id(
    scene_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get scene data by ID."""
    service = SimulationService(db)
    try:
        return service.get_scene_by_id(scene_id, current_user.id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception:
        logger.exception("Failed to get scene by id", extra={"scene_id": scene_id, "user_id": current_user.id})
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/save-message")
async def save_message(
    request: SaveMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Save a system message to conversation history."""
    service = SimulationService(db)
    try:
        return service.save_message(
            current_user.id,
            request.user_progress_id,
            request.scene_id,
            request.sender_name,
            request.message_content,
            request.message_type
        )
    except ValueError as e:
        # session_id is required - fail loudly with clear error message
        logger.error(f"save_message failed: {e}", extra={"user_id": current_user.id, "user_progress_id": request.user_progress_id, "scene_id": request.scene_id})
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Failed to save message", extra={"user_id": current_user.id, "user_progress_id": request.user_progress_id, "scene_id": request.scene_id})
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/execute-code", response_model=CodeExecutionResponse)
async def execute_code(
    request: CodeExecutionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Execute student code in their Daytona sandbox."""
    from common.db.models.simulation.user_progress import UserProgress
    from common.db.models.simulation.conversation import ConversationLog
    from common.db.models.simulation.scene import SimulationScene
    from common.services.sandbox_service import sandbox_service

    user_progress = db.query(UserProgress).filter_by(
        id=request.user_progress_id,
        user_id=current_user.id,
    ).first()

    if not user_progress:
        raise HTTPException(404, "User progress not found")
    if not user_progress.sandbox_id:
        raise HTTPException(404, "No active sandbox for this simulation")

    # Validate that scene belongs to this simulation
    scene = db.query(SimulationScene).filter_by(id=request.scene_id).first()
    if not scene:
        raise HTTPException(404, "Scene not found")
    if scene.simulation_id != user_progress.simulation_id:
        raise HTTPException(400, "Scene does not belong to this simulation")

    result = await sandbox_service.execute_code(
        user_progress.sandbox_id,
        request.code,
    )

    # Log the code execution as a conversation entry
    import secrets
    max_order = db.query(ConversationLog.message_order).filter_by(
        user_progress_id=request.user_progress_id,
        scene_id=request.scene_id,
    ).order_by(ConversationLog.message_order.desc()).first()
    next_order = (max_order[0] + 1) if max_order else 1

    # Find the latest session_id for this scene
    latest_log = db.query(ConversationLog.session_id).filter_by(
        user_progress_id=request.user_progress_id,
        scene_id=request.scene_id,
    ).order_by(ConversationLog.id.desc()).first()
    session_id = latest_log[0] if latest_log else f"code_{request.user_progress_id}_{secrets.token_urlsafe(8)}"

    log = ConversationLog(
        user_progress_id=request.user_progress_id,
        scene_id=request.scene_id,
        session_id=session_id,
        sender_name="student",
        message_type="code_submission",
        message_content=request.code,
        message_order=next_order,
    )
    db.add(log)
    db.commit()

    return CodeExecutionResponse(
        success=result["success"],
        output=result.get("output", ""),
        error=result.get("error"),
    )


@router.get("/grade")
async def get_simulation_grading(
    user_progress_id: int = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get simulation grading.
    
    Under heavy load, grading requests are queued and processed asynchronously.
    Client should poll /job/{job_id}/status for completion.
    """
    # Generate unique session_id for tracking this request
    session_id = str(uuid.uuid4())
    
    # Check if we should use queue
    use_queue = await should_use_queue()
    
    if use_queue:
        # Enqueue the grading request
        try:
            job_id = await enqueue_grading_request(
                user_id=current_user.id,
                user_progress_id=user_progress_id,
                session_id=session_id
            )
            
            logger.info(
                f"[SIMULATION_ROUTER] Enqueued grading request: job_id={job_id}, "
                f"user_id={current_user.id}, user_progress_id={user_progress_id}, "
                f"session_id={session_id}"
            )
            
            # Return job ID immediately
            return JSONResponse(
                status_code=202,  # Accepted
                content={
                    "job_id": job_id,
                    "session_id": session_id,
                    "status": "queued",
                    "message": "Grading request queued for processing. Poll /api/simulation/job/{job_id}/status for updates."
                }
            )
        except Exception as e:
            logger.error(f"Failed to enqueue grading request: {e}", exc_info=True)
            # Fallback to direct processing on queue error
            use_queue = False
    
    # Direct processing (existing behavior)
    if not use_queue:
        service = SimulationService(db)
        try:
            return await service.get_simulation_grading(user_progress_id, current_user.id)
        except NotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ForbiddenError as e:
            raise HTTPException(status_code=403, detail=str(e))
        except Exception:
            logger.exception("Error grading simulation", extra={"user_id": current_user.id, "user_progress_id": user_progress_id})
            raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/progress/{user_progress_id}", response_model=UserProgressResponse)
async def get_user_progress(
    user_progress_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed user progress for a simulation."""
    service = SimulationService(db)
    try:
        return service.get_user_progress(user_progress_id, current_user.id)
    except Exception:
        logger.exception("Failed to get user progress", extra={"user_id": current_user.id, "user_progress_id": user_progress_id})
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/job/{job_id}/status")
async def get_job_status_endpoint(
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get the status of a queued simulation job."""
    try:
        status = await get_job_status(job_id)
        
        # Verify job ownership (security check)
        if status.get("status") != "not_found":
            job_user_id = status.get("user_id")
            if job_user_id is None or job_user_id != current_user.id:
                raise HTTPException(status_code=403, detail="Forbidden")
            
            # Remove user_id from response to avoid leaking internal identifiers
            # Create a copy without user_id
            sanitized_status = {k: v for k, v in status.items() if k != "user_id"}
            return sanitized_status
        
        return status
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get job status: {e}", extra={"job_id": job_id, "user_id": current_user.id})
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/job/{job_id}/result")
async def get_job_result_endpoint(
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get the result of a completed simulation job."""
    try:
        result = await get_job_result(job_id)
        
        if result is None:
            raise HTTPException(status_code=404, detail="Job not found or not completed")
        
        # Verify job ownership (security check)
        job_user_id = result.get("user_id")
        if job_user_id is None or job_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Forbidden")
        
        # Remove user_id from response to avoid leaking internal identifiers
        sanitized_result = {k: v for k, v in result.items() if k != "user_id"}
        return sanitized_result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get job result: {e}", extra={"job_id": job_id, "user_id": current_user.id})
        raise HTTPException(status_code=500, detail="Internal server error")