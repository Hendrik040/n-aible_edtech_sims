"""
Application Entry Point

This file acts as the wiring layer for the application:
- Creates the FastAPI app instance
- Configures middleware
- Registers routers
- Defines lifecycle hooks
"""

import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from app.lifespan import lifespan
from app.middleware import configure_middleware
from app.router import auth as auth_wiring
from modules.pdf_processing.progress_service import progress_manager

# Setup logging
logging.basicConfig(level=logging.INFO)
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

    # 1. Configure Middleware (CORS, etc.)
    configure_middleware(app)

    # 2. Register Routers
    # We import wiring routers from app.router.* which in turn import module routers
    app.include_router(auth_wiring.router)
    
    # Note: Add other routers here as they are migrated
    # from app.router import simulation as simulation_wiring
    # app.include_router(simulation_wiring.router)

    # 3. Health Check
    @app.get("/health", tags=["System"])
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok", "version": "2.0.0"}

    # 4. WebSocket endpoint for PDF processing progress
    @app.websocket("/ws/pdf-progress/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
        """WebSocket endpoint for real-time PDF processing progress updates"""
        await progress_manager.connect(session_id, websocket)  # Fixed: correct argument order
        try:
            while True:
                # Keep connection alive and wait for client messages
                await websocket.receive_text()  # Removed unused 'data' variable
                # Echo back if needed, but main purpose is progress updates from server
        except WebSocketDisconnect:
            progress_manager.disconnect(session_id)

    return app

# Create the app instance for uvicorn
app = create_app()
