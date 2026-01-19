"""
Progress tracking service for PDF processing with WebSocket support.
Extracted from api/pdf_progress.py
"""
import asyncio
import json
import time
from typing import Dict, Any, Optional
from fastapi import WebSocket
import logging

from common.services.cache_service import redis_manager

logger = logging.getLogger(__name__)

# Redis key prefix for progress sessions
PROGRESS_KEY_PREFIX = "pdf_progress"
# TTL for progress sessions: 1 hour (3600 seconds)
PROGRESS_TTL = 3600


class ProgressManager:
    """Manages WebSocket connections and progress updates for PDF parsing"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        # Using Redis for shared storage across replicas
        logger.info("PDF Progress Manager: Using Redis for shared session storage")
    
    def _get_redis_key(self, session_id: str) -> str:
        """Get Redis key for a session"""
        return f"{PROGRESS_KEY_PREFIX}:{session_id}"
    
    def _load_progress_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load progress data from Redis"""
        
        # #endregion
        key = self._get_redis_key(session_id)
        data = redis_manager.get(key)
        # #region agent log
        # #endregion
        return data
    
    def _save_progress_data(self, session_id: str, data: Dict[str, Any]) -> bool:
        """Save progress data to Redis"""

        # #endregion
        key = self._get_redis_key(session_id)
        return redis_manager.set(key, data, ttl=PROGRESS_TTL)
    
    async def connect(self, websocket: WebSocket, session_id: str):
        """Accept a WebSocket connection and store it"""

        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket connected for session: {session_id}")
    
    def disconnect(self, session_id: str):
        """Remove a WebSocket connection"""

        if session_id in self.active_connections:
            del self.active_connections[session_id]

        # Note: We don't delete Redis data on disconnect - let it expire via TTL
        # This allows HTTP polling to continue working even after WebSocket disconnects
        logger.info(f"WebSocket disconnected for session: {session_id}")
    
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
        
        # Load existing progress data from Redis
        progress_info = self._load_progress_data(session_id)
        
        # Initialize session if it doesn't exist
        if progress_info is None:
            logger.info(f"[PROGRESS_MANAGER] Creating new session: {session_id}")
            progress_info = {
                "overall_progress": 0,
                "current_stage": "",
                "stages": {},
                "start_time": time.time(),
                "last_update": time.time()
            }
        else:
            logger.info(f"[PROGRESS_MANAGER] Updating existing session: {session_id}")
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
        
        # Save updated progress data to Redis
        self._save_progress_data(session_id, progress_info)
        
        # Create overall message based on current stage and progress
        overall_message = self._get_overall_message(stage, progress, message)
        
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
        progress_info = self._load_progress_data(session_id)
        if progress_info:
            progress_info["overall_progress"] = 100
            progress_info["completed"] = True
            progress_info["completion_time"] = time.time()
            if result:
                progress_info["result"] = result
            
            # Save updated progress data to Redis
            self._save_progress_data(session_id, progress_info)
            
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
        progress_info = self._load_progress_data(session_id)
        if progress_info:
            if "field_updates" not in progress_info:
                progress_info["field_updates"] = {}
            progress_info["field_updates"][field_name] = field_value
            self._save_progress_data(session_id, progress_info)
        
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
        progress_info = self._load_progress_data(session_id)
        if progress_info:
            progress_info["error"] = error_message
            progress_info["failed"] = True
            self._save_progress_data(session_id, progress_info)
        else:
            # Create a minimal error entry if session doesn't exist
            progress_info = {
                "error": error_message,
                "failed": True,
                "overall_progress": 0,
                "current_stage": "",
                "stages": {},
                "start_time": time.time(),
                "last_update": time.time()
            }
            self._save_progress_data(session_id, progress_info)
        
        # Send error message
        asyncio.create_task(self.send_progress(session_id, {
            "type": "error",
            "session_id": session_id,
            "error": error_message,
            "timestamp": time.time()
        }))
    
    def get_progress_status(self, session_id: str) -> Dict[str, Any]:
        """Get current progress status for a session"""
        logger.info(f"[PROGRESS_API] Getting progress for session: {session_id}")
        
        # Load from Redis (shared across all replicas)
        progress_data = self._load_progress_data(session_id)

        # Format response for HTTP polling (not WebSocket)
        response_data = {
            "overall_progress": progress_data.get("overall_progress", 0),
            "current_stage": progress_data.get("current_stage", "upload"),
            "stage_progress": 0,
            "message": progress_data.get("message", "Processing..."),
            "timestamp": progress_data.get("last_update", time.time()),
            "completed": progress_data.get("completed", False),
            "error": progress_data.get("error"),
            "field_updates": progress_data.get("field_updates", {}),
            "simulation_id": progress_data.get("simulation_id"),
            "result": progress_data.get("result")
        }
        
        # Calculate stage progress
        if progress_data.get("stages") and progress_data.get("current_stage"):
            current_stage = progress_data.get("current_stage")
            if current_stage in progress_data["stages"]:
                response_data["stage_progress"] = progress_data["stages"][current_stage].get("progress", 0)
        
        return response_data
    
    def set_simulation_id(self, session_id: str, simulation_id: int):
        """Set simulation_id in progress data"""
        progress_info = self._load_progress_data(session_id)
        if progress_info:
            progress_info["simulation_id"] = simulation_id
            self._save_progress_data(session_id, progress_info)
        else:
            # Create minimal entry if session doesn't exist
            progress_info = {
                "simulation_id": simulation_id,
                "overall_progress": 0,
                "current_stage": "",
                "stages": {},
                "start_time": time.time(),
                "last_update": time.time()
            }
            self._save_progress_data(session_id, progress_info)
    
    def reset_progress(self, session_id: str):
        """Reset progress for a session"""
        key = self._get_redis_key(session_id)
        redis_manager.delete(key)


# Global progress manager instance
progress_manager = ProgressManager()

