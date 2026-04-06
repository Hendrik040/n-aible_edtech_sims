"""
Admin dashboard endpoints.

Provides aggregated stats, ralph loop progress, trace timelines,
latency percentiles, and prompt version analytics.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.dependencies import require_admin
from common.db.core import get_db
from common.db.models import User
from common.db.models.simulation.prompt_trace import PromptTrace

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/dashboard", tags=["Admin - Dashboard"])

GITHUB_REPO = "Hendrik040/n-aible_edtech_sims"
GITHUB_API = "https://api.github.com"
RALPH_LOOP_LABEL = "ralph-loop"


def _github_headers() -> dict:
    """Build GitHub API headers, using token if available for higher rate limits."""
    import os

    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


# ── Response schemas ────────────────────────────────────────────────


class AgentTypeCount(BaseModel):
    agent_type: str
    count: int


class DashboardSummary(BaseModel):
    total_traces: int
    traces_last_24h: int
    avg_latency_ms: Optional[float]
    avg_total_tokens: Optional[float]
    by_agent_type: List[AgentTypeCount]


class PRInfo(BaseModel):
    number: int
    title: str
    merged_at: Optional[str]
    html_url: Optional[str]
    linked_issue: Optional[int]
    canny_post_id: Optional[str]


class IssueInfo(BaseModel):
    number: int
    title: str
    created_at: str
    labels: List[str]


class RalphLoopProgress(BaseModel):
    total_prs_merged: int
    prs_list: List[PRInfo]
    open_issues_count: int
    issues_list: List[IssueInfo]


class TimelineBucket(BaseModel):
    hour: str  # ISO formatted hour
    count: int


class TraceTimeline(BaseModel):
    buckets: List[TimelineBucket]


class LatencyPercentiles(BaseModel):
    agent_type: str
    p50: Optional[float]
    p90: Optional[float]
    p95: Optional[float]
    p99: Optional[float]


class TraceLatencyResponse(BaseModel):
    percentiles: List[LatencyPercentiles]


class PromptVersionStats(BaseModel):
    agent_type: str
    prompt_version: str
    count: int
    avg_latency_ms: Optional[float]
    avg_total_tokens: Optional[float]


class PromptVersionsResponse(BaseModel):
    versions: List[PromptVersionStats]


# ── Endpoints ───────────────────────────────────────────────────────


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DashboardSummary:
    """Overall prompt trace statistics."""
    total = db.query(func.count(PromptTrace.id)).scalar() or 0

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    last_24h = (
        db.query(func.count(PromptTrace.id))
        .filter(PromptTrace.created_at >= cutoff)
        .scalar()
        or 0
    )

    avg_latency = db.query(func.avg(PromptTrace.latency_ms)).scalar()
    avg_tokens = db.query(func.avg(PromptTrace.total_tokens)).scalar()

    rows = (
        db.query(PromptTrace.agent_type, func.count(PromptTrace.id))
        .group_by(PromptTrace.agent_type)
        .all()
    )
    by_agent_type = [AgentTypeCount(agent_type=r[0], count=r[1]) for r in rows]

    return DashboardSummary(
        total_traces=total,
        traces_last_24h=last_24h,
        avg_latency_ms=round(avg_latency, 2) if avg_latency is not None else None,
        avg_total_tokens=round(avg_tokens, 2) if avg_tokens is not None else None,
        by_agent_type=by_agent_type,
    )


@router.get("/ralph-loop", response_model=RalphLoopProgress)
async def ralph_loop_progress(
    current_user: User = Depends(require_admin),
) -> RalphLoopProgress:
    """Fetch ralph loop progress from GitHub (merged PRs and open issues)."""
    prs_list: List[PRInfo] = []
    issues_list: List[IssueInfo] = []

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            pr_resp, issue_resp = await _fetch_github(client)

            # Process merged PRs
            if pr_resp.status_code == 200:
                import re

                for pr in pr_resp.json():
                    if pr.get("merged_at"):
                        # Extract linked issue and Canny post from PR body
                        linked_issue = None
                        canny_post_id = None
                        body = pr.get("body") or ""
                        issue_match = re.search(
                            r"(?:fixes|closes|resolves)\s+#(\d+)", body, re.IGNORECASE
                        )
                        if issue_match:
                            linked_issue = int(issue_match.group(1))
                        canny_match = re.search(
                            r"post_id[=:\s]+([a-f0-9]{20,})", body, re.IGNORECASE
                        )
                        if canny_match:
                            canny_post_id = canny_match.group(1)
                        prs_list.append(
                            PRInfo(
                                number=pr["number"],
                                title=pr["title"],
                                merged_at=pr["merged_at"],
                                html_url=pr.get("html_url"),
                                linked_issue=linked_issue,
                                canny_post_id=canny_post_id,
                            )
                        )

            # Process open issues (filter out pull requests)
            if issue_resp.status_code == 200:
                for issue in issue_resp.json():
                    if "pull_request" in issue:
                        continue
                    issues_list.append(
                        IssueInfo(
                            number=issue["number"],
                            title=issue["title"],
                            created_at=issue["created_at"],
                            labels=[l["name"] for l in issue.get("labels", [])],
                        )
                    )
    except Exception as exc:
        logger.warning(f"GitHub API request failed: {exc}")
        # Return empty data rather than failing the endpoint

    return RalphLoopProgress(
        total_prs_merged=len(prs_list),
        prs_list=prs_list,
        open_issues_count=len(issues_list),
        issues_list=issues_list,
    )


async def _fetch_github(client: httpx.AsyncClient):
    """Fetch ralph-loop PRs and open issues concurrently."""
    import asyncio

    headers = _github_headers()
    pr_url = f"{GITHUB_API}/repos/{GITHUB_REPO}/pulls"
    issue_url = f"{GITHUB_API}/repos/{GITHUB_REPO}/issues"

    pr_task = client.get(
        pr_url,
        params={
            "state": "closed",
            "base": "ralph-looped",
            "per_page": 100,
        },
        headers=headers,
    )
    issue_task = client.get(
        issue_url,
        params={"state": "open", "per_page": 100, "labels": RALPH_LOOP_LABEL},
        headers=headers,
    )
    return await asyncio.gather(pr_task, issue_task)


@router.get("/traces/timeline", response_model=TraceTimeline)
async def traces_timeline(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TraceTimeline:
    """Trace counts grouped by hour for the last 48 hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

    hour_trunc = func.date_trunc("hour", PromptTrace.created_at)
    rows = (
        db.query(hour_trunc.label("hour"), func.count(PromptTrace.id).label("cnt"))
        .filter(PromptTrace.created_at >= cutoff)
        .group_by(hour_trunc)
        .order_by(hour_trunc)
        .all()
    )

    buckets = [
        TimelineBucket(hour=r.hour.isoformat() if r.hour else "", count=r.cnt)
        for r in rows
    ]
    return TraceTimeline(buckets=buckets)


@router.get("/traces/latency", response_model=TraceLatencyResponse)
async def traces_latency(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TraceLatencyResponse:
    """Latency percentiles (p50, p90, p95, p99) by agent_type."""
    # Use PostgreSQL percentile_cont via ordered-set aggregate
    percentiles_result: List[LatencyPercentiles] = []

    agent_types = (
        db.query(PromptTrace.agent_type)
        .distinct()
        .all()
    )

    for (agent_type,) in agent_types:
        row = (
            db.query(
                func.percentile_cont(0.5)
                .within_group(PromptTrace.latency_ms)
                .label("p50"),
                func.percentile_cont(0.9)
                .within_group(PromptTrace.latency_ms)
                .label("p90"),
                func.percentile_cont(0.95)
                .within_group(PromptTrace.latency_ms)
                .label("p95"),
                func.percentile_cont(0.99)
                .within_group(PromptTrace.latency_ms)
                .label("p99"),
            )
            .filter(PromptTrace.agent_type == agent_type)
            .one()
        )
        percentiles_result.append(
            LatencyPercentiles(
                agent_type=agent_type,
                p50=round(row.p50, 2) if row.p50 is not None else None,
                p90=round(row.p90, 2) if row.p90 is not None else None,
                p95=round(row.p95, 2) if row.p95 is not None else None,
                p99=round(row.p99, 2) if row.p99 is not None else None,
            )
        )

    return TraceLatencyResponse(percentiles=percentiles_result)


@router.get("/prompt-versions", response_model=PromptVersionsResponse)
async def prompt_versions(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PromptVersionsResponse:
    """Distinct prompt versions with counts, avg latency, and avg tokens."""
    rows = (
        db.query(
            PromptTrace.agent_type,
            PromptTrace.prompt_version,
            func.count(PromptTrace.id).label("count"),
            func.avg(PromptTrace.latency_ms).label("avg_latency_ms"),
            func.avg(PromptTrace.total_tokens).label("avg_total_tokens"),
        )
        .group_by(PromptTrace.agent_type, PromptTrace.prompt_version)
        .order_by(PromptTrace.agent_type, PromptTrace.prompt_version)
        .all()
    )

    versions = [
        PromptVersionStats(
            agent_type=r.agent_type,
            prompt_version=r.prompt_version,
            count=r.count,
            avg_latency_ms=round(r.avg_latency_ms, 2) if r.avg_latency_ms is not None else None,
            avg_total_tokens=round(r.avg_total_tokens, 2) if r.avg_total_tokens is not None else None,
        )
        for r in rows
    ]

    return PromptVersionsResponse(versions=versions)
