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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.lifespan import lifespan
from app.middleware import configure_middleware
from app.router import auth as auth_wiring
from modules.pdf_processing.progress_service import progress_manager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

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
    # We import wiring routers from app.router.* which in turn import module routers
    app.include_router(auth_wiring.router)
    
    # Include PDF processing router (no prefix - proxy handles /api/proxy/...)
    from modules.pdf_processing.router import router as pdf_router
    app.include_router(pdf_router, tags=["PDF Processing"])
    
    # Note: Add other routers here as they are migrated
    # from app.router import simulation as simulation_wiring
    # app.include_router(simulation_wiring.router)

    # 3. Health Check
    @app.get("/health", tags=["System"])
    async def health_check():
        """Health check endpoint with database connectivity test."""
        try:
            # Test database connection
            from common.db.connection import SessionLocal
            db = SessionLocal()
            try:
                db.execute(text("SELECT 1"))
                db_status = "connected"
            except Exception as e:
                logger.warning(f"Database health check failed: {e}")
                db_status = f"error: {str(e)}"
            finally:
                db.close()
            
            return {
                "status": "ok",
                "version": "2.0.0",
                "database": db_status
            }
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return JSONResponse(
                status_code=503,
                content={"status": "degraded", "error": str(e)}
            )

    # 4. WebSocket endpoint for PDF processing progress
    @app.websocket("/ws/pdf-progress/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
        """WebSocket endpoint for real-time PDF processing progress updates"""
        await progress_manager.connect(websocket, session_id)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            progress_manager.disconnect(session_id)

    return app

# Create the app instance for uvicorn
app = create_app()
