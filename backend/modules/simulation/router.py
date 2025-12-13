"""
Simulation Router.

HTTP endpoints for simulation operations.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
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
    SaveMessageRequest
)


router = APIRouter(prefix="/api/simulation", tags=["Simulation"])


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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/linear-chat-stream")
async def linear_chat_stream(
    request: SimulationChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Handle orchestrated chat interactions with streaming responses."""
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
            yield f"data: {json.dumps({'error': 'Streaming requires ChatOrchestrator implementation'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_stream(), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Content-Type": "text/event-stream"
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenes/{scene_id}", response_model=SimulationSceneResponse)
async def get_scene_by_id(
    scene_id: int,
    db: Session = Depends(get_db)
):
    """Get scene data by ID."""
    service = SimulationService(db)
    try:
        return service.get_scene_by_id(scene_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/grade")
async def get_simulation_grading(
    user_progress_id: int = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get simulation grading."""
    service = SimulationService(db)
    try:
        return await service.get_simulation_grading(user_progress_id, current_user.id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        print(f"[GRADING ERROR] Error grading simulation: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
