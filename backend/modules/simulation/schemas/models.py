from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Table,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from common.config import get_settings
from common.db.base import Base

settings = get_settings()

try:
    from pgvector.sqlalchemy import Vector

    PGVECTOR_AVAILABLE = True
except ImportError:
    Vector = None
    PGVECTOR_AVAILABLE = False


def get_vector_column_type(dimension: int = 1536):
    if settings.use_pgvector and PGVECTOR_AVAILABLE:
        return Vector(dimension)
    return JSON


def generate_cohort_id():
    """Generate a short, user-friendly cohort ID like CH-MAN8P1QS"""
    import secrets
    import string

    chars = string.ascii_uppercase + string.digits
    random_part = "".join(secrets.choice(chars) for _ in range(8))
    return f"CH-{random_part}"


scene_personas = Table(
    "scene_personas",
    Base.metadata,
    Column("scene_id", Integer, ForeignKey("scenario_scenes.id"), primary_key=True),
    Column("persona_id", Integer, ForeignKey("scenario_personas.id"), primary_key=True),
    Column("involvement_level", String, default="participant"),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)


class Scenario(Base):
    __tablename__ = "scenarios"

    id = Column(Integer, primary_key=True, index=True)
    unique_id = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, index=True)
    description = Column(Text)
    challenge = Column(Text)
    industry = Column(String)
    learning_objectives = Column(JSON)
    source_type = Column(String, default="manual")
    pdf_content = Column(Text, nullable=True)
    student_role = Column(String, nullable=True)
    category = Column(String, nullable=True)
    difficulty_level = Column(String, nullable=True)
    estimated_duration = Column(Integer, nullable=True)
    tags = Column(JSON, nullable=True)
    pdf_title = Column(String, nullable=True)
    pdf_source = Column(String, nullable=True)
    processing_version = Column(String, default="1.0")
    case_study_url = Column(String, nullable=True)
    rating_avg = Column(Float, default=0.0)
    rating_count = Column(Integer, default=0)
    is_public = Column(Boolean, default=False)
    is_template = Column(Boolean, default=False)
    allow_remixes = Column(Boolean, default=True)
    status = Column(String, default="draft", index=True)
    completion_status = Column(JSON, nullable=True)
    name_completed = Column(Boolean, default=False)
    description_completed = Column(Boolean, default=False)
    student_role_completed = Column(Boolean, default=False)
    personas_completed = Column(Boolean, default=False)
    scenes_completed = Column(Boolean, default=False)
    images_completed = Column(Boolean, default=False)
    learning_outcomes_completed = Column(Boolean, default=False)
    ai_enhancement_completed = Column(Boolean, default=False)
    grading_config_completed = Column(Boolean, default=False)
    grading_config = Column(JSON, nullable=True)
    grading_prompt = Column(Text, nullable=True)
    rubric_title = Column(String, nullable=True)
    rubric_criteria = Column(JSON, nullable=True)
    rubric_performance_levels = Column(JSON, nullable=True)
    rubric_total_points = Column(Integer, nullable=True, default=100)
    is_draft = Column(Boolean, default=True, index=True)
    published_version_id = Column(Integer, ForeignKey("scenarios.id"), nullable=True)
    draft_of_id = Column(Integer, ForeignKey("scenarios.id"), nullable=True)
    usage_count = Column(Integer, default=0)
    clone_count = Column(Integer, default=0)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    deletion_reason = Column(String, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("title", "created_by", name="unique_title_per_user"),
        Index("idx_scenarios_title", "title"),
        Index("idx_scenarios_industry", "industry"),
        Index("idx_scenarios_is_public", "is_public"),
        Index("idx_scenarios_created_by", "created_by"),
        Index("idx_scenarios_created_at", "created_at"),
        Index("idx_scenarios_rating_avg", "rating_avg"),
    )

    creator = relationship("User", back_populates="scenarios", foreign_keys=[created_by])
    deleted_by_user = relationship("User", foreign_keys=[deleted_by])
    personas = relationship("ScenarioPersona", back_populates="scenario", cascade="all, delete-orphan")
    scenes = relationship("ScenarioScene", back_populates="scenario", cascade="all, delete-orphan")
    files = relationship("ScenarioFile", back_populates="scenario", cascade="all, delete-orphan")
    reviews = relationship("ScenarioReview", back_populates="scenario", cascade="all, delete-orphan")
    user_progress = relationship("UserProgress", back_populates="scenario")


class ScenarioPersona(Base):
    __tablename__ = "scenario_personas"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)
    name = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)
    background = Column(Text, nullable=True)
    correlation = Column(Text, nullable=True)
    primary_goals = Column(JSON, nullable=True)
    personality_traits = Column(JSON, nullable=True)
    system_prompt = Column(Text, nullable=True)
    image_url = Column(String(2048), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    deletion_reason = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    scenario = relationship("Scenario", back_populates="personas")
    scenes = relationship("ScenarioScene", secondary=scene_personas, back_populates="personas")
    conversation_logs = relationship("ConversationLog", back_populates="persona")


class ScenarioScene(Base):
    __tablename__ = "scenario_scenes"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    user_goal = Column(Text, nullable=True)
    scene_order = Column(Integer, default=0)
    estimated_duration = Column(Integer, nullable=True)
    timeout_turns = Column(Integer, nullable=True)
    success_metric = Column(String, nullable=True)
    max_attempts = Column(Integer, default=5)
    success_threshold = Column(Float, default=0.7)
    goal_criteria = Column(JSON, nullable=True)
    hint_triggers = Column(JSON, nullable=True)
    scene_context = Column(Text, nullable=True)
    persona_instructions = Column(JSON, nullable=True)
    image_url = Column(String, nullable=True)
    image_prompt = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    scenario = relationship("Scenario", back_populates="scenes")
    personas = relationship("ScenarioPersona", secondary=scene_personas, back_populates="scenes")
    scene_progress = relationship("SceneProgress", back_populates="scene")
    conversation_logs = relationship("ConversationLog", back_populates="scene")


class ScenarioFile(Base):
    __tablename__ = "scenario_files"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    file_type = Column(String, nullable=True)
    original_content = Column(Text, nullable=True)
    processed_content = Column(Text, nullable=True)
    processing_status = Column(String, default="pending")
    processing_log = Column(JSON, nullable=True)
    llamaparse_job_id = Column(String, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)

    scenario = relationship("Scenario", back_populates="files")


class ScenarioReview(Base):
    __tablename__ = "scenario_reviews"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))
    reviewer_id = Column(Integer, ForeignKey("users.id"))
    rating = Column(Integer)
    review_text = Column(Text, nullable=True)
    pros = Column(JSON, nullable=True)
    cons = Column(JSON, nullable=True)
    use_case = Column(String, nullable=True)
    helpful_votes = Column(Integer, default=0)
    total_votes = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    scenario = relationship("Scenario", back_populates="reviews")
    reviewer = relationship("User", back_populates="scenario_reviews")


class UserProgress(Base):
    __tablename__ = "user_progress"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)
    current_scene_id = Column(Integer, ForeignKey("scenario_scenes.id"), nullable=True)
    simulation_status = Column(String, default="not_started")
    scenes_completed = Column(JSON, default=list)
    total_attempts = Column(Integer, default=0)
    hints_used = Column(Integer, default=0)
    forced_progressions = Column(Integer, default=0)
    orchestrator_data = Column(JSON, nullable=True)
    completion_percentage = Column(Float, default=0.0)
    total_time_spent = Column(Integer, default=0)
    session_count = Column(Integer, default=0)
    final_score = Column(Float, nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True, index=True)
    archived_reason = Column(String, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    last_activity = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

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
    status = Column(String, default="not_started")
    attempts = Column(Integer, default=0)
    hints_used = Column(Integer, default=0)
    goal_achieved = Column(Boolean, default=False)
    forced_progression = Column(Boolean, default=False)
    time_spent = Column(Integer, default=0)
    messages_sent = Column(Integer, default=0)
    ai_responses = Column(Integer, default=0)
    goal_achievement_score = Column(Float, nullable=True)
    interaction_quality = Column(Float, nullable=True)
    scene_feedback = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user_progress = relationship("UserProgress", back_populates="scene_progress")
    scene = relationship("ScenarioScene", back_populates="scene_progress")


class ConversationLog(Base):
    __tablename__ = "conversation_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_progress_id = Column(Integer, ForeignKey("user_progress.id"), nullable=False)
    scene_id = Column(Integer, ForeignKey("scenario_scenes.id"), nullable=False)
    persona_id = Column(Integer, ForeignKey("scenario_personas.id"), nullable=True)
    sender_name = Column(String, nullable=False)
    message_type = Column(String, default="user")
    message_content = Column(Text, nullable=False)
    message_order = Column(Integer, default=0)
    attempt_number = Column(Integer, default=1)
    is_hint = Column(Boolean, default=False)
    ai_context_used = Column(JSON, nullable=True)
    ai_model_version = Column(String, nullable=True)
    processing_time = Column(Float, nullable=True)
    user_reaction = Column(String, nullable=True)
    led_to_progress = Column(Boolean, default=False)
    metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user_progress = relationship("UserProgress", back_populates="conversation_logs")
    scene = relationship("ScenarioScene", back_populates="conversation_logs")
    persona = relationship("ScenarioPersona", back_populates="conversation_logs")


class VectorEmbeddings(Base):
    __tablename__ = "vector_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False, index=True)
    scene_id = Column(Integer, ForeignKey("scenario_scenes.id"), nullable=True, index=True)
    persona_id = Column(Integer, ForeignKey("scenario_personas.id"), nullable=True, index=True)
    embedding_type = Column(String, default="scene_context")
    vector = Column(get_vector_column_type(), nullable=False)
    metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SessionMemory(Base):
    __tablename__ = "session_memory"

    id = Column(Integer, primary_key=True, index=True)
    user_progress_id = Column(Integer, ForeignKey("user_progress.id"), nullable=False)
    scene_id = Column(Integer, ForeignKey("scenario_scenes.id"), nullable=False)
    agent_id = Column(Integer, ForeignKey("scenario_personas.id"), nullable=True)
    memory_type = Column(String, default="conversation")
    memory_data = Column(JSONB, nullable=False)
    importance = Column(Float, default=0.5)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ConversationSummaries(Base):
    __tablename__ = "conversation_summaries"

    id = Column(Integer, primary_key=True, index=True)
    user_progress_id = Column(Integer, ForeignKey("user_progress.id"), nullable=False)
    scene_id = Column(Integer, ForeignKey("scenario_scenes.id"), nullable=True)
    summary_type = Column(String, default="scene_completion")
    summary_text = Column(Text, nullable=False)
    metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AgentSessions(Base):
    __tablename__ = "agent_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_progress_id = Column(Integer, ForeignKey("user_progress.id"), nullable=False)
    agent_type = Column(String, nullable=False)
    agent_id = Column(String, nullable=False)
    session_id = Column(String, unique=True, nullable=False, index=True)
    session_config = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class StudentSimulationInstance(Base):
    __tablename__ = "student_simulation_instances"

    id = Column(Integer, primary_key=True, index=True)
    simulation_instance_id = Column(String, unique=True, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)
    cohort_id = Column(Integer, ForeignKey("cohorts.id"), nullable=True)
    progress_status = Column(String, default="not_started")
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    last_interaction_at = Column(DateTime(timezone=True), server_default=func.now())
    metadata = Column(JSONB, nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class GradingMaterial(Base):
    __tablename__ = "grading_materials"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False)
    professor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    rubric = Column(JSONB, nullable=True)
    criteria = Column(JSONB, nullable=True)
    max_score = Column(Integer, default=100)
    version = Column(String, default="1.0")
    metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class GradingMaterialChunk(Base):
    __tablename__ = "grading_material_chunks"

    id = Column(Integer, primary_key=True, index=True)
    grading_material_id = Column(Integer, ForeignKey("grading_materials.id"), nullable=False)
    chunk_order = Column(Integer, default=0)
    chunk_type = Column(String, default="rubric_section")
    content = Column(Text, nullable=False)
    metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class GradeHistory(Base):
    __tablename__ = "grade_history"

    id = Column(Integer, primary_key=True, index=True)
    user_progress_id = Column(Integer, ForeignKey("user_progress.id"), nullable=False)
    graded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    grading_material_id = Column(Integer, ForeignKey("grading_materials.id"), nullable=True)
    total_score = Column(Float, nullable=False)
    max_score = Column(Float, nullable=False)
    rubric_breakdown = Column(JSONB, nullable=True)
    feedback = Column(Text, nullable=True)
    grading_method = Column(String, default="manual")
    metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


__all__ = [
    "AgentSessions",
    "ConversationLog",
    "ConversationSummaries",
    "GradeHistory",
    "GradingMaterial",
    "GradingMaterialChunk",
    "Scenario",
    "ScenarioFile",
    "ScenarioPersona",
    "ScenarioReview",
    "ScenarioScene",
    "SceneProgress",
    "SessionMemory",
    "StudentSimulationInstance",
    "UserProgress",
    "VectorEmbeddings",
    "generate_cohort_id",
    "get_vector_column_type",
    "scene_personas",
]

