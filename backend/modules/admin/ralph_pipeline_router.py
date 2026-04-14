"""Admin — Ralph rewrite-loop pipeline visibility.

Exposes the event stream + aggregate stats the admin dashboard renders
as a per-ticket × per-phase grid. The loop's `emit_event` helper POSTs
to /event (shared-secret bearer auth). Everything else is read-only
for the dashboard.

See plan/REWRITE_BREAKDOWN.md for the ticket graph and
scripts/rewrite/WORKFLOW.md for the phase definitions driving this
schema.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dependencies import require_admin
from common.db.core import get_db
from common.db.models import RalphPipelineEvent, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/ralph-pipeline", tags=["Admin - Ralph Pipeline"])

# Phases in the order they appear in the grid.
PHASES: List[str] = ["A-implement", "B-review", "C-testing", "D-merge", "E-canny"]

# In-process fan-out for SSE /stream. Every POST /event pushes into every
# active subscriber's queue. Lightweight — single-process only, which is
# fine for Railway's single-instance backend service.
_SSE_SUBSCRIBERS: "List[asyncio.Queue[str]]" = []


# ── Auth for POST /event ───────────────────────────────────────────────
def _verify_ingest_token(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> None:
    """Shared-secret bearer auth for the loop's event ingestion POST.

    The token lives in `RALPH_EVENT_TOKEN` env var (set on Railway + in
    the loop runner's local .env). Missing env var → ingestion is disabled
    (returns 503) so an unconfigured deploy never accepts anonymous writes.
    """
    expected = os.environ.get("RALPH_EVENT_TOKEN", "")
    if not expected:
        raise HTTPException(503, "ralph-pipeline ingestion not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    provided = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(401, "invalid bearer token")


# ── Schemas ────────────────────────────────────────────────────────────
class EventIn(BaseModel):
    ticket_id: str = Field(..., pattern=r"^phase-\d+(\.\d+)?$")
    iteration: int = Field(..., ge=1)
    loop_run_id: str = Field(..., min_length=1, max_length=64)
    pr_number: Optional[int] = None
    phase: str
    status: str
    detail: Optional[str] = None
    duration_sec: Optional[int] = Field(None, ge=0)
    context: Optional[Dict[str, Any]] = None


class PhaseState(BaseModel):
    status: str
    duration_sec: Optional[int] = None
    detail: Optional[str] = None
    updated_at: Optional[str] = None


class TicketRow(BaseModel):
    ticket_id: str
    pr_number: Optional[int]
    state: str  # pending | running | merged | failed | blocked
    phases: Dict[str, Optional[PhaseState]]
    started_at: Optional[str]
    completed_at: Optional[str]


class PhaseStat(BaseModel):
    phase: str
    runs: int
    passed: int
    failed: int
    warned: int
    success_rate: float  # 0.0 .. 1.0


class FailureSignature(BaseModel):
    phase: str
    detail: str
    count: int


class StatsResponse(BaseModel):
    # Window for phase stats + failure signatures (matches `since_hours` query arg).
    window_hours: int
    phases: List[PhaseStat]
    failure_signatures: List[FailureSignature]
    # Windowed counts — match the window above so the whole response has
    # one consistent time scope.
    merged_in_window: int
    open_in_window: int
    # All-time totals — explicit separate fields so dashboards can show
    # overall project progress ("4/22 merged") without mixing scopes.
    merged_all_time: int
    open_all_time: int


# ── POST /event — loop ingest ──────────────────────────────────────────
@router.post("/event", status_code=202)
async def ingest_event(
    event: EventIn,
    request: Request,
    _: None = Depends(_verify_ingest_token),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Accept one phase-transition event from the Ralph loop."""
    row = RalphPipelineEvent(
        ticket_id=event.ticket_id,
        iteration=event.iteration,
        loop_run_id=event.loop_run_id,
        pr_number=event.pr_number,
        phase=event.phase,
        status=event.status,
        detail=event.detail,
        duration_sec=event.duration_sec,
        context=event.context,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # Fan out to SSE subscribers. Non-blocking — drop on any subscriber
    # whose queue is full (we don't want one slow client to back-pressure
    # ingestion).
    payload = json.dumps(
        {
            "id": row.id,
            "ticket_id": row.ticket_id,
            "iteration": row.iteration,
            "phase": row.phase,
            "status": row.status,
            "detail": row.detail,
            "duration_sec": row.duration_sec,
            "pr_number": row.pr_number,
            "created_at": row.created_at.isoformat(),
        }
    )
    for q in list(_SSE_SUBSCRIBERS):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass

    return {"id": row.id}


# ── GET /tickets — main grid data ──────────────────────────────────────
@router.get("/tickets", response_model=List[TicketRow])
def list_tickets(
    loop_run_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> List[TicketRow]:
    """Latest phase state per ticket. Default: across all loop runs."""
    q = db.query(RalphPipelineEvent)
    if loop_run_id:
        q = q.filter(RalphPipelineEvent.loop_run_id == loop_run_id)
    events = q.order_by(RalphPipelineEvent.created_at.asc()).all()

    by_ticket: Dict[str, Dict[str, Any]] = {}
    for e in events:
        t = by_ticket.setdefault(
            e.ticket_id,
            {
                "pr_number": None,
                "phases": {p: None for p in PHASES},
                "started_at": e.created_at,
                "completed_at": None,
                "events": [],
            },
        )
        t["events"].append(e)
        if e.pr_number and not t["pr_number"]:
            t["pr_number"] = e.pr_number

        # Collapse "started" + later terminal to show the terminal state
        # when present. If only "started" exists, show "running".
        state = PhaseState(
            status="running" if e.status == "started" else e.status,
            duration_sec=e.duration_sec,
            detail=e.detail,
            updated_at=e.created_at.isoformat(),
        )
        t["phases"][e.phase] = state
        if e.status in ("passed", "failed", "warn", "skipped"):
            t["completed_at"] = e.created_at

    rows: List[TicketRow] = []
    for ticket_id, t in sorted(by_ticket.items(), key=lambda kv: kv[0]):
        rows.append(
            TicketRow(
                ticket_id=ticket_id,
                pr_number=t["pr_number"],
                state=_infer_state(t["phases"]),
                phases=t["phases"],
                started_at=t["started_at"].isoformat() if t["started_at"] else None,
                completed_at=t["completed_at"].isoformat() if t["completed_at"] else None,
            )
        )
    return rows


def _infer_state(phases: Dict[str, Optional[PhaseState]]) -> str:
    """Derive the ticket's rollup state from its phase grid."""
    any_running = any(p and p.status == "running" for p in phases.values())
    if any_running:
        return "running"
    merge_phase = phases.get("D-merge")
    if merge_phase and merge_phase.status in ("passed", "warn"):
        return "merged"
    any_failed = any(p and p.status == "failed" for p in phases.values())
    if any_failed:
        return "failed"
    any_seen = any(p is not None for p in phases.values())
    return "pending" if any_seen else "blocked"


# ── GET /tickets/{ticket_id} — drill-down ──────────────────────────────
@router.get("/tickets/{ticket_id}")
def get_ticket_history(
    ticket_id: str,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    events = (
        db.query(RalphPipelineEvent)
        .filter(RalphPipelineEvent.ticket_id == ticket_id)
        .order_by(RalphPipelineEvent.created_at.asc())
        .all()
    )
    if not events:
        raise HTTPException(404, f"no events for ticket {ticket_id}")
    return {
        "ticket_id": ticket_id,
        "events": [
            {
                "id": e.id,
                "iteration": e.iteration,
                "loop_run_id": e.loop_run_id,
                "phase": e.phase,
                "status": e.status,
                "detail": e.detail,
                "duration_sec": e.duration_sec,
                "context": e.context,
                "pr_number": e.pr_number,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
    }


# ── GET /stats — phase success rates + failure clusters ────────────────
@router.get("/stats", response_model=StatsResponse)
def stats(
    since_hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> StatsResponse:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    terminal_statuses = ("passed", "failed", "warn")
    rows = (
        db.query(RalphPipelineEvent)
        .filter(RalphPipelineEvent.created_at >= cutoff)
        .filter(RalphPipelineEvent.status.in_(terminal_statuses))
        .all()
    )

    by_phase: Dict[str, Dict[str, int]] = {p: {"passed": 0, "failed": 0, "warned": 0} for p in PHASES}
    for r in rows:
        bucket = by_phase.get(r.phase)
        if not bucket:
            continue
        if r.status == "passed":
            bucket["passed"] += 1
        elif r.status == "failed":
            bucket["failed"] += 1
        elif r.status == "warn":
            bucket["warned"] += 1

    phase_stats = []
    for p in PHASES:
        b = by_phase[p]
        total = b["passed"] + b["failed"] + b["warned"]
        phase_stats.append(
            PhaseStat(
                phase=p,
                runs=total,
                passed=b["passed"],
                failed=b["failed"],
                warned=b["warned"],
                success_rate=(b["passed"] / total) if total else 0.0,
            )
        )

    # Cluster failure signatures by (phase, first 80 chars of detail).
    signatures: Dict[tuple, int] = {}
    for r in rows:
        if r.status == "failed" and r.detail:
            key = (r.phase, r.detail[:80])
            signatures[key] = signatures.get(key, 0) + 1
    top_sigs = sorted(signatures.items(), key=lambda kv: kv[1], reverse=True)[:5]
    fail_sigs = [FailureSignature(phase=k[0], detail=k[1], count=v) for k, v in top_sigs]

    # Windowed merged/open counts — match the `since_hours` scope used
    # for phase_stats and failure_signatures above so the whole response
    # has one consistent time scope.
    #
    # Both merged_* and open_* count DISTINCT ticket_ids so the
    # subtraction below has unit-consistent semantics: merge events
    # can repeat per ticket (re-runs, warns followed by passes), so
    # counting raw rows would double-count and make open_* go negative.
    merged_in_window = (
        db.query(func.count(func.distinct(RalphPipelineEvent.ticket_id)))
        .filter(RalphPipelineEvent.created_at >= cutoff)
        .filter(RalphPipelineEvent.phase == "D-merge")
        .filter(RalphPipelineEvent.status.in_(("passed", "warn")))
        .scalar()
        or 0
    )
    open_in_window = (
        db.query(func.count(func.distinct(RalphPipelineEvent.ticket_id)))
        .filter(RalphPipelineEvent.created_at >= cutoff)
        .filter(RalphPipelineEvent.status.in_(("started", "failed")))
        .scalar()
        or 0
    )

    # All-time counts — separate fields for the "4/22 merged overall"
    # headline so dashboards can show cumulative progress without
    # mixing scopes with windowed rates. Same distinct-ticket discipline
    # as the windowed counts above.
    merged_all_time = (
        db.query(func.count(func.distinct(RalphPipelineEvent.ticket_id)))
        .filter(RalphPipelineEvent.phase == "D-merge")
        .filter(RalphPipelineEvent.status.in_(("passed", "warn")))
        .scalar()
        or 0
    )
    open_all_time = (
        db.query(func.count(func.distinct(RalphPipelineEvent.ticket_id)))
        .filter(RalphPipelineEvent.status.in_(("started", "failed")))
        .scalar()
        or 0
    )

    return StatsResponse(
        window_hours=since_hours,
        phases=phase_stats,
        failure_signatures=fail_sigs,
        merged_in_window=merged_in_window,
        open_in_window=max(open_in_window - merged_in_window, 0),
        merged_all_time=merged_all_time,
        open_all_time=max(open_all_time - merged_all_time, 0),
    )


# ── GET /stream — SSE live events ──────────────────────────────────────
@router.get("/stream")
async def stream_events(_admin: User = Depends(require_admin)) -> StreamingResponse:
    """Server-sent events: one message per new /event ingestion."""

    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
    _SSE_SUBSCRIBERS.append(queue)

    async def _event_gen():
        try:
            # Initial hello so the client knows the stream is live.
            yield 'event: hello\ndata: {"ok": true}\n\n'
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"event: phase\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat so intermediaries don't close the stream.
                    yield ": keepalive\n\n"
        finally:
            try:
                _SSE_SUBSCRIBERS.remove(queue)
            except ValueError:
                pass

    return StreamingResponse(
        _event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering
        },
    )
