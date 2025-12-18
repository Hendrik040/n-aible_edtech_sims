"""
Progress tracking service for PDF processing with WebSocket support.
Extracted from api/pdf_progress.py
"""
import asyncio
import json
import time
from typing import Dict, Any
from fastapi import WebSocket
import logging

logger = logging.getLogger(__name__)


class ProgressManager:
    """Manages WebSocket connections and progress updates for PDF parsing"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.progress_data: Dict[str, Dict[str, Any]] = {}
        # Using in-memory storage only (no Redis dependency)
        logger.info("PDF Progress Manager: Using in-memory storage")
    
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
        
        # Initialize session if it doesn't exist
        if session_id not in self.progress_data:
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
        logger.info(f"[PROGRESS_API] Available sessions: {list(self.progress_data.keys())}")
        
        # Check in-memory storage
        if session_id in self.progress_data:
            logger.info(f"[PROGRESS_API] Found session in memory: {session_id}")
            progress_data = self.progress_data[session_id].copy()
        else:
            logger.warning(f"[PROGRESS_API] Session not found: {session_id}")
            return None
        
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
    
    def reset_progress(self, session_id: str):
        """Reset progress for a session"""
        if session_id in self.progress_data:
            del self.progress_data[session_id]


# Global progress manager instance
progress_manager = ProgressManager()

