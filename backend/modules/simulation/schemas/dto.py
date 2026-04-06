"""
Simulation DTOs (Data Transfer Objects).

Request and response models for simulation endpoints.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


# Request Models

class SimulationStartRequest(BaseModel):
    """Request model for starting a simulation."""
    simulation_id: int


class SimulationChatRequest(BaseModel):
    """Request model for sending a chat message."""
    user_progress_id: int
    message: str
    scene_id: Optional[int] = None
    user_id: Optional[int] = None
    simulation_id: Optional[int] = None
    target_persona_id: Optional[int] = None


class SaveMessageRequest(BaseModel):
    """Request model for saving a system message."""
    user_progress_id: int
    scene_id: int
    sender_name: str
    message_content: str
    message_type: str  # "system", "orchestrator", etc.
    session_id: Optional[str] = None


class CodeExecutionRequest(BaseModel):
    """Request model for executing code in a Daytona sandbox."""
    user_progress_id: int
    code: str
    scene_id: int
    language: str = "python"


class CodeExecutionResponse(BaseModel):
    """Response model for code execution results."""
    success: bool
    output: str
    error: Optional[str] = None
    sandbox_state: Optional[str] = None


class SandboxStateResponse(BaseModel):
    """Response model for sandbox state polling."""
    sandbox_state: str
    sandbox_id: Optional[str] = None


# Response Models

class SimulationPersonaResponse(BaseModel):
    """Response model for simulation persona."""
    id: int
    simulation_id: int
    name: str
    role: str
    background: Optional[str] = None
    correlation: Optional[str] = None
    primary_goals: List[str] = []
    personality_traits: Dict[str, Any] = {}
    image_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SimulationSceneResponse(BaseModel):
    """Response model for simulation scene."""
    id: int
    simulation_id: int
    title: str
    description: str
    user_goal: Optional[str] = None
    scene_order: int
    estimated_duration: Optional[int] = None
    image_url: Optional[str] = None
    image_prompt: Optional[str] = None
    timeout_turns: Optional[int] = None
    success_metric: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    personas_involved: Optional[List[str]] = None
    personas: List[SimulationPersonaResponse] = []


class SimulationStartResponse(BaseModel):
    """Response model for starting a simulation."""
    user_progress_id: int
    simulation: Dict[str, Any]
    current_scene: Dict[str, Any]
    simulation_status: str
    conversation_history: List[Dict[str, Any]] = []
    is_resuming: bool = False
    all_scenes: List[Dict[str, Any]] = []
    turn_count: Optional[int] = 0
    completed_scene_ids: Optional[List[int]] = []
    sandbox_id: Optional[str] = None


class SimulationChatResponse(BaseModel):
    """Response model for chat message."""
    message: Optional[str] = None
    scene_id: Optional[int] = None
    scene_completed: bool = False
    next_scene_id: Optional[int] = None
    persona_name: Optional[str] = None
    persona_id: Optional[int] = None
    turn_count: int = 0
    scene_intro_message: Optional[str] = None
    simulation_complete: Optional[bool] = None
    next_scene: Optional[Dict[str, Any]] = None
    
    # Legacy fields for compatibility
    message_id: Optional[int] = None
    persona_response: Optional[str] = None
    message_order: Optional[int] = None
    processing_time: Optional[float] = None
    ai_model_version: Optional[str] = None


class UserProgressResponse(BaseModel):
    """Response model for user progress."""
    id: int
    user_id: int
    simulation_id: int
    current_scene_id: Optional[int] = None
    simulation_status: str
    scenes_completed: List[int] = []
    total_attempts: int = 0
    hints_used: int = 0
    forced_progressions: int = 0
    completion_percentage: float = 0.0
    total_time_spent: Optional[int] = None
    session_count: int = 0
    final_score: Optional[float] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None


class SceneProgressResponse(BaseModel):
    """Response model for scene progress."""
    id: int
    scene_id: int
    status: str
    attempts: int = 0
    hints_used: int = 0
    goal_achieved: Optional[bool] = None
    forced_progression: Optional[bool] = None
    time_spent: Optional[int] = None
    messages_sent: int = 0
    ai_responses: int = 0
    goal_achievement_score: Optional[float] = None
    interaction_quality: Optional[float] = None
    scene_feedback: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    success: bool = True
    next_scene: Optional[Dict[str, Any]] = None
    simulation_complete: bool = False
    completion_summary: Optional[str] = None
