# AI Agent Education Platform - Database Models
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, JSON, Table, Float, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.connection import Base, settings
import secrets
import string

# Import pgvector if available and configured
try:
    from pgvector.sqlalchemy import Vector
    PGVECTOR_AVAILABLE = True
except ImportError:
    PGVECTOR_AVAILABLE = False
    Vector = None

# Use configuration to determine vector column type
def get_vector_column_type(dimension: int = 1536):
    """Get the appropriate column type based on configuration and dimension"""
    if settings.use_pgvector and PGVECTOR_AVAILABLE:
        return Vector(dimension)
    else:
        return JSON

def generate_cohort_id():
    """Generate a short, user-friendly cohort ID like CH-MAN8P1QS"""
    # Use uppercase letters and numbers for readability
    chars = string.ascii_uppercase + string.digits
    # Generate 8 random characters
    random_part = ''.join(secrets.choice(chars) for _ in range(8))
    return f"CH-{random_part}"

# Junction table for scene-persona relationships
scene_personas = Table(
    'scene_personas',
    Base.metadata,
    Column('scene_id', Integer, ForeignKey('scenario_scenes.id'), primary_key=True),
    Column('persona_id', Integer, ForeignKey('scenario_personas.id'), primary_key=True),
    Column('involvement_level', String, default='participant'),  # key, participant, mentioned
    Column('created_at', DateTime(timezone=True), server_default=func.now())
)

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(15), unique=True, nullable=True, index=True)  # Role-based ID (STUD-XXXXX or INSTR-XXXXX)
    email = Column(String, unique=True, index=True)
    full_name = Column(String)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String, nullable=True)  # Make nullable for OAuth users
    bio = Column(Text, nullable=True)
    avatar_url = Column(String, nullable=True)
    role = Column(String, default="user")  # admin, teacher, professor, student, user
    
    # OAuth fields
    google_id = Column(String, unique=True, nullable=True, index=True)
    provider = Column(String, default="password")  # password, google
    
    # Community stats
    published_scenarios = Column(Integer, default=0)
    total_simulations = Column(Integer, default=0)
    reputation_score = Column(Float, default=0.0)
    
    # Settings
    profile_public = Column(Boolean, default=True)
    allow_contact = Column(Boolean, default=True)
    
    # Account status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    scenarios = relationship("Scenario", back_populates="creator", foreign_keys="Scenario.created_by")
    scenario_reviews = relationship("ScenarioReview", back_populates="reviewer")
    user_progress = relationship("UserProgress", back_populates="user")
    created_cohorts = relationship("Cohort", back_populates="creator")
    
    # Invitation and notification relationships
    sent_invitations = relationship("CohortInvitation", foreign_keys="CohortInvitation.professor_id", back_populates=None)
    received_invitations = relationship("CohortInvitation", foreign_keys="CohortInvitation.student_id", back_populates=None)
    notifications = relationship("Notification", back_populates="user")
    
    # PostgreSQL indexes for better performance
    __table_args__ = (
        Index('idx_users_email', 'email'),
        Index('idx_users_username', 'username'),
        Index('idx_users_role', 'role'),
        Index('idx_users_created_at', 'created_at'),
        Index('idx_users_google_id', 'google_id'),
        Index('idx_users_provider', 'provider'),
    )

class Scenario(Base):
    __tablename__ = "scenarios"
    
    id = Column(Integer, primary_key=True, index=True)
    unique_id = Column(String, unique=True, nullable=False, index=True)  # Unique, unguessable ID
    title = Column(String, index=True)
    description = Column(Text)
    challenge = Column(Text)
    industry = Column(String)
    learning_objectives = Column(JSON)
    
    # Source information
    source_type = Column(String, default="manual")  # manual, pdf_upload, template
    pdf_content = Column(Text, nullable=True)
    
    # Publishing metadata
    student_role = Column(String, nullable=True)
    category = Column(String, nullable=True)
    difficulty_level = Column(String, nullable=True)
    estimated_duration = Column(Integer, nullable=True)
    tags = Column(JSON, nullable=True)
    
    # PDF processing metadata
    pdf_title = Column(String, nullable=True)
    pdf_source = Column(String, nullable=True)
    processing_version = Column(String, default="1.0")
    
    # Community ratings
    rating_avg = Column(Float, default=0.0)
    rating_count = Column(Integer, default=0)
    
    # Sharing settings
    is_public = Column(Boolean, default=False)
    is_template = Column(Boolean, default=False)
    allow_remixes = Column(Boolean, default=True)
    
    # Status field for Draft/Active tags
    status = Column(String, default="draft", index=True)  # draft, active, archived
    
    # Completion tracking for simulation builder
    completion_status = Column(JSON, nullable=True)  # Track completion of different sections
    
    # Individual completion boolean fields for easier tracking
    name_completed = Column(Boolean, default=False)
    description_completed = Column(Boolean, default=False)
    student_role_completed = Column(Boolean, default=False)
    personas_completed = Column(Boolean, default=False)
    scenes_completed = Column(Boolean, default=False)
    images_completed = Column(Boolean, default=False)
    learning_outcomes_completed = Column(Boolean, default=False)
    ai_enhancement_completed = Column(Boolean, default=False)
    grading_config_completed = Column(Boolean, default=False)
    
    # Grading configuration for AI grading agent
    grading_config = Column(JSON, nullable=True)  # Store grading agent configuration
    
    # Draft system fields
    is_draft = Column(Boolean, default=True, index=True)  # True for draft, False for published
    published_version_id = Column(Integer, ForeignKey("scenarios.id"), nullable=True)  # Reference to published version
    draft_of_id = Column(Integer, ForeignKey("scenarios.id"), nullable=True)  # Reference to original if this is a draft
    
    # Community metrics
    usage_count = Column(Integer, default=0)
    clone_count = Column(Integer, default=0)
    
    # Soft deletion fields
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    deletion_reason = Column(String, nullable=True)
    
    # Metadata
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Unique constraint to prevent duplicate scenarios with same title by same user
    __table_args__ = (
        UniqueConstraint('title', 'created_by', name='unique_title_per_user'),
    )
    
    # Relationships
    creator = relationship("User", back_populates="scenarios", foreign_keys=[created_by])
    deleted_by_user = relationship("User", foreign_keys=[deleted_by])
    personas = relationship("ScenarioPersona", back_populates="scenario", cascade="all, delete-orphan")
    scenes = relationship("ScenarioScene", back_populates="scenario", cascade="all, delete-orphan")
    files = relationship("ScenarioFile", back_populates="scenario", cascade="all, delete-orphan")
    reviews = relationship("ScenarioReview", back_populates="scenario", cascade="all, delete-orphan")
    user_progress = relationship("UserProgress", back_populates="scenario")
    
    # PostgreSQL indexes for better performance
    __table_args__ = (
        Index('idx_scenarios_title', 'title'),
        Index('idx_scenarios_industry', 'industry'),
        Index('idx_scenarios_is_public', 'is_public'),
        Index('idx_scenarios_created_by', 'created_by'),
        Index('idx_scenarios_created_at', 'created_at'),
        Index('idx_scenarios_rating_avg', 'rating_avg'),
    )

class ScenarioPersona(Base):
    __tablename__ = "scenario_personas"
    
    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)
    
    # Persona details from AI processing
    name = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)
    background = Column(Text, nullable=True)
    correlation = Column(Text, nullable=True)
    
    # Goals and traits from AI
    primary_goals = Column(JSON, nullable=True)
    personality_traits = Column(JSON, nullable=True)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    scenario = relationship("Scenario", back_populates="personas")
    scenes = relationship("ScenarioScene", secondary=scene_personas, back_populates="personas")
    conversation_logs = relationship("ConversationLog", back_populates="persona")

class ScenarioScene(Base):
    __tablename__ = "scenario_scenes"
    
    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)
    
    # Scene details from AI processing
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    user_goal = Column(Text, nullable=True)
    scene_order = Column(Integer, default=0)
    estimated_duration = Column(Integer, nullable=True)
    
    # New fields for simulation control
    timeout_turns = Column(Integer, nullable=True)  # Number of turns before timeout
    success_metric = Column(String, nullable=True)  # How to measure scene success
    
    # Sequential simulation features
    max_attempts = Column(Integer, default=5)
    success_threshold = Column(Float, default=0.7)
    goal_criteria = Column(JSON, nullable=True)
    hint_triggers = Column(JSON, nullable=True)
    scene_context = Column(Text, nullable=True)
    persona_instructions = Column(JSON, nullable=True)
    
    # Visual assets
    image_url = Column(String, nullable=True)
    image_prompt = Column(String, nullable=True)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    scenario = relationship("Scenario", back_populates="scenes")
    personas = relationship("ScenarioPersona", secondary=scene_personas, back_populates="scenes")
    scene_progress = relationship("SceneProgress", back_populates="scene")
    conversation_logs = relationship("ConversationLog", back_populates="scene")

class ScenarioFile(Base):
    __tablename__ = "scenario_files"
    
    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)
    
    filename = Column(String, nullable=False)  # Add missing filename field
    file_path = Column(String, nullable=True)  # Make nullable since we have filename
    file_size = Column(Integer, nullable=True)
    file_type = Column(String, nullable=True)
    original_content = Column(Text, nullable=True)
    processed_content = Column(Text, nullable=True)
    processing_status = Column(String, default="pending")
    processing_log = Column(JSON, nullable=True)
    llamaparse_job_id = Column(String, nullable=True)  # Add missing field from schema
    
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    scenario = relationship("Scenario", back_populates="files")

class ScenarioReview(Base):
    __tablename__ = "scenario_reviews"
    
    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))
    reviewer_id = Column(Integer, ForeignKey("users.id"))
    
    rating = Column(Integer)  # 1-5 stars
    review_text = Column(Text, nullable=True)
    pros = Column(JSON, nullable=True)
    cons = Column(JSON, nullable=True)
    use_case = Column(String, nullable=True)
    
    # Helpful votes
    helpful_votes = Column(Integer, default=0)
    total_votes = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    scenario = relationship("Scenario", back_populates="reviews")
    reviewer = relationship("User", back_populates="scenario_reviews")

# --- SEQUENTIAL SIMULATION SYSTEM MODELS ---

class UserProgress(Base):
    __tablename__ = "user_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Allow None for now
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)
    
    # Current simulation state
    current_scene_id = Column(Integer, ForeignKey("scenario_scenes.id"), nullable=True)
    simulation_status = Column(String, default="not_started")  # not_started, in_progress, completed, abandoned
    
    # Progress tracking
    scenes_completed = Column(JSON, default=list)
    total_attempts = Column(Integer, default=0)
    hints_used = Column(Integer, default=0)
    forced_progressions = Column(Integer, default=0)
    
    # Orchestrator state for linear simulation
    orchestrator_data = Column(JSON, nullable=True)
    
    # Performance metrics
    completion_percentage = Column(Float, default=0.0)
    total_time_spent = Column(Integer, default=0)
    session_count = Column(Integer, default=0)
    final_score = Column(Float, nullable=True)
    
    # Soft deletion fields
    archived_at = Column(DateTime(timezone=True), nullable=True, index=True)
    archived_reason = Column(String, nullable=True)
    
    # Metadata
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    last_activity = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="user_progress")
    scenario = relationship("Scenario", back_populates="user_progress")
    current_scene = relationship("ScenarioScene", foreign_keys=[current_scene_id])
    scene_progress = relationship("SceneProgress", back_populates="user_progress")
    conversation_logs = relationship("ConversationLog", back_populates="user_progress")

class SceneProgress(Base):
    __tablename__ = "scene_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    user_progress_id = Column(Integer, ForeignKey("user_progress.id"), nullable=False)
    scene_id = Column(Integer, ForeignKey("scenario_scenes.id"), nullable=False)
    
    # Progress tracking
    status = Column(String, default="not_started")  # not_started, in_progress, completed, failed
    attempts = Column(Integer, default=0)
    hints_used = Column(Integer, default=0)
    goal_achieved = Column(Boolean, default=False)
    forced_progression = Column(Boolean, default=False)
    
    # Performance metrics
    time_spent = Column(Integer, default=0)  # seconds
    messages_sent = Column(Integer, default=0)
    ai_responses = Column(Integer, default=0)
    goal_achievement_score = Column(Float, nullable=True)
    interaction_quality = Column(Float, nullable=True)
    scene_feedback = Column(Text, nullable=True)
    
    # Metadata
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user_progress = relationship("UserProgress", back_populates="scene_progress")
    scene = relationship("ScenarioScene", back_populates="scene_progress")

class ConversationLog(Base):
    __tablename__ = "conversation_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_progress_id = Column(Integer, ForeignKey("user_progress.id"), nullable=False)
    scene_id = Column(Integer, ForeignKey("scenario_scenes.id"), nullable=False)
    
    # Message details
    message_type = Column(String, nullable=False)  # user, ai_persona, system, hint
    sender_name = Column(String, nullable=True)
    persona_id = Column(Integer, ForeignKey("scenario_personas.id"), nullable=True)
    message_content = Column(Text, nullable=False)
    
    # Context and metadata
    message_order = Column(Integer, nullable=False)
    attempt_number = Column(Integer, default=1)
    is_hint = Column(Boolean, default=False)
    
    # AI processing context
    ai_context_used = Column(JSON, nullable=True)
    ai_model_version = Column(String, nullable=True)
    processing_time = Column(Float, nullable=True)
    
    # User interaction tracking
    user_reaction = Column(String, nullable=True)
    led_to_progress = Column(Boolean, default=False)
    
    # Metadata
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user_progress = relationship("UserProgress", back_populates="conversation_logs")
    scene = relationship("ScenarioScene", back_populates="conversation_logs")
    persona = relationship("ScenarioPersona", back_populates="conversation_logs")


# ============================================================================
# LangChain Integration Models
# ============================================================================

class VectorEmbeddings(Base):
    """Store vector embeddings for similarity search"""
    __tablename__ = "vector_embeddings"
    
    id = Column(Integer, primary_key=True, index=True)
    content_type = Column(String, nullable=False, index=True)  # 'scenario', 'persona', 'conversation', etc.
    content_id = Column(Integer, nullable=False, index=True)  # ID of the original content
    content_hash = Column(String, nullable=False, index=True)  # Hash for deduplication
    # Store as Vector when configured and available, JSON otherwise
    # The vector dimension will be validated against embedding_dimension at runtime
    embedding_vector = Column(
        get_vector_column_type(), 
        nullable=False
    )
    embedding_model = Column(String, nullable=False)  # 'openai-ada-002', 'sentence-transformers', etc.
    embedding_dimension = Column(Integer, nullable=False)  # Dimension of the vector
    original_content = Column(Text, nullable=False)  # Original text content
    content_metadata = Column(JSON, nullable=True)  # Additional metadata
    similarity_threshold = Column(Float, nullable=True)  # Threshold for similarity matching
    is_active = Column(Boolean, default=True, index=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_vector_embeddings_content_type', 'content_type'),
        Index('idx_vector_embeddings_content_id', 'content_id'),
        Index('idx_vector_embeddings_content_hash', 'content_hash'),
        Index('idx_vector_embeddings_active', 'is_active'),
        Index('idx_vector_embeddings_created_at', 'created_at'),
    )


class SessionMemory(Base):
    """Store session-specific memory for LangChain agents"""
    __tablename__ = "session_memory"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, nullable=False, index=True)
    user_progress_id = Column(Integer, ForeignKey("user_progress.id"), nullable=False, index=True)
    scene_id = Column(Integer, ForeignKey("scenario_scenes.id"), nullable=True, index=True)
    memory_type = Column(String, nullable=False, index=True)  # 'conversation', 'context', 'summary', 'insight'
    memory_content = Column(Text, nullable=False)  # The actual memory content
    memory_metadata = Column(JSON, nullable=True)  # Additional metadata
    parent_memory_id = Column(Integer, ForeignKey("session_memory.id"), nullable=True)  # For hierarchical memory
    related_persona_id = Column(Integer, ForeignKey("scenario_personas.id"), nullable=True)  # If memory is persona-specific
    importance_score = Column(Float, nullable=True, index=True)  # 0.0 to 1.0
    access_count = Column(Integer, default=0)  # How many times this memory was accessed
    last_accessed = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user_progress = relationship("UserProgress")
    scene = relationship("ScenarioScene")
    persona = relationship("ScenarioPersona")
    parent_memory = relationship("SessionMemory", remote_side=[id])
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_session_memory_session_id', 'session_id'),
        Index('idx_session_memory_user_progress_id', 'user_progress_id'),
        Index('idx_session_memory_scene_id', 'scene_id'),
        Index('idx_session_memory_type', 'memory_type'),
        Index('idx_session_memory_importance', 'importance_score'),
        Index('idx_session_memory_last_accessed', 'last_accessed'),
    )


class ConversationSummaries(Base):
    """Store AI-generated summaries of conversations"""
    __tablename__ = "conversation_summaries"
    
    id = Column(Integer, primary_key=True, index=True)
    user_progress_id = Column(Integer, ForeignKey("user_progress.id"), nullable=False, index=True)
    scene_id = Column(Integer, ForeignKey("scenario_scenes.id"), nullable=True, index=True)
    summary_type = Column(String, nullable=False, index=True)  # 'scene_completion', 'conversation', 'learning_moment'
    summary_text = Column(Text, nullable=False)  # The summary content
    key_points = Column(JSON, nullable=True)  # Extracted key points
    learning_moments = Column(JSON, nullable=True)  # Important learning moments
    insights = Column(JSON, nullable=True)  # AI-generated insights
    recommendations = Column(JSON, nullable=True)  # Recommendations for improvement
    conversation_count = Column(Integer, nullable=True)  # Number of conversations summarized
    message_count = Column(Integer, nullable=True)  # Number of messages summarized
    summary_metadata = Column(JSON, nullable=True)  # Additional metadata
    quality_score = Column(Float, nullable=True, index=True)  # Quality score of the summary
    relevance_score = Column(Float, nullable=True)  # Relevance to learning objectives
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user_progress = relationship("UserProgress")
    scene = relationship("ScenarioScene")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_conversation_summaries_user_progress_id', 'user_progress_id'),
        Index('idx_conversation_summaries_scene_id', 'scene_id'),
        Index('idx_conversation_summaries_type', 'summary_type'),
        Index('idx_conversation_summaries_quality', 'quality_score'),
        Index('idx_conversation_summaries_created_at', 'created_at'),
    )


class AgentSessions(Base):
    """Store LangChain agent session information"""
    __tablename__ = "agent_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, nullable=False, unique=True, index=True)
    user_progress_id = Column(Integer, ForeignKey("user_progress.id"), nullable=False, index=True)
    agent_type = Column(String, nullable=False, index=True)  # 'persona', 'grading', 'summarization', 'retrieval'
    agent_id = Column(String, nullable=True, index=True)  # Specific agent identifier
    session_state = Column(JSON, nullable=True)  # Current session state
    session_config = Column(JSON, nullable=True)  # Session configuration
    session_metadata = Column(JSON, nullable=True)  # Additional metadata
    total_interactions = Column(Integer, default=0)  # Total number of interactions
    total_tokens_used = Column(Integer, default=0)  # Total tokens consumed
    average_response_time = Column(Float, nullable=True)  # Average response time in seconds
    error_count = Column(Integer, default=0)  # Number of errors encountered
    is_active = Column(Boolean, default=True, index=True)  # Whether session is active
    last_activity = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)  # Session expiration
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user_progress = relationship("UserProgress")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_agent_sessions_session_id', 'session_id'),
        Index('idx_agent_sessions_user_progress_id', 'user_progress_id'),
        Index('idx_agent_sessions_agent_type', 'agent_type'),
        Index('idx_agent_sessions_active', 'is_active'),
        Index('idx_agent_sessions_last_activity', 'last_activity'),
    )


# --- COHORT MANAGEMENT MODELS ---

class Cohort(Base):
    """Cohort management for educational groups"""
    __tablename__ = "cohorts"
    
    id = Column(Integer, primary_key=True, index=True)
    unique_id = Column(String, unique=True, nullable=False, index=True)  # Unique, unguessable ID
    title = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    course_code = Column(String, nullable=True, index=True)
    semester = Column(String, nullable=True)  # Fall, Spring, Summer, Winter
    year = Column(Integer, nullable=True, index=True)
    max_students = Column(Integer, nullable=True)
    
    # Settings
    auto_approve = Column(Boolean, default=True)
    allow_self_enrollment = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True, index=True)
    
    # Metadata
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    creator = relationship("User", back_populates="created_cohorts")
    students = relationship("CohortStudent", back_populates="cohort", cascade="all, delete-orphan")
    simulations = relationship("CohortSimulation", back_populates="cohort", cascade="all, delete-orphan")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_cohorts_created_by', 'created_by'),
        Index('idx_cohorts_active', 'is_active'),
        Index('idx_cohorts_year', 'year'),
        Index('idx_cohorts_course_code', 'course_code'),
    )


class CohortStudent(Base):
    """Student enrollment in cohorts"""
    __tablename__ = "cohort_students"
    
    id = Column(Integer, primary_key=True, index=True)
    cohort_id = Column(Integer, ForeignKey("cohorts.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Enrollment status
    status = Column(String, default="pending")  # pending, approved, rejected, withdrawn
    enrollment_date = Column(DateTime(timezone=True), server_default=func.now())
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    cohort = relationship("Cohort", back_populates="students")
    student = relationship("User", foreign_keys=[student_id])
    approver = relationship("User", foreign_keys=[approved_by])
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_cohort_students_cohort_id', 'cohort_id'),
        Index('idx_cohort_students_student_id', 'student_id'),
        Index('idx_cohort_students_status', 'status'),
        Index('idx_cohort_students_enrollment_date', 'enrollment_date'),
    )


class CohortSimulation(Base):
    """Simulations assigned to cohorts"""
    __tablename__ = "cohort_simulations"
    
    id = Column(Integer, primary_key=True, index=True)
    cohort_id = Column(Integer, ForeignKey("cohorts.id"), nullable=False, index=True)
    simulation_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False, index=True)
    
    # Assignment details
    assigned_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    due_date = Column(DateTime(timezone=True), nullable=True)
    is_required = Column(Boolean, default=True)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    cohort = relationship("Cohort", back_populates="simulations")
    simulation = relationship("Scenario")
    assigner = relationship("User", foreign_keys=[assigned_by])
    student_instances = relationship("StudentSimulationInstance", back_populates="cohort_assignment", cascade="all, delete-orphan")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_cohort_simulations_cohort_id', 'cohort_id'),
        Index('idx_cohort_simulations_simulation_id', 'simulation_id'),
        Index('idx_cohort_simulations_assigned_by', 'assigned_by'),
        Index('idx_cohort_simulations_due_date', 'due_date'),
    )


class StudentSimulationInstance(Base):
    """Individual student simulation instances for cohort assignments"""
    __tablename__ = "student_simulation_instances"
    
    id = Column(Integer, primary_key=True, index=True)
    cohort_assignment_id = Column(Integer, ForeignKey("cohort_simulations.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    user_progress_id = Column(Integer, ForeignKey("user_progress.id"), nullable=False, index=True)
    
    # Instance status
    status = Column(String, default="not_started")  # not_started, in_progress, completed, submitted, graded
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Grading and feedback
    grade = Column(Float, nullable=True)  # 0.0 to 100.0
    feedback = Column(Text, nullable=True)
    graded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    graded_at = Column(DateTime(timezone=True), nullable=True)
    
    # Performance metrics
    completion_percentage = Column(Float, default=0.0)
    total_time_spent = Column(Integer, default=0)  # seconds
    attempts_count = Column(Integer, default=0)
    hints_used = Column(Integer, default=0)
    
    # Due date tracking
    is_overdue = Column(Boolean, default=False)
    days_late = Column(Integer, default=0)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    cohort_assignment = relationship("CohortSimulation", back_populates="student_instances")
    student = relationship("User", foreign_keys=[student_id])
    user_progress = relationship("UserProgress")
    grader = relationship("User", foreign_keys=[graded_by])
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_student_sim_instances_cohort_assignment', 'cohort_assignment_id'),
        Index('idx_student_sim_instances_student_id', 'student_id'),
        Index('idx_student_sim_instances_user_progress', 'user_progress_id'),
        Index('idx_student_sim_instances_status', 'status'),
        Index('idx_student_sim_instances_grade', 'grade'),
        Index('idx_student_sim_instances_completed_at', 'completed_at'),
    )


class CacheEntries(Base):
    """Store cached data for performance optimization"""
    __tablename__ = "cache_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    cache_key = Column(String, nullable=False, unique=True, index=True)
    cache_type = Column(String, nullable=False, index=True)  # 'embedding', 'response', 'summary', 'context'
    cache_data = Column(JSON, nullable=False)  # The cached data
    cache_size = Column(Integer, nullable=True)  # Size of cached data in bytes
    hit_count = Column(Integer, default=0)  # Number of cache hits
    miss_count = Column(Integer, default=0)  # Number of cache misses
    last_accessed = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)  # Cache expiration
    is_expired = Column(Boolean, default=False, index=True)  # Whether cache is expired
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_cache_entries_key', 'cache_key'),
        Index('idx_cache_entries_type', 'cache_type'),
        Index('idx_cache_entries_expires_at', 'expires_at'),
        Index('idx_cache_entries_last_accessed', 'last_accessed'),
    )


# Alias for backward compatibility
EmbeddingStore = VectorEmbeddings


class CohortInvitation(Base):
    """Cohort invitations sent by professors to students"""
    __tablename__ = "cohort_invitations"
    
    id = Column(Integer, primary_key=True, index=True)
    cohort_id = Column(Integer, ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False)
    professor_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    student_email = Column(String(255), nullable=False)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    invitation_token = Column(String(255), nullable=False, unique=True, index=True)
    status = Column(String(50), nullable=False, default="pending")  # pending, accepted, declined, expired
    message = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    cohort = relationship("Cohort")
    professor = relationship("User", foreign_keys=[professor_id], back_populates=None, viewonly=True)
    student = relationship("User", foreign_keys=[student_id], back_populates=None, viewonly=True)
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_cohort_invitations_cohort_id', 'cohort_id'),
        Index('idx_cohort_invitations_professor_id', 'professor_id'),
        Index('idx_cohort_invitations_student_email', 'student_email'),
        Index('idx_cohort_invitations_token', 'invitation_token'),
        Index('idx_cohort_invitations_status', 'status'),
    )


class Notification(Base):
    """User notifications for in-app messaging"""
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(50), nullable=False)  # invitation, assignment, grade, etc.
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    data = Column(JSON, nullable=True)  # Additional data like cohort_id, invitation_id, etc.
    is_read = Column(Boolean, nullable=False, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_notifications_user_id', 'user_id'),
        Index('idx_notifications_type', 'type'),
        Index('idx_notifications_is_read', 'is_read'),
        Index('idx_notifications_created_at', 'created_at'),
    )


class ProfessorStudentMessage(Base):
    """Messages between professors and students"""
    __tablename__ = "professor_student_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    professor_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    cohort_id = Column(Integer, ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=True, index=True)
    
    # Message content
    subject = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    message_type = Column(String(50), nullable=False, default="general")  # general, assignment, grade, etc.
    
    # Threading support
    parent_message_id = Column(Integer, ForeignKey("professor_student_messages.id", ondelete="CASCADE"), nullable=True)
    is_reply = Column(Boolean, nullable=False, default=False)
    
    # Status tracking
    professor_read = Column(Boolean, nullable=False, default=True)  # Professor always reads their own messages
    student_read = Column(Boolean, nullable=False, default=False)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    professor = relationship("User", foreign_keys=[professor_id])
    student = relationship("User", foreign_keys=[student_id])
    cohort = relationship("Cohort")
    parent_message = relationship("ProfessorStudentMessage", remote_side=[id], backref="replies")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_professor_student_messages_professor_id', 'professor_id'),
        Index('idx_professor_student_messages_student_id', 'student_id'),
        Index('idx_professor_student_messages_cohort_id', 'cohort_id'),
        Index('idx_professor_student_messages_parent_id', 'parent_message_id'),
        Index('idx_professor_student_messages_created_at', 'created_at'),
        Index('idx_professor_student_messages_type', 'message_type'),
    )


class EmailQueue(Base):
    """Email queue for sending notifications"""
    __tablename__ = "email_queue"
    
    id = Column(Integer, primary_key=True, index=True)
    to_email = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    email_type = Column(String(50), nullable=False)  # invitation, reminder, etc.
    status = Column(String(50), nullable=False, default="pending")  # pending, sent, failed
    scheduled_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_email_queue_status', 'status'),
        Index('idx_email_queue_scheduled_at', 'scheduled_at'),
        Index('idx_email_queue_email_type', 'email_type'),
    ) 