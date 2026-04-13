"""
Publishing router for HTTP endpoints.

Handles all HTTP endpoints for the publishing module.
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Tuple

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_current_user_optional
from common.db.core import get_db
from common.db.models import (
    Simulation,
    SimulationPersona,
    SimulationScene,
    User,
    scene_personas,
)
from common.services.s3_service import s3_service
from common.services.cache_service import redis_manager as cache_service
from modules.publishing.tasks import is_temporary_image_url
from .service import PublishingService
from .schemas.dto import (
    ImageUploadStatusResponse,
    PublishResponse,
    SimulationPublishRequest,
    SimulationPublishingResponse,
    StatusUpdateRequest,
    SaveResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/publishing/simulations", tags=["Publishing"])

# In-memory WebSocket connections (per server instance)
# Maps user_id -> WebSocket connection
user_websocket_connections: Dict[int, WebSocket] = {}


def invalidate_user_simulations_cache(user_id: int) -> None:
    """Invalidate all simulation caches for a user.
    
    Called when user creates, publishes, archives, or deletes a simulation
    to ensure the dashboard shows fresh data.
    """
    patterns = [
        f"user:{user_id}:simulations:drafts=True",
        f"user:{user_id}:simulations:drafts=False",
        f"user:{user_id}:simulations:drafts=True:status=active",
        f"user:{user_id}:simulations:drafts=True:status=draft",
        f"user:{user_id}:simulations:drafts=True:status=creating",
        f"user:{user_id}:simulations:drafts=False:status=active",
        f"user:{user_id}:simulations:drafts=False:status=draft",
        f"user:{user_id}:simulations:drafts=False:status=creating",
    ]
    for key in patterns:
        cache_service.delete(key)
    logger.info(f"[CACHE_INVALIDATE] Cleared simulation caches for user {user_id}")


async def build_simulation_responses_batched(
    simulations: List[Simulation],
    db: Session
) -> List[Dict]:
    """Build responses for multiple simulations with batched queries.
    
    OPTIMIZED: Instead of N+1 queries, this uses 4 batched queries:
    1. All simulations (already loaded)
    2. All personas for all simulations
    3. All scenes for all simulations
    4. All scene_personas associations
    """
    if not simulations:
        return []
    
    # Step 1: Collect all simulation IDs
    simulation_ids = [sim.id for sim in simulations]
    logger.info(f"[BATCH_QUERY] Building responses for {len(simulation_ids)} simulations")
    
    # Step 2: Batch query ALL personas for all simulations (1 query instead of N)
    all_personas = (
        db.query(SimulationPersona)
        .filter(
            SimulationPersona.simulation_id.in_(simulation_ids),
            SimulationPersona.deleted_at.is_(None)
        )
        .all()
    )
    logger.info(f"[BATCH_QUERY] Loaded {len(all_personas)} personas in 1 query")
    
    # Step 3: Batch query ALL scenes for all simulations (1 query instead of N)
    all_scenes = (
        db.query(SimulationScene)
        .filter(
            SimulationScene.simulation_id.in_(simulation_ids),
            SimulationScene.deleted_at.is_(None)
        )
        .order_by(SimulationScene.scene_order)
        .all()
    )
    logger.info(f"[BATCH_QUERY] Loaded {len(all_scenes)} scenes in 1 query")
    
    # Step 4: Batch query ALL scene_personas associations (1 query instead of N*M)
    scene_ids = [scene.id for scene in all_scenes]
    all_scene_persona_assocs = []
    if scene_ids:
        all_scene_persona_assocs = db.execute(
            scene_personas.select().where(scene_personas.c.scene_id.in_(scene_ids))
        ).fetchall()
    logger.info(f"[BATCH_QUERY] Loaded {len(all_scene_persona_assocs)} scene-persona associations in 1 query")
    
    # Step 5: Group data by simulation_id for O(1) lookup
    personas_by_sim: Dict[int, List[SimulationPersona]] = {}
    for persona in all_personas:
        personas_by_sim.setdefault(persona.simulation_id, []).append(persona)
    
    scenes_by_sim: Dict[int, List[SimulationScene]] = {}
    for scene in all_scenes:
        scenes_by_sim.setdefault(scene.simulation_id, []).append(scene)
    
    # Group scene_personas by scene_id
    scene_persona_map: Dict[int, List[int]] = {}
    for assoc in all_scene_persona_assocs:
        scene_persona_map.setdefault(assoc.scene_id, []).append(assoc.persona_id)
    
    # Step 6: Build responses in memory (no more DB queries!)
    responses: List[Dict] = []
    for simulation in simulations:
        sim_personas = personas_by_sim.get(simulation.id, [])
        sim_scenes = scenes_by_sim.get(simulation.id, [])
        
        # Build persona_id -> name mapping for this simulation
        persona_id_to_name = {p.id: p.name for p in sim_personas}
        
        # Parse learning objectives
        learning_objectives = simulation.learning_objectives or []
        if isinstance(learning_objectives, str):
            learning_objectives = [
                item.strip()
                for item in learning_objectives.split("\n")
                if item.strip()
            ]
        
        response = {
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
                    "current_context": persona.current_context,
                    "correlation": persona.correlation,
                    "primary_goals": persona.primary_goals or [],
                    "personality_traits": persona.personality_traits or {},
                    "knowledge_areas": persona.knowledge_areas or [],
                    "communication_style": persona.communication_style,
                    "system_prompt": persona.system_prompt,
                    "image_url": persona.image_url,
                }
                for persona in sim_personas
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
                    "scene_type": getattr(scene, "scene_type", None) or "conversation",
                    "code_language": getattr(scene, "code_language", None) or "python",
                    "starter_code": getattr(scene, "starter_code", None),
                    "code_grading_criteria": getattr(scene, "code_grading_criteria", None),
                    "data_files": getattr(scene, "data_files", None),
                    "reference_files": getattr(scene, "reference_files", None),
                    "personas_involved": [
                        persona_id_to_name.get(pid)
                        for pid in scene_persona_map.get(scene.id, [])
                        if persona_id_to_name.get(pid)
                    ],
                }
                for scene in sim_scenes
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
            "ai_enhancement_completed": simulation.ai_enhancement_completed,
        }
        responses.append(response)
    
    logger.info(f"[BATCH_QUERY] Built {len(responses)} responses with batched queries")
    return responses


async def _check_persona_s3_image(
    persona: SimulationPersona, simulation_id: int
) -> Tuple[int, Optional[str]]:
    """
    Check S3 for persona avatar image (runs in parallel).
    
    Returns: (persona_id, s3_url or None)
    """
    image_url = persona.image_url
    needs_s3_check = (
        not image_url
        or (isinstance(image_url, str) and not image_url.strip())
        or (isinstance(image_url, str) and is_temporary_image_url(image_url))
    )
    
    if not needs_s3_check:
        return (persona.id, None)  # No update needed
    
    # Try each extension in parallel within this persona
    for ext in ["jpg", "png", "webp"]:
        s3_key = s3_service.get_persona_avatar_key(simulation_id, persona.id, ext)
        try:
            file_exists = await s3_service.file_exists(s3_key)
            if file_exists:
                s3_url = s3_service._build_public_url(s3_key)
                logger.info(f"[S3_PARALLEL] ✅ Found persona {persona.id} image: {s3_key}")
                return (persona.id, s3_url)
        except Exception as e:
            logger.warning(f"[S3_PARALLEL] Error checking S3 for persona {persona.id}: {e}")
            continue
    
    logger.warning(f"[S3_PARALLEL] ❌ Persona {persona.id} image not found in S3")
    return (persona.id, None)


async def _check_scene_s3_image(
    scene: SimulationScene, simulation_id: int
) -> Tuple[int, Optional[str]]:
    """
    Check S3 for scene image (runs in parallel).
    
    Returns: (scene_id, s3_url or None)
    """
    image_url = scene.image_url
    needs_s3_check = (
        not image_url
        or (isinstance(image_url, str) and not image_url.strip())
        or (isinstance(image_url, str) and is_temporary_image_url(image_url))
    )
    
    if not needs_s3_check:
        return (scene.id, None)  # No update needed
    
    # Try each extension
    for ext in ["jpg", "png", "webp"]:
        s3_key = s3_service.get_scene_image_key(simulation_id, scene.id, ext)
        try:
            file_exists = await s3_service.file_exists(s3_key)
            if file_exists:
                s3_url = s3_service._build_public_url(s3_key)
                logger.info(f"[S3_PARALLEL] ✅ Found scene {scene.id} image: {s3_key}")
                return (scene.id, s3_url)
        except Exception as e:
            logger.warning(f"[S3_PARALLEL] Error checking S3 for scene {scene.id}: {e}")
            continue
    
    logger.warning(f"[S3_PARALLEL] ❌ Scene {scene.id} image not found in S3")
    return (scene.id, None)


async def build_simulation_response(simulation: Simulation, db: Session) -> Dict:
    """Build simulation response with personas and scenes.

    OPTIMIZED: For draft/creating simulations, checks S3 in PARALLEL using asyncio.gather().
    This reduces wait time from (N personas + M scenes) * latency to max(latency).
    """
    personas = (
        db.query(SimulationPersona)
        .filter(
            SimulationPersona.simulation_id == simulation.id,
            SimulationPersona.deleted_at.is_(None),
        )
        .all()
    )

    scenes = (
        db.query(SimulationScene)
        .filter(SimulationScene.simulation_id == simulation.id)
        .filter(SimulationScene.deleted_at.is_(None))
        .order_by(SimulationScene.scene_order)
        .all()
    )

    is_draft = simulation.is_draft if simulation.is_draft is not None else False
    is_creating = simulation.status == "creating"

    # For draft/creating simulations, check S3 in PARALLEL
    if is_draft or is_creating:
        logger.info(
            f"[S3_PARALLEL] Checking images for simulation {simulation.id} "
            f"(draft={is_draft}, creating={is_creating}) - "
            f"{len(personas)} personas, {len(scenes)} scenes"
        )

        # Build parallel tasks for ALL personas and scenes
        persona_tasks = [
            _check_persona_s3_image(persona, simulation.id)
            for persona in personas
        ]
        scene_tasks = [
            _check_scene_s3_image(scene, simulation.id)
            for scene in scenes
        ]
        
        # Execute ALL S3 checks in parallel (single await)
        all_results = await asyncio.gather(
            *persona_tasks, *scene_tasks,
            return_exceptions=True
        )
        
        # Split results back into personas and scenes
        persona_results = all_results[:len(personas)]
        scene_results = all_results[len(personas):]
        
        # Build lookup maps for quick access
        persona_map = {p.id: p for p in personas}
        scene_map = {s.id: s for s in scenes}
        
        # Process persona results and update DB
        updates_made = False
        for result in persona_results:
            if isinstance(result, Exception):
                logger.warning(f"[S3_PARALLEL] Persona check exception: {result}")
                continue
            persona_id, s3_url = result
            if s3_url and persona_id in persona_map:
                persona_map[persona_id].image_url = s3_url
                db.add(persona_map[persona_id])
                updates_made = True
        
        # Process scene results and update DB
        for result in scene_results:
            if isinstance(result, Exception):
                logger.warning(f"[S3_PARALLEL] Scene check exception: {result}")
                continue
            scene_id, s3_url = result
            if s3_url and scene_id in scene_map:
                scene_map[scene_id].image_url = s3_url
                db.add(scene_map[scene_id])
                updates_made = True
        
        # Single commit for all updates (instead of N commits)
        if updates_made:
            db.commit()
            logger.info("[S3_PARALLEL] ✅ Committed all S3 URL updates")

    # Build scene-persona associations (involved personas)
    persona_id_to_name = {persona.id: persona.name for persona in personas}

    scene_persona_names: Dict[int, list] = {}
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
        learning_objectives = [
            item.strip()
            for item in learning_objectives.split("\n")
            if item.strip()
        ]

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
                "current_context": persona.current_context,
                "correlation": persona.correlation,
                "primary_goals": persona.primary_goals or [],
                "personality_traits": persona.personality_traits or {},
                "knowledge_areas": persona.knowledge_areas or [],
                "communication_style": persona.communication_style,
                "system_prompt": persona.system_prompt,
                "image_url": persona.image_url,
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
                "scene_type": getattr(scene, "scene_type", None) or "conversation",
                "code_language": getattr(scene, "code_language", None) or "python",
                "starter_code": getattr(scene, "starter_code", None),
                "code_grading_criteria": getattr(scene, "code_grading_criteria", None),
                "data_files": getattr(scene, "data_files", None),
                "reference_files": getattr(scene, "reference_files", None),
                "personas_involved": scene_persona_names.get(scene.id, []),
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
        "ai_enhancement_completed": simulation.ai_enhancement_completed,
    }

@router.get("/", response_model=List[SimulationPublishingResponse])
async def get_simulations(
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None, description="Filter by status: draft, active, archived"),
    include_drafts: Optional[bool] = Query(False, description="Include draft simulations"),
    current_user: User = Depends(get_current_user)
):
    """Get simulations with optional filtering by status.
    
    OPTIMIZED: Uses Redis caching + batched queries.
    - Cache TTL: 5 minutes
    - Invalidated when user modifies simulations
    - Before: 1 + N + N + (N*M) queries
    - After: 4 queries total (0 on cache hit)
    """
    # Build cache key based on user and query params
    cache_key = f"user:{current_user.id}:simulations:drafts={include_drafts}"
    if status:
        cache_key += f":status={status}"
    
    # Try cache first
    cached_data = cache_service.get(cache_key)
    if cached_data is not None:
        logger.info(f"[CACHE_HIT] Returning cached simulations for user {current_user.id}")
        return cached_data
    
    logger.info(f"[CACHE_MISS] Fetching simulations from DB for user {current_user.id}")
    
    try:
        service = PublishingService(db)
        simulations = service.repository.get_simulations_by_user(
            current_user.id, status, include_drafts
        )

        # OPTIMIZED: Use batched query builder instead of per-simulation queries
        result = await build_simulation_responses_batched(simulations, db)
        
        # Cache for 5 minutes (300 seconds)
        cache_service.set(cache_key, result, ttl=300)
        logger.info(f"[CACHE_SET] Cached {len(result)} simulations for user {current_user.id}")
        
        return result
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
    """Get draft simulations only.
    
    OPTIMIZED: Uses batched queries instead of N+1 pattern.
    """
    try:
        service = PublishingService(db)
        simulations = service.repository.get_draft_simulations(current_user.id)

        # OPTIMIZED: Use batched query builder
        return await build_simulation_responses_batched(simulations, db)
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
                detail="You can only access simulations you created",
            )

        return await build_simulation_response(simulation, db)
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
    current_user: User = Depends(get_current_user)
):
    """Publish a simulation (makes it available for assignment)."""
    logger.info(f"[PUBLISH] Starting publish for simulation {simulation_id}")

    service = PublishingService(db)

    target = service.repository.get_simulation_by_id(simulation_id)
    if not target:
        raise HTTPException(status_code=404, detail="Simulation not found")
    if target.created_by != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only publish simulations you created",
        )

    simulation = await service.publish_simulation(simulation_id)

    # Invalidate cache so dashboard shows the newly published simulation
    if simulation.created_by:
        invalidate_user_simulations_cache(simulation.created_by)

    return PublishResponse(
        status="published",
        simulation_id=simulation.id,
        message=f"Simulation '{simulation.title}' has been published"
    )


@router.get("/{simulation_id}/upload-status", response_model=ImageUploadStatusResponse)
async def get_upload_status(
    simulation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get image upload status for a simulation."""
    service = PublishingService(db)
    simulation = service.repository.get_simulation_by_id(simulation_id)

    if not simulation:
        raise HTTPException(status_code=404, detail="Simulation not found")

    # Check permissions - user can only check their own simulations
    if simulation.created_by != current_user.id:
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

    return await build_simulation_response(simulation, db)


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
        
        # Invalidate cache so dashboard shows the updated simulation
        if user_id:
            invalidate_user_simulations_cache(user_id)
        
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
            simulation_id, status_request.status, current_user.id
        )
        
        # Invalidate cache so dashboard shows the updated status
        invalidate_user_simulations_cache(current_user.id)

        return await build_simulation_response(simulation, db)
        
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
        
        # Invalidate cache so dashboard reflects the deletion
        if user_id:
            invalidate_user_simulations_cache(user_id)
        
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
            logger.error(f"WebSocket authentication error: invalid user id in token for user {user_id}")
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
    websocket = user_websocket_connections.get(user_id)
    if websocket is None:
        logger.debug(f"User {user_id} not connected to WebSocket, skipping notification for simulation {simulation_id}")
        return  # User not connected, no notification needed
    
    try:
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
