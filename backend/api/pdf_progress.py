"""
PDF Parsing Progress Tracking with WebSockets
Provides real-time progress updates for PDF parsing operations
"""

import asyncio
import json
import time
from typing import Dict, Any
from fastapi import WebSocket, WebSocketDisconnect, HTTPException
from fastapi.routing import APIRouter
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

class ProgressManager:
    """Manages WebSocket connections and progress updates for PDF parsing"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.progress_data: Dict[str, Dict[str, Any]] = {}
        # Initialize Redis for persistent session storage
        try:
            from utilities.redis_manager import redis_manager
            self.redis = redis_manager
            self.use_redis = redis_manager.is_available()
            logger.info(f"PDF Progress Manager: Redis {'enabled' if self.use_redis else 'disabled'}")
        except Exception as e:
            logger.warning(f"PDF Progress Manager: Redis not available: {e}")
            self.redis = None
            self.use_redis = False
    
    async def connect(self, websocket: WebSocket, session_id: str):
        """Accept a WebSocket connection and store it"""
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket connected for session: {session_id}")
    
    def disconnect(self, session_id: str):
        """Remove a WebSocket connection"""
        if session_id in self.active_connections:
            del self.active_connections[session_id]
        if session_id in self.progress_data:
            del self.progress_data[session_id]
        # Also remove from Redis
        if self.use_redis:
            try:
                self.redis.delete(f"pdf_progress:{session_id}")
            except Exception as e:
                logger.warning(f"Failed to remove session from Redis: {e}")
        logger.info(f"WebSocket disconnected for session: {session_id}")
    
    def _get_redis_key(self, session_id: str) -> str:
        """Get Redis key for session"""
        return f"pdf_progress:{session_id}"
    
    def _store_progress_data(self, session_id: str, data: Dict[str, Any]):
        """Store progress data in Redis if available"""
        if self.use_redis:
            try:
                # Store with 1 hour expiration
                self.redis.setex(
                    self._get_redis_key(session_id),
                    3600,  # 1 hour TTL
                    json.dumps(data)
                )
            except Exception as e:
                logger.warning(f"Failed to store progress data in Redis: {e}")
    
    def _get_progress_data(self, session_id: str) -> Dict[str, Any]:
        """Get progress data from Redis if available"""
        if self.use_redis:
            try:
                data = self.redis.get(self._get_redis_key(session_id))
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.warning(f"Failed to get progress data from Redis: {e}")
        return None
    
    async def send_progress(self, session_id: str, progress_data: Dict[str, Any]):
        """Send progress update to a specific session"""
        if session_id in self.active_connections:
            try:
                websocket = self.active_connections[session_id]
                await websocket.send_text(json.dumps(progress_data))
                logger.debug(f"Sent progress update to {session_id}: {progress_data}")
            except Exception as e:
                logger.error(f"Failed to send progress to {session_id}: {e}")
                self.disconnect(session_id)
    
    def update_progress(self, session_id: str, stage: str, progress: int, message: str = "", details: Dict[str, Any] = None):
        """Update progress data for a session"""
        logger.info(f"[PROGRESS_MANAGER] Updating progress for session: {session_id}")
        
        # Try to get existing data from Redis first
        if session_id not in self.progress_data:
            redis_data = self._get_progress_data(session_id)
            if redis_data:
                logger.info(f"[PROGRESS_MANAGER] Restored session from Redis: {session_id}")
                self.progress_data[session_id] = redis_data
            else:
                logger.info(f"[PROGRESS_MANAGER] Creating new session: {session_id}")
                self.progress_data[session_id] = {
                    "overall_progress": 0,
                    "current_stage": "",
                    "stages": {},
                    "start_time": time.time(),
                    "last_update": time.time()
                }
        else:
            logger.info(f"[PROGRESS_MANAGER] Updating existing session: {session_id}")
        
        progress_info = self.progress_data[session_id]
        progress_info["current_stage"] = stage
        progress_info["stages"][stage] = {
            "progress": progress,
            "message": message,
            "details": details or {},
            "timestamp": time.time()
        }
        progress_info["last_update"] = time.time()
        
        # Calculate overall progress based on stage weights
        stage_weights = {
            "upload": 20,  # Upload is 20% of total progress
            "processing": 80,  # Processing is 80% of total progress
            # Removed ai_analysis stage
        }
        
        total_weighted_progress = 0
        total_weight = 0
        
        for stage_name, weight in stage_weights.items():
            if stage_name in progress_info["stages"]:
                stage_progress = progress_info["stages"][stage_name]["progress"]
                total_weighted_progress += stage_progress * weight
                total_weight += weight
        
        if total_weight > 0:
            calculated_progress = int(total_weighted_progress / total_weight)
            # Don't show 100% until processing stage is complete
            if stage == "processing" and progress < 100:
                progress_info["overall_progress"] = min(calculated_progress, 95)
            else:
                progress_info["overall_progress"] = calculated_progress
        
        # Create overall message based on current stage and progress
        overall_message = self._get_overall_message(stage, progress, message)
        
        # Store progress data in Redis for persistence
        self._store_progress_data(session_id, progress_info)
        
        # Send update to frontend
        asyncio.create_task(self.send_progress(session_id, {
            "type": "progress_update",
            "session_id": session_id,
            "overall_progress": progress_info["overall_progress"],
            "current_stage": stage,
            "stage_progress": progress,
            "message": overall_message,  # Use overall message instead of stage-specific message
            "details": details or {},
            "timestamp": time.time()
        }))
    
    def _get_overall_message(self, stage: str, progress: int, stage_message: str) -> str:
        """Create an overall progress message that describes the entire PDF processing status"""
        if stage == "upload":
            if progress < 50:
                return "Reading and uploading PDF file..."
            elif progress < 100:
                return "Uploading PDF to processing service..."
            else:
                return "PDF uploaded successfully, starting analysis..."
        
        elif stage == "processing":
            if progress < 20:
                return "Analyzing document structure and content..."
            elif progress < 40:
                return "Extracting key information from document..."
            elif progress < 60:
                return "Identifying personas and roles..."
            elif progress < 80:
                return "Generating scenes and learning outcomes..."
            elif progress < 100:
                return "Finalizing analysis and preparing results..."
            else:
                return "PDF analysis complete, updating form fields..."
        
        else:
            return stage_message or "Processing PDF..."
    
    def complete_processing(self, session_id: str, result: Dict[str, Any] = None):
        """Mark processing as complete"""
        if session_id in self.progress_data:
            progress_info = self.progress_data[session_id]
            progress_info["overall_progress"] = 100
            progress_info["completed"] = True
            progress_info["completion_time"] = time.time()
            
            # Store completion in Redis
            self._store_progress_data(session_id, progress_info)
            
            # Send completion message
            asyncio.create_task(self.send_progress(session_id, {
                "type": "completion",
                "session_id": session_id,
                "overall_progress": 100,
                "result": result or {},
                "timestamp": time.time()
            }))
    
    def send_field_update(self, session_id: str, field_name: str, field_value: any, message: str):
        """Send real-time field update to frontend"""
        # Store field update in progress data for HTTP polling
        if session_id in self.progress_data:
            if "field_updates" not in self.progress_data[session_id]:
                self.progress_data[session_id]["field_updates"] = {}
            self.progress_data[session_id]["field_updates"][field_name] = field_value
            
            # Store updated progress data in Redis
            self._store_progress_data(session_id, self.progress_data[session_id])
        
        # Also try to send via WebSocket if available
        asyncio.create_task(self.send_progress(session_id, {
            "type": "field_update",
            "session_id": session_id,
            "field_name": field_name,
            "field_value": field_value,
            "message": message,
            "timestamp": time.time()
        }))
    
    def error_processing(self, session_id: str, error_message: str):
        """Mark processing as failed"""
        if session_id in self.progress_data:
            progress_info = self.progress_data[session_id]
            progress_info["error"] = error_message
            progress_info["failed"] = True
            
            # Store error state in Redis
            self._store_progress_data(session_id, progress_info)
            
            # Send error message
            asyncio.create_task(self.send_progress(session_id, {
                "type": "error",
                "session_id": session_id,
                "error": error_message,
                "timestamp": time.time()
            }))

# Global progress manager instance
progress_manager = ProgressManager()

# WebSocket endpoint moved to main.py to avoid router conflicts

@router.get("/pdf-progress/{session_id}")
async def get_progress_status(session_id: str):
    """Get current progress status for a session"""
    logger.info(f"[PROGRESS_API] Getting progress for session: {session_id}")
    logger.info(f"[PROGRESS_API] Available sessions: {list(progress_manager.progress_data.keys())}")
    
    # Check in-memory first
    if session_id in progress_manager.progress_data:
        logger.info(f"[PROGRESS_API] Found session in memory: {session_id}")
        return progress_manager.progress_data[session_id]
    
    # If not in memory, try Redis
    if progress_manager.use_redis:
        redis_data = progress_manager._get_progress_data(session_id)
        if redis_data:
            logger.info(f"[PROGRESS_API] Found session in Redis: {session_id}")
            # Restore to memory for faster future access
            progress_manager.progress_data[session_id] = redis_data
            return redis_data
    
    logger.warning(f"[PROGRESS_API] Session not found: {session_id}")
    raise HTTPException(status_code=404, detail="Session not found")

@router.post("/pdf-progress/{session_id}/reset")
async def reset_progress(session_id: str):
    """Reset progress for a session"""
    if session_id in progress_manager.progress_data:
        del progress_manager.progress_data[session_id]
    return {"message": "Progress reset successfully"}

