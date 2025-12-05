"""
Pydantic schemas for PDF processing module.
"""
from pydantic import BaseModel, ConfigDict, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime


class PersonalityTraitsSchema(BaseModel):
    """Personality traits for a persona (0-10 scale)"""
    analytical: Optional[int] = Field(None, ge=0, le=10)
    creative: Optional[int] = Field(None, ge=0, le=10)
    assertive: Optional[int] = Field(None, ge=0, le=10)
    collaborative: Optional[int] = Field(None, ge=0, le=10)
    detail_oriented: Optional[int] = Field(None, ge=0, le=10)
    risk_taking: Optional[int] = Field(None, ge=0, le=10)
    empathetic: Optional[int] = Field(None, ge=0, le=10)
    decisive: Optional[int] = Field(None, ge=0, le=10)


class PersonaSchema(BaseModel):
    """Schema for a persona extracted from PDF"""
    name: str
    role: str
    background: Optional[str] = None
    correlation: Optional[str] = None
    primary_goals: Optional[List[str]] = None
    personality_traits: Optional[Dict[str, int]] = None
    image_url: Optional[str] = None


class SceneSchema(BaseModel):
    """Schema for a scene extracted from PDF"""
    title: str
    description: str
    user_goal: Optional[str] = None
    scene_order: int = 0
    sequence_order: Optional[int] = None  # Alias for scene_order
    image_url: Optional[str] = None
    image_prompt: Optional[str] = None
    timeout_turns: Optional[int] = 15
    success_metric: Optional[str] = None
    personas_involved: Optional[List[str]] = None


class PDFMetadataSchema(BaseModel):
    """Schema for PDF metadata"""
    filename: str
    file_size: int
    file_type: str
    file_contents_base64: Optional[str] = None  # For small files
    temp_pdf_url: Optional[str] = None  # For large files (temp storage)
    wasabi_url: Optional[str] = None  # For final storage


class PreprocessedContent(BaseModel):
    """Schema for preprocessed PDF content"""
    title: str
    cleaned_content: str


class AIExtractionResult(BaseModel):
    """Result from AI extraction of PDF content"""
    title: str
    description: str
    student_role: str
    key_figures: List[PersonaSchema]
    scenes: Optional[List[SceneSchema]] = None
    learning_outcomes: Optional[List[str]] = None
    pdf_metadata: Optional[PDFMetadataSchema] = None


class FastAutofillRequest(BaseModel):
    """Request for fast autofill (personas only)"""
    file: Any  # UploadFile
    
    model_config = ConfigDict(arbitrary_types_allowed=True)


class FastAutofillResponse(BaseModel):
    """Response from fast autofill endpoint"""
    status: str = "fast_autofill_completed"
    processing_time: float
    simulation_id: Optional[int] = None
    title: str
    student_role: str
    personas: List[PersonaSchema]
    key_figures: List[PersonaSchema]


class ParsePDFRequest(BaseModel):
    """Request for full PDF parsing with progress"""
    file: Any  # UploadFile
    context_files: Optional[List[Any]] = None
    save_to_db: bool = False
    session_id: Optional[str] = None
    
    model_config = ConfigDict(arbitrary_types_allowed=True)


class ParsePDFResponse(BaseModel):
    """Response from PDF parsing"""
    success: bool
    data: AIExtractionResult
    session_id: Optional[str] = None
    simulation_id: Optional[int] = None
    message: str


class ProgressUpdate(BaseModel):
    """Progress update for PDF processing"""
    type: str  # "progress_update", "field_update", "completion", "error"
    session_id: str
    overall_progress: Optional[int] = None
    current_stage: Optional[str] = None
    stage_progress: Optional[int] = None
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    timestamp: float
    # Field update specific
    field_name: Optional[str] = None
    field_value: Optional[Any] = None
    # Completion/error specific
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ProgressStatusResponse(BaseModel):
    """Response for progress status check"""
    overall_progress: int
    current_stage: str
    stage_progress: int
    message: str
    timestamp: float
    completed: bool = False
    error: Optional[str] = None
    field_updates: Dict[str, Any] = {}
    simulation_id: Optional[int] = None
    result: Optional[Dict[str, Any]] = None


class HealthCheckResponse(BaseModel):
    """Health check response for LlamaParse"""
    status: str  # "healthy", "error"
    message: str
    details: Optional[str] = None
    api_key_length: Optional[int] = None
    api_response_status: Optional[int] = None


class DefaultPersonasResponse(BaseModel):
    """Response for default personas endpoint"""
    status: str = "instant_fallback"
    processing_time: float = 0.001
    title: str = "Business Case Study"
    student_role: str = "Business Manager"
    personas: List[PersonaSchema]
    key_figures: List[PersonaSchema]
