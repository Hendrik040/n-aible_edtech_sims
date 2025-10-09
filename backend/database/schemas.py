# Enhanced Pydantic Schemas for CrewAI Agent Builder Platform
from pydantic import BaseModel, conint, validator, model_validator
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime

# --- SCENARIO SCHEMAS ---
class ScenarioCreate(BaseModel):
    title: str
    description: str
    industry: str
    challenge: str
    learning_objectives: List[str]
    source_type: str = "manual"
    pdf_content: Optional[str] = None
    is_public: bool = False
    is_template: bool = False
    allow_remixes: bool = True

class ScenarioResponse(BaseModel):
    id: int
    title: str
    description: str
    industry: Optional[str] = None
    challenge: str
    learning_objectives: List[str]
    source_type: str
    pdf_content: Optional[str] = None
    is_public: bool
    is_template: bool
    allow_remixes: bool
    status: str  # draft, active, archived
    is_draft: bool  # True for draft, False for published
    published_version_id: Optional[int]  # Reference to published version
    draft_of_id: Optional[int]  # Reference to original if this is a draft
    usage_count: int
    clone_count: int
    created_by: Optional[int]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class ScenarioUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    industry: Optional[str] = None
    challenge: Optional[str] = None
    learning_objectives: Optional[List[str]] = None
    student_role: Optional[str] = None
    category: Optional[str] = None
    difficulty_level: Optional[str] = None
    estimated_duration: Optional[int] = None
    tags: Optional[List[str]] = None
    is_public: Optional[bool] = None
    allow_remixes: Optional[bool] = None

# --- PDF-TO-SCENARIO PUBLISHING SCHEMAS ---

# Define trait type with validation
Trait = conint(ge=0, le=10)

class PersonalityTraits(BaseModel):
    analytical: Optional[Trait] = None  # 0-10 scale
    creative: Optional[Trait] = None    # 0-10 scale
    assertive: Optional[Trait] = None   # 0-10 scale
    collaborative: Optional[Trait] = None  # 0-10 scale
    detail_oriented: Optional[Trait] = None  # 0-10 scale
    risk_taking: Optional[Trait] = None  # 0-10 scale
    empathetic: Optional[Trait] = None   # 0-10 scale
    decisive: Optional[Trait] = None     # 0-10 scale

class ScenarioPersonaCreate(BaseModel):
    name: str
    role: str
    background: Optional[str] = None
    correlation: Optional[str] = None
    primary_goals: Optional[List[str]] = None
    personality_traits: Optional[PersonalityTraits] = None

class ScenarioPersonaResponse(BaseModel):
    id: int
    scenario_id: Optional[int] = None
    name: str
    role: str
    background: Optional[str] = None
    correlation: Optional[str] = None
    primary_goals: Optional[List[str]] = None
    personality_traits: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    @validator('primary_goals', pre=True)
    def convert_primary_goals(cls, v):
        """Convert string primary_goals to list"""
        if isinstance(v, str):
            # Split by bullet points or newlines
            goals = [g.strip().lstrip('•').strip() for g in v.split('\n') if g.strip()]
            return [g for g in goals if g]  # Remove empty strings
        return v
    
    class Config:
        from_attributes = True

class ScenarioSceneCreate(BaseModel):
    title: str
    description: str
    user_goal: Optional[str] = None
    scene_order: int = 0
    estimated_duration: Optional[int] = None
    image_url: Optional[str] = None
    image_prompt: Optional[str] = None
    # New fields
    timeout_turns: Optional[int] = None
    success_metric: Optional[str] = None
    persona_ids: Optional[List[int]] = None  # IDs of personas involved

class ScenarioSceneResponse(BaseModel):
    id: int
    scenario_id: Optional[int] = None
    title: str
    description: str
    user_goal: Optional[str] = None
    scene_order: int
    estimated_duration: Optional[int] = None
    image_url: Optional[str] = None
    image_prompt: Optional[str] = None
    # New fields
    timeout_turns: Optional[int] = None
    success_metric: Optional[str] = None
    personas_involved: Optional[List[str]] = None  # Add personas_involved field
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    personas: Optional[List[ScenarioPersonaResponse]] = None
    
    class Config:
        from_attributes = True

class ScenarioFileResponse(BaseModel):
    id: int
    scenario_id: int
    filename: str
    file_size: Optional[int]
    file_type: str
    processing_status: str
    uploaded_at: datetime
    processed_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class ScenarioReviewCreate(BaseModel):
    rating: int
    review_text: Optional[str] = None
    pros: Optional[List[str]] = None
    cons: Optional[List[str]] = None
    use_case: Optional[str] = None

class ScenarioReviewResponse(BaseModel):
    id: int
    scenario_id: int
    reviewer_id: int
    rating: int
    review_text: Optional[str]
    pros: Optional[List[str]]
    cons: Optional[List[str]]
    use_case: Optional[str]
    helpful_votes: int
    total_votes: int
    created_at: datetime
    reviewer: Optional[Dict[str, Any]] = None  # Basic user info
    
    class Config:
        from_attributes = True

# Enhanced scenario response with publishing data
class ScenarioPublishingResponse(BaseModel):
    id: int
    title: str
    description: str
    challenge: str
    industry: str
    learning_objectives: List[str]
    student_role: Optional[str]
    category: Optional[str]
    difficulty_level: Optional[str]
    estimated_duration: Optional[int]
    tags: Optional[List[str]]
    pdf_title: Optional[str]
    pdf_source: Optional[str]
    processing_version: str
    rating_avg: float
    rating_count: int
    source_type: str
    is_public: bool
    is_template: bool
    allow_remixes: bool
    usage_count: int
    clone_count: int
    created_by: Optional[int]
    created_at: datetime
    updated_at: datetime
    
    status: Literal["draft", "active", "archived"]

    @property
    def is_draft(self) -> bool:
        """Computed property to check if scenario is a draft"""
        return self.status == "draft"
    
    # Related data
    personas: Optional[List[ScenarioPersonaResponse]] = None
    scenes: Optional[List[ScenarioSceneResponse]] = None
    files: Optional[List[ScenarioFileResponse]] = None
    reviews: Optional[List[ScenarioReviewResponse]] = None
    creator: Optional[Dict[str, Any]] = None  # Basic user info
    completion_status: Optional[Dict[str, Any]] = None  # Completion tracking for simulation builder
    
    # Database boolean fields for completion tracking
    name_completed: Optional[bool] = None
    description_completed: Optional[bool] = None
    student_role_completed: Optional[bool] = None
    personas_completed: Optional[bool] = None
    scenes_completed: Optional[bool] = None
    images_completed: Optional[bool] = None
    learning_outcomes_completed: Optional[bool] = None
    ai_enhancement_completed: Optional[bool] = None
    grading_config_completed: Optional[bool] = None
    
    # Grading configuration for AI grading agent
    grading_config: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True

# Publishing workflow schemas
class ScenarioPublishRequest(BaseModel):
    category: str
    difficulty_level: str
    tags: Optional[List[str]] = None
    estimated_duration: Optional[int] = None

class MarketplaceFilters(BaseModel):
    category: Optional[str] = None
    difficulty_level: Optional[str] = None
    tags: Optional[List[str]] = None
    min_rating: Optional[float] = None
    search: Optional[str] = None
    page: int = 1
    page_size: int = 20

class MarketplaceResponse(BaseModel):
    scenarios: List[ScenarioPublishingResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

# AI Processing result schema (from parse_pdf)
class AIProcessingResult(BaseModel):
    title: str
    description: str
    student_role: str
    key_figures: List[Dict[str, Any]]  # Personas from AI
    scenes: List[Dict[str, Any]]       # Scenes from AI
    learning_outcomes: List[str]

# --- SIMULATION SCHEMAS (Dynamic Crew Assembly) ---
class DynamicSimulationCreate(BaseModel):
    scenario_id: int
    selected_agent_ids: List[int]  # Agents chosen for this simulation
    agent_role_assignments: Optional[Dict[int, str]] = None  # Map agent_id -> role (e.g., {1: "marketing", 2: "finance"})
    process_type: str = "sequential"  # sequential, hierarchical, collaborative

class SimulationCreate(BaseModel):
    scenario_id: int
    crew_configuration: Optional[Dict[str, Any]] = None
    process_type: str = "sequential"

class SimulationResponse(BaseModel):
    id: int
    scenario_id: int
    user_id: Optional[int]
    selected_agent_ids: Optional[List[int]]
    agent_role_assignments: Optional[Dict[int, str]]
    process_type: str
    crew_configuration: Optional[Dict[str, Any]]
    status: str
    crew_output: Optional[str]
    execution_log: Optional[Dict[str, Any]]
    error_details: Optional[Dict[str, Any]]
    missing_agents: Optional[List[int]]
    missing_tasks: Optional[List[int]]
    fallback_used: bool
    is_public: bool
    allow_sharing: bool
    started_at: datetime
    completed_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class SimulationFallbackCreate(BaseModel):
    scenario_id: int
    fallback_agents: List[int] = []
    fallback_tasks: List[int] = []
    fallback_strategy: str = "substitute"  # substitute, skip, fail

class SimulationFallbackResponse(BaseModel):
    id: int
    scenario_id: int
    fallback_agents: List[int]
    fallback_tasks: List[int]
    fallback_strategy: str
    created_by: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True



# --- USER SCHEMAS ---
class UserCreate(BaseModel):
    email: str
    full_name: str
    username: str
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str = "user"
    profile_public: bool = True
    allow_contact: bool = True

class UserResponse(BaseModel):
    id: int
    user_id: Optional[str] = None  # Role-based ID (STUD-XXXXX or INSTR-XXXXX)
    email: str
    full_name: str
    username: str
    bio: Optional[str]
    avatar_url: Optional[str]
    role: str
    published_scenarios: int
    total_simulations: int
    reputation_score: float
    profile_public: bool
    allow_contact: bool
    is_active: bool
    is_verified: bool
    provider: str = "password"
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    username: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    profile_public: Optional[bool] = None
    allow_contact: Optional[bool] = None

# --- USER AUTHENTICATION SCHEMAS ---
class UserRegister(BaseModel):
    email: str
    full_name: str
    username: str
    password: str
    role: Literal["student", "professor"]  # Required role selection
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    profile_public: bool = True
    allow_contact: bool = True

class UserLogin(BaseModel):
    email: str
    password: str

class UserLoginResponse(BaseModel):
    access_token: str
    token_type: str = "cookie"  # HttpOnly cookie authentication
    user: UserResponse

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class PasswordReset(BaseModel):
    email: str

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

# OAuth schemas
class GoogleOAuthRequest(BaseModel):
    code: str
    state: Optional[str] = None

class OAuthUserData(BaseModel):
    google_id: str
    email: str
    full_name: str
    avatar_url: Optional[str] = None

class AccountLinkingRequest(BaseModel):
    action: Literal["link", "create_separate"]
    existing_user_id: Optional[int] = None  # Required when action == "link"
    state: str  # OAuth state for verification - server will fetch google_data from this
    role: Optional[Literal["student", "professor"]] = None  # Required when action == "create_separate"
    
    @model_validator(mode='after')
    def validate_required_fields(self):
        if self.action == "link" and self.existing_user_id is None:
            raise ValueError("existing_user_id is required when action == 'link'")
        
        if self.action == "link" and self.existing_user_id is not None and self.existing_user_id <= 0:
            raise ValueError("existing_user_id must be a positive integer")
        
        if self.action == "create_separate" and self.role is None:
            raise ValueError("role is required when action == 'create_separate'")
        
        return self

# --- COLLECTION SCHEMAS ---
class CollectionCreate(BaseModel):
    name: str
    description: str
    agents: List[int] = []
    tools: List[int] = []
    scenarios: List[int] = []
    is_public: bool = False
    tags: List[str] = []

class CollectionResponse(BaseModel):
    id: int
    name: str
    description: str
    agents: Optional[List[int]]
    tools: Optional[List[int]]
    scenarios: Optional[List[int]]
    is_public: bool
    tags: Optional[List[str]]
    created_by: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# --- SEQUENTIAL SIMULATION SYSTEM SCHEMAS ---

class SimulationStartRequest(BaseModel):
    scenario_id: int

class SimulationScenarioResponse(BaseModel):
    id: int
    title: str
    description: str
    challenge: str
    industry: Optional[str] = None
    learning_objectives: List[str]
    student_role: Optional[str] = None
    total_scenes: Optional[int] = None  # Add total scenes count
    
    class Config:
        from_attributes = True

class SimulationStartResponse(BaseModel):
    user_progress_id: int
    scenario: SimulationScenarioResponse
    current_scene: ScenarioSceneResponse
    simulation_status: str
    
    class Config:
        from_attributes = True

class SimulationChatRequest(BaseModel):
    user_progress_id: int
    scene_id: Optional[int] = None
    message: str
    target_persona_id: Optional[int] = None  # Which persona to address

class SimulationChatResponse(BaseModel):
    # Support both formats - regular chat and linear simulation
    message_id: Optional[int] = None
    persona_name: Optional[str] = None
    persona_response: Optional[str] = None
    message_order: Optional[int] = None
    processing_time: Optional[float] = None
    ai_model_version: Optional[str] = None
    
    # Linear simulation format
    message: Optional[str] = None
    scene_id: Optional[int] = None
    scene_completed: Optional[bool] = None
    next_scene_id: Optional[int] = None
    next_scene: Optional[Dict[str, Any]] = None  # Full next scene object for frontend
    persona_id: Optional[int] = None  # Persona ID for @mentions
    scene_intro_message: Optional[str] = None  # Scene introduction message for new scenes
    turn_count: Optional[int] = None  # Current turn count
    
    class Config:
        from_attributes = True

class GoalValidationRequest(BaseModel):
    user_progress_id: int
    scene_id: int
    recent_messages: Optional[List[str]] = None  # Recent conversation context

class GoalValidationResponse(BaseModel):
    goal_achieved: bool
    confidence_score: float
    reasoning: str
    next_action: str  # "continue", "progress", "hint", "force_progress"
    hint_message: Optional[str] = None
    
    class Config:
        from_attributes = True

class SceneProgressRequest(BaseModel):
    user_progress_id: int
    current_scene_id: int
    goal_achieved: bool = False
    forced_progression: bool = False

class SceneProgressResponse(BaseModel):
    success: bool
    next_scene: Optional[ScenarioSceneResponse] = None
    simulation_complete: bool = False
    completion_summary: Optional[str] = None
    
    class Config:
        from_attributes = True

class UserProgressResponse(BaseModel):
    id: int
    user_id: int
    scenario_id: int
    current_scene_id: Optional[int]
    simulation_status: str
    scenes_completed: List[int]
    total_attempts: int
    hints_used: int
    forced_progressions: int
    completion_percentage: float
    total_time_spent: int
    session_count: int
    final_score: Optional[float]
    started_at: datetime
    completed_at: Optional[datetime]
    last_activity: datetime
    
    class Config:
        from_attributes = True

class SceneProgressDetailResponse(BaseModel):
    id: int
    scene_id: int
    status: str
    attempts: int
    hints_used: int
    goal_achieved: bool
    forced_progression: bool
    time_spent: int
    messages_sent: int
    ai_responses: int
    goal_achievement_score: Optional[float]
    interaction_quality: Optional[float]
    scene_feedback: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class ConversationLogResponse(BaseModel):
    id: int
    scene_id: int
    message_type: str
    sender_name: Optional[str]
    persona_id: Optional[int]
    message_content: str
    message_order: int
    attempt_number: int
    is_hint: bool
    timestamp: datetime
    
    class Config:
        from_attributes = True

class SimulationAnalyticsResponse(BaseModel):
    user_progress: UserProgressResponse
    scene_progress: List[SceneProgressDetailResponse]
    conversation_summary: Dict[str, Any]
    performance_metrics: Dict[str, Any]
    
    class Config:
        from_attributes = True

# Enhanced scene response with simulation features
class SimulationSceneResponse(ScenarioSceneResponse):
    goal_criteria: Optional[List[str]] = None
    max_attempts: int
    success_threshold: float
    hint_triggers: Optional[List[str]] = None
    scene_context: Optional[str] = None
    persona_instructions: Optional[Dict[str, str]] = None
    
    class Config:
        from_attributes = True

# --- COHORT SCHEMAS ---

class CohortCreate(BaseModel):
    title: str
    description: Optional[str] = None
    course_code: Optional[str] = None
    semester: Optional[str] = None
    year: Optional[int] = None
    max_students: Optional[int] = None
    auto_approve: bool = True
    allow_self_enrollment: bool = False

class CohortUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    course_code: Optional[str] = None
    semester: Optional[str] = None
    year: Optional[int] = None
    max_students: Optional[int] = None
    auto_approve: Optional[bool] = None
    allow_self_enrollment: Optional[bool] = None
    is_active: Optional[bool] = None

class CohortStudentResponse(BaseModel):
    id: int
    student_id: int
    student_name: str
    student_email: str
    status: str
    enrollment_date: datetime
    approved_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class CohortSimulationResponse(BaseModel):
    id: int
    simulation_id: int
    assigned_by: int
    assigned_at: datetime
    due_date: Optional[datetime]
    is_required: bool
    simulation: Optional[dict] = None
    
    class Config:
        from_attributes = True

class CohortResponse(BaseModel):
    id: int
    unique_id: str
    title: str
    description: Optional[str]
    course_code: Optional[str]
    semester: Optional[str]
    year: Optional[int]
    max_students: Optional[int]
    auto_approve: bool
    allow_self_enrollment: bool
    is_active: bool
    created_by: int
    created_at: datetime
    updated_at: datetime
    students: List[CohortStudentResponse] = []
    simulations: List[CohortSimulationResponse] = []
    
    class Config:
        from_attributes = True

class CohortListResponse(BaseModel):
    id: int
    unique_id: str
    title: str
    description: Optional[str]
    course_code: Optional[str]
    semester: Optional[str]
    year: Optional[int]
    max_students: Optional[int]
    is_active: bool
    created_by: int
    created_at: datetime
    student_count: int = 0
    simulation_count: int = 0
    
    class Config:
        from_attributes = True

class CohortStudentCreate(BaseModel):
    student_id: int
    status: str = "pending"

class CohortStudentUpdate(BaseModel):
    status: str

class CohortSimulationCreate(BaseModel):
    simulation_id: int
    due_date: Optional[datetime] = None
    is_required: bool = True

class CohortSimulationUpdate(BaseModel):
    due_date: Optional[datetime] = None
    is_required: Optional[bool] = None

# --- STUDENT SIMULATION INSTANCE SCHEMAS ---

class StudentSimulationInstanceResponse(BaseModel):
    id: int
    unique_id: str
    cohort_assignment_id: int
    student_id: int
    user_progress_id: Optional[int]
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    submitted_at: Optional[datetime]
    grade: Optional[float]
    feedback: Optional[str]
    graded_by: Optional[int]
    graded_at: Optional[datetime]
    completion_percentage: float
    total_time_spent: int
    attempts_count: int
    hints_used: int
    is_overdue: bool
    days_late: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class StudentSimulationInstanceCreate(BaseModel):
    cohort_assignment_id: int
    student_id: int

class StudentSimulationInstanceUpdate(BaseModel):
    status: Optional[str] = None
    grade: Optional[float] = None
    feedback: Optional[str] = None
    completion_percentage: Optional[float] = None
    total_time_spent: Optional[int] = None
    attempts_count: Optional[int] = None
    hints_used: Optional[int] = None
    is_overdue: Optional[bool] = None
    days_late: Optional[int] = None


# --- INVITATION SYSTEM SCHEMAS ---

class StudentInvitation(BaseModel):
    """Schema for inviting a student to a cohort"""
    email: str
    message: Optional[str] = None

class InvitationResponse(BaseModel):
    """Schema for responding to an invitation"""
    action: Literal["accept", "decline"]

class RoleSelectionRequest(BaseModel):
    """Schema for OAuth role selection"""
    role: Literal["student", "professor"]
    state: str

class CohortInvitationResponse(BaseModel):
    """Response schema for cohort invitations"""
    id: int
    cohort_id: int
    professor_id: int
    student_email: str
    student_id: Optional[int] = None
    status: str
    message: Optional[str] = None
    expires_at: datetime
    created_at: datetime
    cohort: Optional[Dict[str, Any]] = None
    invited_by: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True

class NotificationResponse(BaseModel):
    """Response schema for notifications"""
    id: int
    type: str
    title: str
    message: str
    data: Optional[dict] = None
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

# --- PROFESSOR-STUDENT MESSAGE SCHEMAS ---

class MessageCreate(BaseModel):
    """Schema for creating a new message"""
    recipient_id: int
    cohort_id: Optional[int] = None
    subject: str
    message: str
    message_type: str = "general"

class MessageReply(BaseModel):
    """Schema for replying to a message"""
    message: str

class MessageResponse(BaseModel):
    """Response schema for messages"""
    id: int
    professor_id: int
    student_id: int
    cohort_id: Optional[int]
    subject: str
    message: str
    message_type: str
    parent_message_id: Optional[int]
    is_reply: bool
    professor_read: bool
    student_read: bool
    created_at: datetime
    updated_at: datetime
    
    # Nested data
    professor: Optional[Dict[str, Any]] = None
    student: Optional[Dict[str, Any]] = None
    cohort: Optional[Dict[str, Any]] = None
    replies: List['MessageResponse'] = []
    
    class Config:
        from_attributes = True

class MessageListResponse(BaseModel):
    """Response schema for message lists"""
    id: int
    professor_id: int
    student_id: int
    cohort_id: Optional[int]
    subject: str
    message: str
    message_type: str
    parent_message_id: Optional[int]
    is_reply: bool
    professor_read: bool
    student_read: bool
    created_at: datetime
    updated_at: datetime
    
    # Nested data
    professor: Optional[Dict[str, Any]] = None
    student: Optional[Dict[str, Any]] = None
    cohort: Optional[Dict[str, Any]] = None
    reply_count: int = 0
    
    class Config:
        from_attributes = True

class MessageThreadResponse(BaseModel):
    """Response schema for message threads"""
    parent_message: MessageResponse
    replies: List[MessageResponse] = []

class EmailTemplate(BaseModel):
    """Schema for email templates"""
    email_type: str
    subject: str
    body: str
    variables: Optional[dict] = None
