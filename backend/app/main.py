"""
Application Entry Point

This file acts as the wiring layer for the application:
- Creates the FastAPI app instance
- Configures middleware
- Registers routers
- Defines lifecycle hooks
"""

import logging
import sys
from sqlalchemy import text
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from fastapi import Depends

from app.lifespan import lifespan
from app.middleware import configure_middleware
from app.routers import auth as auth_wiring
from app.routers import pdf_processing as pdf_processing_wiring
from app.routers import publishing as publishing_wiring
from app.routers import professor as professor_wiring
from app.routers import invites as invites_router
from common.db.connection import SessionLocal

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Reduce SQLAlchemy logging verbosity - only show WARNING and above
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.pool').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.dialects').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Health check cache (module-level so tests can import/inspect)
import time as _time
_health_cache: dict = {"status": None, "ts": 0.0}
_HEALTH_CACHE_TTL = 30  # seconds

def create_app() -> FastAPI:
    """Factory function to create the FastAPI application."""
    
    app = FastAPI(
        title="n-gage Backend",
        description="Backend API for n-gage EdTech simulation platform",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 0. Global exception handlers
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Catch all unhandled exceptions to prevent server crashes."""
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "error": str(exc)}
        )
    
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """Handle HTTP exceptions."""
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle validation errors."""
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors()}
        )

    # 1. Configure Middleware (CORS, etc.)
    configure_middleware(app)

    # 2. Register Routers
    # We import wiring routers from app.routers.* which in turn import module routers
    app.include_router(auth_wiring.router)
    app.include_router(pdf_processing_wiring.router)
    app.include_router(publishing_wiring.router)
    app.include_router(professor_wiring.router)
    app.include_router(invites_router.router)
    
    # Include professor and student routers
    from modules.professor.router import router as professor_router
    from modules.student.router import router as student_router
    from modules.notifications.router import router as notifications_router
    from modules.auth.profile_router import router as profile_router
    app.include_router(professor_router)
    app.include_router(student_router)
    app.include_router(notifications_router)
    app.include_router(profile_router)
    
    # Simulation router
    from app.routers import simulation as simulation_wiring
    app.include_router(simulation_wiring.router)
    
    # Add route alias for /api/stream-chat -> delegates to /api/simulation/linear-chat-stream
    # Frontend calls /api/stream-chat, so we provide an alias
    from modules.simulation.router import linear_chat_stream as linear_chat_stream_handler
    from modules.simulation.schemas.dto import SimulationChatRequest
    from app.dependencies import get_current_user
    from common.db.connection import get_db as get_db_func
    
    @app.post("/api/stream-chat")
    async def stream_chat_alias(
        request: SimulationChatRequest,
        current_user = Depends(get_current_user),
        db = Depends(get_db_func)
    ):
        """Route alias for /api/stream-chat -> /api/simulation/linear-chat-stream"""
        return await linear_chat_stream_handler(request, current_user, db)

    # 3. Health Check (cached to reduce database polling)
    @app.get("/health", tags=["System"])
    async def health_check():
        """Health check endpoint with cached database connectivity test."""
        now = _time.monotonic()
        # Return cached result if still fresh
        if _health_cache["status"] is not None and (now - _health_cache["ts"]) < _HEALTH_CACHE_TTL:
            return _health_cache["status"]

        try:
            # Test database connection
            db = SessionLocal()
            try:
                db.execute(text("SELECT 1"))
                db_status = "connected"
            except Exception as e:
                logger.warning(f"Database health check failed: {e}")
                db_status = f"error: {str(e)}"
            finally:
                db.close()

            result = {
                "status": "ok",
                "version": "2.0.0",
                "database": db_status
            }
            _health_cache["status"] = result
            _health_cache["ts"] = now
            return result
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return JSONResponse(
                status_code=503,
                content={"status": "degraded", "error": str(e)}
            )

    return app

# Create the app instance for uvicorn
app = create_app()
