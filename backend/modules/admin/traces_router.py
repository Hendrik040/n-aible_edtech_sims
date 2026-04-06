"""
API endpoints for querying prompt traces.

Provides admin/professor visibility into every LLM call made by
the simulation agents, with filtering and pagination.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, require_admin
from common.db.core import get_db
from common.db.models import User
from common.db.models.simulation.prompt_trace import PromptTrace

router = APIRouter(prefix="/api/admin/traces", tags=["Admin - Traces"])


# ── Response schemas ────────────────────────────────────────────────

class PromptTraceResponse(BaseModel):
    id: UUID
    created_at: datetime
    agent_type: str
    agent_name: str
    session_id: str
    user_id: Optional[int] = None
    scenario_id: Optional[int] = None
    scene_id: Optional[int] = None
    prompt_version: str
    system_prompt: str
    user_message: str
    context_injected: Optional[str] = None
    assistant_response: str
    model_name: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    latency_ms: int
    temperature: Optional[float] = None
    metadata_json: Optional[Dict[str, Any]] = None

    model_config = {"from_attributes": True}


class PaginatedTracesResponse(BaseModel):
    traces: List[PromptTraceResponse]
    total: int
    page: int
    page_size: int


# ── Endpoints ───────────────────────────────────────────────────────

@router.get("", response_model=PaginatedTracesResponse)
async def list_traces(
    session_id: Optional[str] = Query(None, description="Filter by simulation session ID"),
    scenario_id: Optional[int] = Query(None, description="Filter by scenario/simulation ID"),
    scene_id: Optional[int] = Query(None, description="Filter by scene ID"),
    agent_type: Optional[str] = Query(None, description="Filter by agent type (persona, grading, summarization)"),
    agent_name: Optional[str] = Query(None, description="Filter by agent name (partial match)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PaginatedTracesResponse:
    """List prompt traces with optional filters and pagination.

    Requires admin role. Returns traces ordered by most recent first.
    """
    query = db.query(PromptTrace)

    if session_id:
        query = query.filter(PromptTrace.session_id == session_id)
    if scenario_id:
        query = query.filter(PromptTrace.scenario_id == scenario_id)
    if scene_id:
        query = query.filter(PromptTrace.scene_id == scene_id)
    if agent_type:
        query = query.filter(PromptTrace.agent_type == agent_type)
    if agent_name:
        query = query.filter(PromptTrace.agent_name.ilike(f"%{agent_name}%"))

    total = query.count()
    traces = (
        query.order_by(desc(PromptTrace.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return PaginatedTracesResponse(
        traces=[PromptTraceResponse.model_validate(t) for t in traces],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{trace_id}", response_model=PromptTraceResponse)
async def get_trace(
    trace_id: UUID,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PromptTraceResponse:
    """Retrieve a single prompt trace by ID. Requires admin role."""
    from fastapi import HTTPException

    trace = db.query(PromptTrace).filter(PromptTrace.id == trace_id).first()
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return PromptTraceResponse.model_validate(trace)
