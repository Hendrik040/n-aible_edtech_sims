"""
Publishing router for HTTP endpoints.

Handles all HTTP endpoints for the publishing module.
"""

import json
import logging
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from common.db.core import get_db
from common.db.models import Simulation, SimulationPersona, SimulationScene, User, scene_personas
from app.dependencies import get_current_user, get_current_user_optional
from .service import PublishingService
from .schemas.dto import (
    SimulationPublishRequest,
    SimulationPublishingResponse,
    PublishResponse,
    SaveResponse,
    StatusUpdateRequest,
    CloneResponse,
    CleanupStatsResponse,
    ImageUploadStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/publishing/simulations", tags=["Publishing"])

# In-memory WebSocket connections (per server instance)
# Maps user_id -> WebSocket connection
user_websocket_connections: Dict[int, WebSocket] = {}


async def _build_simulation_response(simulation: Simulation, db: Session) -> dict:
    """Build simulation response with personas and scenes.
    
    For draft simulations, checks S3 if image_url is None to see if image was uploaded
    but database wasn't updated yet.
    """
    from common.services.s3_service import s3_service
    
    personas = db.query(SimulationPersona).filter(
        SimulationPersona.simulation_id == simulation.id,
        SimulationPersona.deleted_at.is_(None)
    ).all()
    
    scenes = db.query(SimulationScene).filter(
        SimulationScene.simulation_id == simulation.id
    ).order_by(SimulationScene.scene_order).all()
    
    # For draft simulations, check S3 if image_url is None (worker might have uploaded but DB not updated)
    is_draft = simulation.is_draft if simulation.is_draft is not None else False
    if is_draft:
        for persona in personas:
            if not persona.image_url:
                # Check S3 for existing image
                for ext in ['jpg', 'png', 'webp']:
                    s3_key = s3_service.get_persona_avatar_key(simulation.id, persona.id, ext)
                    try:
                        file_exists = await s3_service.file_exists(s3_key)
                        if file_exists:
                            persona.image_url = s3_service._build_public_url(s3_key)
                            # Update database for future requests
                            db.add(persona)
                            db.commit()
                            logger.info(f"[DRAFT_LOAD] Found persona image in S3 for {persona.id}, updated database")
                            break
                    except Exception as e:
                        logger.warning(f"[DRAFT_LOAD] Error checking S3 for persona {persona.id}: {e}")
                        break
        
        for scene in scenes:
            if not scene.image_url:
                # Check S3 for existing image
                for ext in ['jpg', 'png', 'webp']:
                    s3_key = s3_service.get_scene_image_key(simulation.id, scene.id, ext)
                    try:
                        file_exists = await s3_service.file_exists(s3_key)
                        if file_exists:
                            scene.image_url = s3_service._build_public_url(s3_key)
                            # Update database for future requests
                            db.add(scene)
                            db.commit()
                            logger.info(f"[DRAFT_LOAD] Found scene image in S3 for {scene.id}, updated database")
                            break
                    except Exception as e:
                        logger.warning(f"[DRAFT_LOAD] Error checking S3 for scene {scene.id}: {e}")
                        break
    
    # Get scene-persona associations (involved personas)
    # Build a map of persona IDs to names for quick lookup
    persona_id_to_name = {persona.id: persona.name for persona in personas}
    
    # Get involved persona names for each scene
    scene_persona_names = {}
    for scene in scenes:
        associations = db.execute(
            scene_personas.select().where(scene_personas.c.scene_id == scene.id)
        ).fetchall()
        scene_persona_names[scene.id] = [
            persona_id_to_name.get(assoc.persona_id)
            for assoc in associations
            if persona_id_to_name.get(assoc.persona_id)
        ]
    
    learning_objectives = simulation.learning_objectives or []
    if isinstance(learning_objectives, str):
        learning_objectives = [item.strip() for item in learning_objectives.split('\n') if item.strip()]
    
    return {
        "id": simulation.id,
        "title": simulation.title or "",
        "description": simulation.description or "",
        "challenge": simulation.challenge or "",
        "industry": simulation.industry or "Business",
        "learning_objectives": learning_objectives,
        "student_role": simulation.student_role or "",
        "pdf_title": simulation.pdf_title,
        "pdf_source": simulation.pdf_source,
        "processing_version": simulation.processing_version,
        "source_type": simulation.source_type,
        "is_public": simulation.is_public,
        "is_template": simulation.is_template,
        "allow_remixes": simulation.allow_remixes,
        "usage_count": simulation.usage_count,
        "clone_count": simulation.clone_count,
        "created_by": simulation.created_by,
        "created_at": simulation.created_at,
        "updated_at": simulation.updated_at,
        "status": simulation.status or "draft",
        "is_draft": simulation.is_draft if simulation.is_draft is not None else False,
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
                "image_url": scene.image_url,
                "timeout_turns": scene.timeout_turns,
                "success_metric": scene.success_metric,
                "personas_involved": scene_persona_names.get(scene.id, [])
            }
            for scene in scenes
        ],
        "completion_status": {
            "name_completed": simulation.name_completed,
            "description_completed": simulation.description_completed,
            "student_role_completed": simulation.student_role_completed,
            "personas_completed": simulation.personas_completed,
            "scenes_completed": simulation.scenes_completed,
            "images_completed": simulation.images_completed,
            "learning_outcomes_completed": simulation.learning_outcomes_completed,
            "ai_enhancement_completed": simulation.ai_enhancement_completed,
        },
        "name_completed": simulation.name_completed,
        "description_completed": simulation.description_completed,
        "student_role_completed": simulation.student_role_completed,
        "personas_completed": simulation.personas_completed,
        "scenes_completed": simulation.scenes_completed,
        "images_completed": simulation.images_completed,
        "learning_outcomes_completed": simulation.learning_outcomes_completed,
        "ai_enhancement_completed": simulation.ai_enhancement_completed
    }


@router.get("/", response_model=List[SimulationPublishingResponse])
async def get_simulations(
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None, description="Filter by status: draft, active, archived"),
    include_drafts: Optional[bool] = Query(False, description="Include draft simulations"),
    current_user: User = Depends(get_current_user)
):
    """Get simulations with optional filtering by status."""
    try:
        service = PublishingService(db)
        simulations = service.repository.get_simulations_by_user(
            current_user.id, status, include_drafts
        )
        
        simulation_responses = []
        for simulation in simulations:
            try:
                simulation_responses.append(await _build_simulation_response(simulation, db))
            except Exception as e:
                logger.error(f"Error building response for simulation {simulation.id}: {e}")
                continue
        
        return simulation_responses
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching simulations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch simulations: {str(e)}")


@router.get("/drafts/", response_model=List[SimulationPublishingResponse])
async def get_draft_simulations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get draft simulations only."""
    try:
        service = PublishingService(db)
        simulations = service.repository.get_draft_simulations(current_user.id)
        
        simulation_responses = []
        for simulation in simulations:
            learning_objectives = simulation.learning_objectives or []
            if isinstance(learning_objectives, str):
                learning_objectives = [item.strip() for item in learning_objectives.split('\n') if item.strip()]
            
            simulation_responses.append(await _build_simulation_response(simulation, db))
        
        return simulation_responses
    except Exception as e:
        logger.error(f"Error fetching draft simulations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch draft simulations: {str(e)}")


@router.get("/drafts/{simulation_id}", response_model=SimulationPublishingResponse)
async def get_draft_simulation(
    simulation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a single draft simulation by ID for editing."""
    try:
        service = PublishingService(db)
        simulation = service.repository.get_simulation_by_id(simulation_id)
        
        if not simulation:
            raise HTTPException(status_code=404, detail="Simulation not found")
        
        # Check permissions - user can only access their own simulations
        if simulation.created_by != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You can only access simulations you created"
            )
        
        return await _build_simulation_response(simulation, db)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching draft simulation {simulation_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch draft simulation: {str(e)}"
        )


@router.post("/publish/{simulation_id}", response_model=PublishResponse)
async def publish_simulation(
    simulation_id: int,
    publish_request: SimulationPublishRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Publish a simulation (makes it available for assignment)."""
    logger.info(f"[PUBLISH] Starting publish for simulation {simulation_id}")
    
    service = PublishingService(db)
    simulation = await service.publish_simulation(simulation_id)
    
    return PublishResponse(
        status="published",
        simulation_id=simulation.id,
        message=f"Simulation '{simulation.title}' has been published"
    )


@router.get("/{simulation_id}/upload-status", response_model=ImageUploadStatusResponse)
async def get_upload_status(
    simulation_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Get image upload status for a simulation."""
    service = PublishingService(db)
    simulation = service.repository.get_simulation_by_id(simulation_id)
    
    if not simulation:
        raise HTTPException(status_code=404, detail="Simulation not found")
    
    # Check permissions - user can only check their own simulations
    if current_user and simulation.created_by != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only check upload status for simulations you created"
        )
    
    from modules.publishing.tasks import get_upload_status
    status = get_upload_status(simulation_id)
    return ImageUploadStatusResponse(**status)


@router.get("/{simulation_id}/full", response_model=SimulationPublishingResponse)
async def get_simulation_full(
    simulation_id: int,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Get full simulation details with personas and scenes."""
    service = PublishingService(db)
    simulation = service.repository.get_simulation_by_id(simulation_id)
    
    if not simulation:
        raise HTTPException(status_code=404, detail="Simulation not found")
    
    # Check access permissions
    if not simulation.is_public:
        if not current_user:
            raise HTTPException(
                status_code=401,
                detail="Authentication required to access private simulations"
            )
        if simulation.created_by != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You can only access simulations you created"
            )
    
    if simulation.is_public:
        simulation.usage_count += 1
        db.commit()
    
    return await _build_simulation_response(simulation, db)


@router.post("/save", response_model=SaveResponse)
async def save_simulation_draft(
    request: Request,
    simulation_id: Optional[int] = Query(None, description="Simulation ID for updates"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Save AI processing results as a draft simulation.
    
    Creates or updates a simulation with personas, scenes, and completion status.
    """
    logger.info(f"[SAVE] Starting save_simulation_draft - simulation_id: {simulation_id}")
    
    try:
        data = await request.json()
        logger.info(f"[SAVE] Received data with keys: {list(data.keys())}")
        
        service = PublishingService(db)
        user_id = current_user.id if current_user else None
        
        simulation = await service.save_simulation_draft(simulation_id, user_id, data)
        
        return SaveResponse(
            status="saved",
            simulation_id=simulation.id,
            message=f"Simulation '{simulation.title}' has been saved"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in save_simulation_draft: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save simulation: {str(e)}")


@router.put("/{simulation_id}/status", response_model=SimulationPublishingResponse)
async def update_simulation_status(
    simulation_id: int,
    status_request: StatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update simulation status (draft, active, archived, creating).
    
    - "active": Publishes the simulation (makes it available for assignment)
    - "draft": Unpublishes the simulation (makes it unavailable)
    - "archived": Archives the simulation
    - "creating": Marks simulation as being created
    """
    logger.info(f"[STATUS_UPDATE] Updating simulation {simulation_id} to {status_request.status}")
    
    try:
        service = PublishingService(db)
        simulation = service.update_simulation_status(
            simulation_id,
            status_request.status,
            current_user.id
        )
        
        return await _build_simulation_response(simulation, db)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in update_simulation_status: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update simulation status: {str(e)}"
        )


@router.delete("/{simulation_id}", status_code=204)
async def delete_simulation(
    simulation_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Delete a simulation (soft delete).
    
    Only the creator of the simulation can delete it.
    """
    logger.info(f"[DELETE] Starting delete for simulation {simulation_id}")
    
    try:
        service = PublishingService(db)
        user_id = current_user.id if current_user else None
        
        service.delete_simulation(simulation_id, user_id)
        
        return None  # 204 No Content
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in delete_simulation: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete simulation: {str(e)}")


@router.websocket("/ws/{user_id}")
async def websocket_simulation_updates(websocket: WebSocket, user_id: int):
    """
    WebSocket endpoint for real-time simulation status updates.
    
    Connects user to receive notifications when their simulations are ready.
    Note: Uses in-memory connections on a single server instance (no cross-instance pub/sub).
    """
    # Accept connection first (required to read cookies and query params)
    await websocket.accept()
    
    # Authenticate user - try query params first, then cookies
    token = websocket.query_params.get("token")
    
    # If no token in query, try to get from cookies (WebSocket can access cookies after accept)
    if not token:
        token = websocket.cookies.get("access_token")
    
    if not token:
        await websocket.close(code=1008, reason="Missing authentication token")
        return
    
    # Verify token and get user
    try:
        from modules.auth.service import auth_service
        payload = auth_service.verify_token(token)
        if not payload:
            await websocket.close(code=1008, reason="Invalid authentication token")
            return
        
        sub_value = payload.get("sub")
        if sub_value is None:
            await websocket.close(code=1008, reason="Missing user in token")
            return
        try:
            token_user_id = int(sub_value)
        except (TypeError, ValueError):
            await websocket.close(code=1008, reason="Invalid user in token")
            return
        if token_user_id != user_id:
            await websocket.close(code=1008, reason="User ID mismatch")
            return
    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"WebSocket authentication error: {e}")
        await websocket.close(code=1008, reason="Authentication failed")
        return
    
    # Store connection after successful authentication
    user_websocket_connections[user_id] = websocket
    logger.info(f"WebSocket connected for user {user_id}")
    
    try:
        # Keep connection alive and listen for messages
        while True:
            # Wait for ping or close
            try:
                data = await websocket.receive_text()
                # Handle ping/pong if needed
                if data == "ping":
                    await websocket.send_text("pong")
            except WebSocketDisconnect:
                break
    except (RuntimeError, ValueError, TypeError) as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
    finally:
        # Cleanup on disconnect
        user_websocket_connections.pop(user_id, None)
        logger.info(f"WebSocket disconnected for user {user_id}")


async def send_simulation_notification(user_id: int, simulation_id: int, status: str, title: str):
    """
    Send simulation status update notification to user via WebSocket.
    
    This function is called when simulation status changes (e.g., from 'creating' to 'draft').
    It sends the notification to the user's WebSocket connection if connected.
    """
    if user_id not in user_websocket_connections:
        logger.debug(f"User {user_id} not connected to WebSocket, skipping notification for simulation {simulation_id}")
        return  # User not connected, no notification needed
    
    try:
        websocket = user_websocket_connections[user_id]
        message = {
            "type": "simulation_ready",
            "simulation_id": simulation_id,
            "status": status,
            "title": title
        }
        await websocket.send_text(json.dumps(message))
        logger.info(f"✅ Sent simulation notification to user {user_id} for simulation {simulation_id} (status: {status})")
    except (RuntimeError, ValueError, TypeError) as e:
        logger.error(f"❌ Failed to send notification to user {user_id}: {e}", exc_info=True)
        # Remove broken connection
        user_websocket_connections.pop(user_id, None)
