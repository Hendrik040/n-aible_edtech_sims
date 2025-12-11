"""
Publishing DTOs (Data Transfer Objects).

Request and response models for publishing endpoints.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class SimulationPublishRequest(BaseModel):
    """Request model for publishing a simulation."""
    pass  # No additional fields needed for publishing


class SimulationPublishingResponse(BaseModel):
    """Response model for simulation publishing data."""
    id: int
    title: str
    description: str
    challenge: Optional[str] = None
    industry: Optional[str] = None
    learning_objectives: Optional[List[str]] = None
    student_role: Optional[str] = None
    pdf_title: Optional[str] = None
    pdf_source: Optional[str] = None
    processing_version: Optional[str] = None
    source_type: Optional[str] = None
    is_public: bool = False
    is_template: bool = False
    allow_remixes: bool = True
    usage_count: int = 0
    clone_count: int = 0
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    status: str = "draft"
    is_draft: bool = True
    personas: List[Dict[str, Any]] = []
    scenes: List[Dict[str, Any]] = []
    completion_status: Optional[Dict[str, Any]] = None
    name_completed: bool = False
    description_completed: bool = False
    student_role_completed: bool = False
    personas_completed: bool = False
    scenes_completed: bool = False
    images_completed: bool = False
    learning_outcomes_completed: bool = False
    ai_enhancement_completed: bool = False

    class Config:
        from_attributes = True


class PublishResponse(BaseModel):
    """Response model for publish operation."""
    status: str
    simulation_id: int
    message: str


class SaveResponse(BaseModel):
    """Response model for save operation."""
    status: str
    simulation_id: int
    message: str


class StatusUpdateRequest(BaseModel):
    """Request model for updating simulation status."""
    status: str = Field(..., pattern="^(draft|active|archived|creating)$")


class CloneResponse(BaseModel):
    """Response model for clone operation."""
    status: str
    simulation_id: int
    cloned_from_id: int
    message: str


class CleanupStatsResponse(BaseModel):
    """Response model for cleanup statistics."""
    temp_pdfs_deleted: int
    archives_cleaned: int
    total_space_freed_mb: Optional[float] = None


class ImageUploadStatusResponse(BaseModel):
    """Response model for image upload status."""
    status: str  # 'pending', 'uploading', 'completed', 'failed'
    completed: int
    total: int
    pending: int = 0
    failed: List[Dict[str, Any]] = []
