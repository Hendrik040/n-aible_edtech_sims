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
    # We import wiring routers from app.routers.* which in turn import module routers
    app.include_router(auth_wiring.router)
    app.include_router(pdf_processing_wiring.router)
    app.include_router(publishing_wiring.router)
    app.include_router(professor_wiring.router)
    app.include_router(invites_router.router)
    
    # Include professor and student routers
    from modules.professor.router import router as professor_router
    from modules.student.router import router as student_router
    app.include_router(professor_router)
    app.include_router(student_router)
    
    # Note: Add other routers here as they are migrated
    # from app.routers import simulation as simulation_wiring
    # app.include_router(simulation_wiring.router)

    # 3. Health Check
    @app.get("/health", tags=["System"])
    async def health_check():
        """Health check endpoint with database connectivity test."""
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

    return app

# Create the app instance for uvicorn
app = create_app()
