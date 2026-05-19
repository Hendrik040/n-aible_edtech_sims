"""Ralph rewrite-loop pipeline event model.

Each row is one phase transition during a loop iteration. The admin
dashboard queries this table to render the per-ticket × per-phase
pipeline grid and the aggregate phase success-rate bars.

Phases correspond to scripts/rewrite/WORKFLOW.md:
  A-implement, B-review, C-testing, D-merge, E-canny.

Statuses: started | passed | failed | skipped | warn.
"""
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from common.db.base import Base


class RalphPipelineEvent(Base):
    __tablename__ = "ralph_pipeline_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Ticket + iteration identity
    ticket_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    iteration: Mapped[int] = mapped_column(Integer, nullable=False)
    loop_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    pr_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    issue_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # What happened
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Flexible per-phase data (round number for B, check name for D, etc.)
    context: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
