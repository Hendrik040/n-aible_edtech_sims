"""Prompt trace model for logging every LLM call with full context."""
import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import Integer, String, Float, Text, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from common.db.base import Base


class PromptTrace(Base):
    """Records every LLM call with full prompt context, response, and metrics."""

    __tablename__ = "prompt_traces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Agent identification
    agent_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # "persona", "grading", "summarization"
    agent_name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # persona name or agent identifier

    # Session / context identifiers
    session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    scenario_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    scene_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # Prompt versioning
    prompt_version: Mapped[str] = mapped_column(
        String(20), nullable=False, default="v1"
    )

    # Full prompt data
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    context_injected: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assistant_response: Mapped[str] = mapped_column(Text, nullable=False)

    # Model info
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Token usage
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Performance
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    # Model params
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Extensible metadata
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
