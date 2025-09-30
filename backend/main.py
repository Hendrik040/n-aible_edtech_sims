# AI Agent Education Platform - Main FastAPI Application
from fastapi import FastAPI, HTTPException, Depends, status, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from typing import List, Optional
import uvicorn
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import asynccontextmanager
import asyncio
import logging
import time
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Logger for main application
logger = logging.getLogger(__name__)

from database.connection import get_db, engine, settings, _validate_environment
from database.models import Base, User, Scenario, ScenarioPersona, ScenarioScene, ScenarioFile, ScenarioReview, scene_personas
from database.schemas import (
    ScenarioCreate, UserRegister, UserLogin, UserLoginResponse, 
    UserResponse, UserUpdate, PasswordChange
)
from utilities.auth import (
    get_password_hash, authenticate_user, create_access_token, 
    get_current_user, get_current_user_optional, require_admin
)
from utilities.debug_logging import debug_log
from utilities.rate_limiter import check_test_login_rate_limit

# Import API routers
from api.professor.invitations import router as professor_invitations_router
from api.professor.notifications import router as professor_notifications_router
from api.messages import router as messages_router
from api.student.notifications import router as student_notifications_router
from api.student.cohorts import router as student_cohorts_router
from api.student.simulation_instances import router as student_simulation_instances_router
from api.parse_pdf import router as pdf_router
from api.pdf_progress import router as progress_router
from api.simulation import router as simulation_router
from api.publishing import router as publishing_router
from api.oauth import router as oauth_router, lifespan as oauth_lifespan
from api.cohorts import router as cohorts_router
from services.session_manager import session_manager_lifespan

# Startup check module was removed - startup checks are no longer performed

# Import session manager for cleanup task
from services.session_manager import session_manager

# Import Redis services
from utilities.redis_manager import redis_manager, redis_cleanup_task
from services.ai_cache_service import ai_cache_service
from services.db_cache_service import db_cache_service

# Combined lifespan manager for all background tasks
@asynccontextmanager
async def combined_lifespan(app):
    """Combined lifespan manager for OAuth, session, and Redis cleanup tasks"""
    # Validate environment on startup
    _validate_environment()
    
    # Test Redis connection on startup
    try:
        if not redis_manager.is_available():
            raise RuntimeError("Redis is not available. Please check your Redis configuration.")
        logger.info("Redis connection verified successfully")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        raise RuntimeError(f"Redis initialization failed: {e}")
    
    # Start OAuth cleanup task
    async with oauth_lifespan(app):
        # Start session manager cleanup task
        async with session_manager_lifespan(app):
            # Start Redis cleanup task
            redis_task = asyncio.create_task(redis_cleanup_task())
            try:
                yield
            finally:
                redis_task.cancel()
                try:
                    await redis_task
                except asyncio.CancelledError:
                    pass

# Create FastAPI app
app = FastAPI(
    title="AI Agent Education Platform",
    description="Transform business case studies into immersive AI-powered educational simulations",
    version="2.0.0",
    lifespan=combined_lifespan
)

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring and load balancers"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.on_event("startup")
async def startup_event():
    """Run startup checks when the application starts"""
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("🚀 Starting AI Agent Education Platform...")
    
    # Run database migrations in production
    if settings.environment == "production":
        try:
            logger.info("🗄️  Running database migrations...")
            import subprocess
            import sys
            from pathlib import Path
            
            # Change to database directory and run migrations
            db_dir = Path(__file__).parent / "database"
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=db_dir,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                logger.info("✅ Database migrations completed successfully")
            else:
                logger.warning(f"⚠️  Migration warning: {result.stderr}")
                logger.info("💡 App will continue - migrations may have been already applied")
                
        except Exception as e:
            logger.warning(f"⚠️  Migration error: {e}")
            logger.info("💡 App will continue - database may already be up to date")
    
    logger.info("✅ Application startup completed successfully!")
    

# CORS middleware - Dynamic origins based on environment
def get_cors_origins():
    """Get CORS origins based on environment"""
    base_origins = [
        "http://localhost:3000", 
        "http://localhost:5173", 
        "http://127.0.0.1:3000", 
        "http://127.0.0.1:5173",
        "http://127.0.0.1:51231"
    ]
    
    # Add production origins from environment variable
    cors_origins = os.getenv("CORS_ORIGINS")
    if cors_origins:
        # Split by comma and add each origin
        additional_origins = [origin.strip() for origin in cors_origins.split(",")]
        base_origins.extend(additional_origins)
    
    # Add production origins
    if settings.environment == "production":
        base_origins.extend([
            "https://trustworthy-perfection-production.up.railway.app",  # Your frontend URL
        ])
    
    # Add custom frontend URL from environment if set
    frontend_url = os.getenv("FRONTEND_BASE_URL")
    if frontend_url:
        base_origins.append(frontend_url)
    
    return base_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(pdf_router, tags=["PDF Processing"])
app.include_router(progress_router, tags=["PDF Progress"])
app.include_router(simulation_router, tags=["Simulation"])
app.include_router(publishing_router, tags=["Publishing"])
app.include_router(oauth_router, tags=["OAuth"])
app.include_router(cohorts_router, tags=["Cohorts"])
app.include_router(professor_invitations_router, tags=["Professor Invitations"])
app.include_router(professor_notifications_router, tags=["Professor Notifications"])
app.include_router(messages_router, tags=["Messages"])
app.include_router(student_notifications_router, tags=["Student Notifications"])
app.include_router(student_cohorts_router, tags=["Student Cohorts"])
app.include_router(student_simulation_instances_router, tags=["Student Simulation Instances"])

# Import progress manager for WebSocket endpoint
from api.pdf_progress import progress_manager

# Add WebSocket endpoint directly to the app
@app.websocket("/ws/pdf-progress/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for PDF parsing progress updates"""
    await progress_manager.connect(websocket, session_id)
    
    try:
        while True:
            # Keep connection alive and handle any incoming messages
            data = await websocket.receive_text()
            import json
            message = json.loads(data)
            
            if message.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "timestamp": time.time()}))
            
    except WebSocketDisconnect:
        progress_manager.disconnect(session_id)
        print(f"WebSocket {session_id} disconnected")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
        progress_manager.disconnect(session_id)

# Create database tables (development only)
if settings.environment != "production":
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created (development mode)")
else:
    print("⚠️  Skipping create_all in production - use Alembic migrations")

# Mount static files for serving images
static_dir = Path("static")
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "AI Simulation Marketplace Platform API",
        "version": "2.0.0",
        "status": "active"
    }

@app.get("/api/scenarios/")
async def get_scenarios(
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Get scenarios with their personas and scenes"""
    try:
        # If user is authenticated, show their scenarios; otherwise show all public scenarios
        if current_user:
            # For authenticated users, show all their scenarios (both draft and active)
            # but prioritize active versions over draft versions for the same scenario
            scenarios = db.query(Scenario).filter(
                Scenario.created_by == current_user.id,
                Scenario.deleted_at.is_(None)  # Exclude soft-deleted scenarios
            ).order_by(
                Scenario.status.desc(),  # Active scenarios first
                Scenario.updated_at.desc()  # Then by most recently updated
            ).all()
        else:
            # For unauthenticated users, show all public scenarios
            scenarios = db.query(Scenario).filter(
                Scenario.is_public == True,
                Scenario.deleted_at.is_(None)  # Exclude soft-deleted scenarios
            ).order_by(Scenario.created_at.desc()).all()
        
        result = []
        for scenario in scenarios:
            # Get personas for this scenario
            personas = db.query(ScenarioPersona).filter(
                ScenarioPersona.scenario_id == scenario.id
            ).all()
            
            # Get scenes for this scenario
            scenes = db.query(ScenarioScene).filter(
                ScenarioScene.scenario_id == scenario.id
            ).order_by(ScenarioScene.scene_order).all()
            
            scenario_data = {
                "id": scenario.id,
                "unique_id": scenario.unique_id,
                "title": scenario.title,
                "description": scenario.description,
                "challenge": scenario.challenge,
                "industry": scenario.industry,
                "learning_objectives": scenario.learning_objectives or [],
                "student_role": scenario.student_role,
                "status": scenario.status,  # Add status field
                "created_at": scenario.created_at.isoformat() if scenario.created_at else None,
                "is_public": scenario.is_public,
                "personas": [
                    {
                        "id": persona.id,
                        "name": persona.name,
                        "role": persona.role,
                        "background": persona.background,
                        "correlation": persona.correlation,
                        "primary_goals": persona.primary_goals or [],
                        "personality_traits": persona.personality_traits or {}
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
                        "estimated_duration": scene.estimated_duration,
                        "image_url": scene.image_url
                    }
                    for scene in scenes
                ]
            }
            result.append(scenario_data)
        
        return result
        
    except Exception as e:
        print(f"[ERROR] Failed to fetch scenarios: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch scenarios: {str(e)}")

@app.get("/api/scenarios/drafts/")
async def get_draft_scenarios(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get draft scenarios created by the current user"""
    try:
        scenarios = db.query(Scenario).filter(
            Scenario.created_by == current_user.id,
            Scenario.is_draft == True,  # Only show draft scenarios
            Scenario.deleted_at.is_(None)  # Exclude soft-deleted scenarios
        ).order_by(Scenario.created_at.desc()).all()
        
        result = []
        for scenario in scenarios:
            # Get personas for this scenario
            personas = db.query(ScenarioPersona).filter(
                ScenarioPersona.scenario_id == scenario.id
            ).all()
            
            # Get scenes for this scenario
            scenes = db.query(ScenarioScene).filter(
                ScenarioScene.scenario_id == scenario.id
            ).order_by(ScenarioScene.scene_order).all()
            
            # Get scene-persona relationships for each scene
            scene_persona_relationships = {}
            for scene in scenes:
                relationships = db.query(scene_personas).filter(
                    scene_personas.c.scene_id == scene.id
                ).all()
                scene_persona_relationships[scene.id] = relationships
            
            scenario_data = {
                "id": scenario.id,
                "unique_id": scenario.unique_id,
                "title": scenario.title,
                "description": scenario.description,
                "challenge": scenario.challenge,
                "industry": scenario.industry,
                "learning_objectives": scenario.learning_objectives or [],
                "student_role": scenario.student_role,
                "status": scenario.status,
                "is_draft": scenario.is_draft,
                "published_version_id": scenario.published_version_id,
                "created_at": scenario.created_at.isoformat() if scenario.created_at else None,
                "is_public": scenario.is_public,
                # Completion status fields
                "completion_status": scenario.completion_status,
                "name_completed": scenario.name_completed,
                "description_completed": scenario.description_completed,
                "personas_completed": scenario.personas_completed,
                "scenes_completed": scenario.scenes_completed,
                "images_completed": scenario.images_completed,
                "learning_outcomes_completed": scenario.learning_outcomes_completed,
                "ai_enhancement_completed": scenario.ai_enhancement_completed,
                "personas": [
                    {
                        "id": persona.id,
                        "name": persona.name,
                        "role": persona.role,
                        "background": persona.background,
                        "correlation": persona.correlation,
                        "primary_goals": persona.primary_goals or [],
                        "personality_traits": persona.personality_traits or {}
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
                        "estimated_duration": scene.estimated_duration,
                        "image_url": scene.image_url,
                        "timeout_turns": scene.timeout_turns,
                        "success_metric": scene.success_metric,
                        "personas_involved": [
                            persona.name for persona in personas 
                            if any(rel.persona_id == persona.id for rel in scene_persona_relationships.get(scene.id, []))
                        ],
                        "created_at": scene.created_at.isoformat() if scene.created_at else None,
                        "updated_at": scene.updated_at.isoformat() if scene.updated_at else None,
                        "personas": [
                            {
                                "id": persona.id,
                                "scenario_id": persona.scenario_id,
                                "name": persona.name,
                                "role": persona.role,
                                "background": persona.background,
                                "correlation": persona.correlation,
                                "primary_goals": persona.primary_goals or [],
                                "personality_traits": persona.personality_traits or {},
                                "created_at": persona.created_at.isoformat() if persona.created_at else None,
                                "updated_at": persona.updated_at.isoformat() if persona.updated_at else None
                            }
                            for persona in personas 
                            if any(rel.persona_id == persona.id for rel in scene_persona_relationships.get(scene.id, []))
                        ]
                    }
                    for scene in scenes
                ]
            }
            result.append(scenario_data)
        
        return result
        
    except Exception as e:
        print(f"[ERROR] Failed to fetch draft scenarios: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch draft scenarios: {str(e)}")

@app.delete("/api/scenarios/unique/{unique_id}")
async def delete_scenario_by_unique_id(
    unique_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a scenario by unique_id using soft deletion"""
    from services.soft_deletion import SoftDeletionService
    
    try:
        # Find the scenario by unique_id
        scenario = db.query(Scenario).filter(
            Scenario.unique_id == unique_id,
            Scenario.created_by == current_user.id,
            Scenario.deleted_at.is_(None)  # Only get non-deleted scenarios
        ).first()
        
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")
        
        # Store scenario info before deletion
        scenario_title = scenario.title
        scenario_id = scenario.id
        
        debug_log(f"Soft deleting scenario {unique_id} (ID: {scenario_id})")
        
        # Use soft deletion service
        service = SoftDeletionService(db)
        success = service.soft_delete_scenario(
            scenario_id=scenario_id,
            deleted_by=current_user.id,
            reason="Unique ID deletion"
        )
        
        if not success:
            raise HTTPException(
                status_code=500, 
                detail="Failed to delete scenario"
            )
        
        return {
            "status": "success", 
            "message": f"Scenario '{scenario_title}' deleted successfully. User progress data has been archived."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        debug_log(f"Error deleting scenario {unique_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete scenario: {str(e)}")

@app.delete("/api/scenarios/drafts/{scenario_id}")
async def delete_draft_scenario(
    scenario_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Soft delete a draft scenario"""
    from services.soft_deletion import SoftDeletionService
    
    try:
        # Find the draft scenario
        scenario = db.query(Scenario).filter(
            Scenario.id == scenario_id,
            Scenario.created_by == current_user.id,
            Scenario.is_draft == True,
            Scenario.deleted_at.is_(None)  # Only get non-deleted scenarios
        ).first()
        
        if not scenario:
            raise HTTPException(status_code=404, detail="Draft scenario not found")
        
        # Store scenario title before deletion
        scenario_title = scenario.title
        
        debug_log(f"Soft deleting draft scenario {scenario_id}")
        
        # Use soft deletion service
        service = SoftDeletionService(db)
        success = service.soft_delete_scenario(
            scenario_id=scenario_id,
            deleted_by=current_user.id,
            reason="Draft deletion"
        )
        
        if not success:
            raise HTTPException(
                status_code=500, 
                detail="Failed to delete draft scenario"
            )
        
        return {
            "message": f"Draft scenario '{scenario_title}' deleted successfully. User progress data has been archived.",
            "deleted_id": scenario_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to delete draft scenario: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete draft scenario: {str(e)}")

@app.get("/api/scenarios/drafts/{scenario_id}")
async def get_draft_scenario(
    scenario_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Return the draft scenario payload for editing, including its personas, scenes, and per-scene persona relationships.
    
    Parameters:
        scenario_id (int): ID of the draft scenario to retrieve. `current_user` and `db` are injected dependencies.
    
    Returns:
        dict: A dictionary containing scenario fields (id, title, description, challenge, industry, learning_objectives, student_role, status, is_draft, published_version_id, created_at, is_public), completion status flags, a `personas` list of persona objects, and a `scenes` list where each scene includes its fields, `personas_involved` (names), and a `personas` list of persona objects associated with that scene.
    
    Raises:
        HTTPException: 404 if the draft scenario is not found or does not belong to the current user; 500 for unexpected internal errors.
    """
    try:
        scenario = db.query(Scenario).filter(
            Scenario.id == scenario_id,
            Scenario.created_by == current_user.id,
            Scenario.is_draft == True
        ).first()
        
        if not scenario:
            raise HTTPException(status_code=404, detail="Draft scenario not found")
        
        # Get personas for this scenario
        personas = db.query(ScenarioPersona).filter(
            ScenarioPersona.scenario_id == scenario.id
        ).all()
        
        # Get scenes for this scenario
        scenes = db.query(ScenarioScene).filter(
            ScenarioScene.scenario_id == scenario.id
        ).order_by(ScenarioScene.scene_order).all()
        
        # Get scene-persona relationships for each scene
        scene_persona_relationships = {}
        for scene in scenes:
            relationships = db.query(scene_personas).filter(
                scene_personas.c.scene_id == scene.id
            ).all()
            # Extract persona IDs from relationships
            scene_persona_relationships[scene.id] = [rel.persona_id for rel in relationships]
        
        scenario_data = {
            "id": scenario.id,
            "title": scenario.title,
            "description": scenario.description,
            "challenge": scenario.challenge,
            "industry": scenario.industry,
            "learning_objectives": scenario.learning_objectives or [],
            "student_role": scenario.student_role,
            "status": scenario.status,
            "is_draft": scenario.is_draft,
            "published_version_id": scenario.published_version_id,
            "created_at": scenario.created_at.isoformat() if scenario.created_at else None,
            "is_public": scenario.is_public,
            # Completion status fields
            "completion_status": scenario.completion_status,
            "name_completed": scenario.name_completed,
            "description_completed": scenario.description_completed,
            "personas_completed": scenario.personas_completed,
            "scenes_completed": scenario.scenes_completed,
            "images_completed": scenario.images_completed,
            "learning_outcomes_completed": scenario.learning_outcomes_completed,
            "ai_enhancement_completed": scenario.ai_enhancement_completed,
            "personas": [
                {
                    "id": persona.id,
                    "name": persona.name,
                    "role": persona.role,
                    "background": persona.background,
                    "correlation": persona.correlation,
                    "primary_goals": persona.primary_goals or [],
                    "personality_traits": persona.personality_traits or {}
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
                    "estimated_duration": scene.estimated_duration,
                    "image_url": scene.image_url,
                    "timeout_turns": scene.timeout_turns,
                    "success_metric": scene.success_metric,
                    "personas_involved": [
                        persona.name for persona in personas 
                        if persona.id in scene_persona_relationships.get(scene.id, [])
                    ],
                    "created_at": scene.created_at.isoformat() if scene.created_at else None,
                    "updated_at": scene.updated_at.isoformat() if scene.updated_at else None,
                    "personas": [
                        {
                            "id": persona.id,
                            "scenario_id": persona.scenario_id,
                            "name": persona.name,
                            "role": persona.role,
                            "background": persona.background,
                            "correlation": persona.correlation,
                            "primary_goals": persona.primary_goals or [],
                            "personality_traits": persona.personality_traits or {},
                            "created_at": persona.created_at.isoformat() if persona.created_at else None,
                            "updated_at": persona.updated_at.isoformat() if persona.updated_at else None
                        }
                        for persona in personas 
                        if persona.id in scene_persona_relationships.get(scene.id, [])
                    ]
                }
                for scene in scenes
            ]
        }
        
        return scenario_data
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to fetch draft scenario: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch draft scenario: {str(e)}")

@app.put("/api/scenarios/{scenario_id}/status")
async def update_scenario_status(
    scenario_id: int,
    status_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update scenario status (draft/active/archived)"""
    try:
        scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")
        
        # Check ownership
        if scenario.created_by != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to update this scenario")
        
        # Validate status
        new_status = status_data.get("status")
        if new_status not in ["draft", "active"]:
            raise HTTPException(status_code=400, detail="Invalid status. Must be 'draft' or 'active'")
        
        # Update status and is_draft field
        scenario.status = new_status
        scenario.updated_at = datetime.utcnow()
        
        # Update is_draft field based on status
        if new_status == "draft":
            scenario.is_draft = True
            scenario.is_public = False
        elif new_status == "active":
            scenario.is_draft = False
            scenario.is_public = True
        
        db.commit()
        db.refresh(scenario)
        
        return {
            "id": scenario.id,
            "status": scenario.status,
            "is_draft": scenario.is_draft,
            "is_public": scenario.is_public,
            "updated_at": scenario.updated_at.isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Failed to update scenario status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update scenario status: {str(e)}")

# --- USER AUTHENTICATION & MANAGEMENT ---
@app.post("/users/register", response_model=UserResponse)
async def register_user(user: UserRegister, response: Response, db: Session = Depends(get_db)):
    """Register a new user"""
    print(f"🔍 Registration request received for role: {user.role}")
    print(f"📧 Email: {user.email}")
    print(f"👤 Full name: {user.full_name}")
    
    # Check if user already exists
    existing_user = db.query(User).filter(
        (User.email == user.email) | (User.username == user.username)
    ).first()
    
    if existing_user:
        if existing_user.email == user.email:
            raise HTTPException(status_code=400, detail="Email already registered")
        else:
            raise HTTPException(status_code=400, detail="Username already taken")
    
    # Generate role-based user ID
    from utilities.id_generator import generate_unique_user_id
    
    try:
        user_id = generate_unique_user_id(db, user.role)
        print(f"✅ Generated user ID: {user_id} for role: {user.role}")
    except Exception as e:
        print(f"❌ Failed to generate user ID: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate user ID: {str(e)}")
    
    # Create new user
    hashed_password = get_password_hash(user.password)
    db_user = User(
        user_id=user_id,
        email=user.email,
        full_name=user.full_name,
        username=user.username,
        password_hash=hashed_password,
        role=user.role,  # Set the role from registration
        bio=user.bio,
        avatar_url=user.avatar_url,
        profile_public=user.profile_public,
        allow_contact=user.allow_contact
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # Create access token and set HttpOnly cookie
    access_token = create_access_token(data={"sub": str(db_user.id)})
    # For cross-origin requests, we need samesite="none" in production
    is_production = settings.environment == "production"
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,  # HttpOnly cookie - not accessible via JavaScript
        secure=is_production,  # Required for samesite="none"
        samesite="none" if is_production else "lax",  # "none" for cross-origin in production
        max_age=30 * 24 * 60 * 60  # 30 days (same as token expiry)
    )
    
    return db_user

@app.post("/users/login", response_model=UserLoginResponse)
async def login_user(user: UserLogin, response: Response, db: Session = Depends(get_db)):
    """Login user and return access token"""
    db_user = authenticate_user(db, user.email, user.password)
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    
    access_token = create_access_token(data={"sub": str(db_user.id)})
    
    # Set HttpOnly cookie for secure authentication
    # For cross-origin requests, we need samesite="none" in production
    is_production = settings.environment == "production"
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,  # HttpOnly cookie - not accessible via JavaScript
        secure=is_production,  # Required for samesite="none"
        samesite="none" if is_production else "lax",  # "none" for cross-origin in production
        max_age=30 * 24 * 60 * 60  # 30 days (same as token expiry)
    )
    
    return UserLoginResponse(
        access_token="",  # Empty token - authentication via HttpOnly cookie only
        token_type="cookie",
        user=UserResponse(
            id=db_user.id,
            email=db_user.email,
            full_name=db_user.full_name,
            username=db_user.username,
            bio=db_user.bio,
            avatar_url=db_user.avatar_url,
            role=db_user.role,
            published_scenarios=db_user.published_scenarios,
            total_simulations=db_user.total_simulations,
            reputation_score=db_user.reputation_score,
            profile_public=db_user.profile_public,
            allow_contact=db_user.allow_contact,
            is_active=db_user.is_active,
            is_verified=db_user.is_verified,
            created_at=db_user.created_at,
            updated_at=db_user.updated_at
        )
    )

@app.post("/users/check-email")
async def check_email_exists(request: dict, db: Session = Depends(get_db)):
    """Check if an email already exists in the database"""
    email = request.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    
    existing_user = db.query(User).filter(User.email == email).first()
    return {"exists": existing_user is not None}

@app.post("/users/logout")
async def logout_user(response: Response):
    """Logout user by clearing HttpOnly cookie"""
    is_production = settings.environment == "production"
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=is_production,  # Match login cookie settings
        samesite="none" if is_production else "lax"
    )
    return {"message": "Successfully logged out"}

@app.get("/users/me", response_model=UserResponse)
async def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Get current user profile"""
    return current_user

@app.post("/test-login")
async def test_login(
    user: UserLogin, 
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(check_test_login_rate_limit)
):
    """Test endpoint to debug login issues (development only)"""
    # Only allow in development environment
    if settings.environment == "production":
        raise HTTPException(
            status_code=404,
            detail="Not found"
        )
    
    try:
        db_user = authenticate_user(db, user.email, user.password)
        if not db_user:
            # Always return generic error to prevent user enumeration
            return {"error": "Authentication failed", "status": "error"}
        
        return {"success": True, "user": {"id": "redacted"}}
    except Exception as e:
        # Log the actual error server-side but return generic error to client
        print(f"[ERROR] Test login failed: {str(e)}")
        return {"error": "Authentication failed", "status": "error"}

@app.put("/users/me", response_model=UserResponse)
async def update_current_user(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update current user profile"""
    # Update fields
    for field, value in user_update.dict(exclude_unset=True).items():
        setattr(current_user, field, value)
    
    current_user.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(current_user)
    
    return current_user

@app.post("/users/change-password")
async def change_password(
    password_change: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change user password"""
    # Verify current password
    if not authenticate_user(db, current_user.email, password_change.current_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    # Update password
    current_user.password_hash = get_password_hash(password_change.new_password)
    current_user.updated_at = datetime.utcnow()
    
    db.commit()
    
    return {"message": "Password changed successfully"}

@app.post("/users/activity")
async def track_user_activity(
    activity_data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Track user activity for inactivity monitoring"""
    try:
        # Update user's last_activity timestamp
        current_user.last_activity = datetime.utcnow()
        db.commit()
        return {"status": "success", "timestamp": current_user.last_activity.isoformat()}
    except Exception as e:
        # Log error but don't fail the request to avoid disrupting UX
        print(f"[ERROR] Activity tracking failed: {str(e)}")
        return {"status": "error", "message": "Activity tracking failed"}

@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user_profile(user_id: int, db: Session = Depends(get_db)):
    """Get user profile (public information only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Only return public profiles
    if not user.profile_public:
        raise HTTPException(status_code=404, detail="Profile is private")
    
    return user

# --- BASIC SCENARIO ENDPOINTS ---
@app.get("/scenarios", response_model=List[dict])
async def get_public_scenarios(
    skip: int = 0, 
    limit: int = 20, 
    db: Session = Depends(get_db)
):
    """Get public scenarios for marketplace"""
    scenarios = db.query(Scenario).filter(
        Scenario.is_public == True,
        Scenario.deleted_at.is_(None)  # Exclude soft-deleted scenarios
    ).offset(skip).limit(limit).all()
    
    return [
        {
            "id": scenario.id,
            "title": scenario.title,
            "description": scenario.description,
            "category": scenario.category,
            "difficulty_level": scenario.difficulty_level,
            "estimated_duration": scenario.estimated_duration,
            "rating_avg": scenario.rating_avg,
            "rating_count": scenario.rating_count,
            "usage_count": scenario.usage_count
        }
        for scenario in scenarios
    ]

@app.get("/scenarios/{scenario_id}")
async def get_scenario_details(scenario_id: int, db: Session = Depends(get_db)):
    """Get detailed scenario information"""
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    
    # Count personas and scenes
    persona_count = db.query(ScenarioPersona).filter(ScenarioPersona.scenario_id == scenario_id).count()
    scene_count = db.query(ScenarioScene).filter(ScenarioScene.scenario_id == scenario_id).count()
    
    return {
        "id": scenario.id,
        "title": scenario.title,
        "description": scenario.description,
        "challenge": scenario.challenge,
        "industry": scenario.industry,
        "learning_objectives": scenario.learning_objectives,
        "student_role": scenario.student_role,
        "category": scenario.category,
        "difficulty_level": scenario.difficulty_level,
        "estimated_duration": scenario.estimated_duration,
        "tags": scenario.tags,
        "rating_avg": scenario.rating_avg,
        "rating_count": scenario.rating_count,
        "usage_count": scenario.usage_count,
        "persona_count": persona_count,
        "scene_count": scene_count,
        "is_public": scenario.is_public,
        "created_at": scenario.created_at
    }

@app.get("/api/test")
async def test_endpoint():
    """Test endpoint to verify server is working"""
    return {"status": "ok", "message": "Server is working"}

@app.get("/api/test-auth")
async def test_auth_endpoint(current_user: User = Depends(get_current_user)):
    """Test endpoint with authentication"""
    return {"status": "ok", "user": current_user.email}

@app.get("/api/test-db")
async def test_db_endpoint(db: Session = Depends(get_db)):
    """Test endpoint with database"""
    try:
        count = db.query(Scenario).count()
        return {"status": "ok", "scenario_count": count}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/api/test-combined")
async def test_combined_endpoint(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Test endpoint with both database and authentication"""
    try:
        count = db.query(Scenario).count()
        return {"status": "ok", "scenario_count": count, "user": current_user.email}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/api/scenario-test/{scenario_id}")
async def test_scenario_endpoint(scenario_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Test endpoint with scenario_id parameter"""
    try:
        scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
        if not scenario:
            return {"status": "error", "error": "Scenario not found"}
        return {"status": "ok", "scenario_id": scenario_id, "title": scenario.title, "user": current_user.email}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/api/scenarios/{scenario_id}/full")
async def get_scenario_full(scenario_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Get full scenario with personas and scenes including scene-persona relationships"""
    try:
        print(f"[DEBUG] Starting get_scenario_full for scenario_id: {scenario_id}")
        print(f"[DEBUG] Database session: {db}")
        print(f"[DEBUG] Current user: {current_user.email}")
        return {"status": "ok", "scenario_id": scenario_id, "user": current_user.email}
    except Exception as e:
        print(f"[ERROR] get_scenario_full failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# --- REDIS CACHE MANAGEMENT ---
@app.get("/api/cache/stats")
async def get_cache_stats(current_user: User = Depends(require_admin)):
    """Get cache statistics (admin only)"""
    try:
        ai_stats = ai_cache_service.get_cache_stats()
        db_stats = db_cache_service.get_cache_stats()
        redis_info = {
            "redis_available": redis_manager.is_available(),
            "total_keys": len(redis_manager.get_keys("*"))
        }
        
        return {
            "ai_cache": ai_stats,
            "db_cache": db_stats,
            "redis_info": redis_info,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get cache statistics: {str(e)}")

@app.post("/api/cache/invalidate/user/{user_id}")
async def invalidate_user_cache(user_id: int, current_user: User = Depends(require_admin)):
    """Invalidate all cache entries for a specific user (admin only)"""
    try:
        ai_count = ai_cache_service.invalidate_user_cache(user_id)
        db_count = db_cache_service.invalidate_user_related_cache(user_id)
        
        return {
            "message": f"Invalidated cache for user {user_id}",
            "ai_cache_invalidated": ai_count,
            "db_cache_invalidated": db_count,
            "total_invalidated": ai_count + db_count
        }
    except Exception as e:
        logger.error(f"Failed to invalidate user cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to invalidate user cache: {str(e)}")

@app.post("/api/cache/invalidate/scenario/{scenario_id}")
async def invalidate_scenario_cache(scenario_id: int, current_user: User = Depends(require_admin)):
    """Invalidate all cache entries for a specific scenario (admin only)"""
    try:
        ai_count = ai_cache_service.invalidate_simulation_cache(scenario_id)
        db_count = db_cache_service.invalidate_scenario_cache(scenario_id)
        
        return {
            "message": f"Invalidated cache for scenario {scenario_id}",
            "ai_cache_invalidated": ai_count,
            "db_cache_invalidated": db_count,
            "total_invalidated": ai_count + db_count
        }
    except Exception as e:
        logger.error(f"Failed to invalidate scenario cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to invalidate scenario cache: {str(e)}")

@app.post("/api/cache/cleanup")
async def cleanup_cache(current_user: User = Depends(require_admin)):
    """Manually trigger cache cleanup (admin only)"""
    try:
        ai_cleaned = ai_cache_service.cleanup_expired_cache()
        db_cleaned = db_cache_service.cleanup_expired_cache()
        
        return {
            "message": "Cache cleanup completed",
            "ai_cache_entries": ai_cleaned,
            "db_cache_entries": db_cleaned
        }
    except Exception as e:
        logger.error(f"Failed to cleanup cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cleanup cache: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 