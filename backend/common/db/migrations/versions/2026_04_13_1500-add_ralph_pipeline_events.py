"""Add ralph_pipeline_events table

Revision ID: add_ralph_pipeline_events
Revises: add_code_language_to_scenes
Create Date: 2026-04-13 15:00:00.000000

One row per phase transition in the Ralph rewrite loop. Feeds the
admin dashboard's pipeline visibility grid — shows per-ticket × per-
phase pass/fail state so we can see WHERE in the pipeline things are
breaking, not just what the final outcome was.

Schema:
    id           bigserial PK
    ticket_id    "phase-0.1" / "phase-1.4" / etc.
    iteration    iteration number within a loop run (1-indexed)
    loop_run_id  loop invocation timestamp (groups iterations from one run)
    pr_number    null until Phase A opens one
    phase        "A-implement" | "B-review" | "C-testing" | "D-merge" | "E-canny"
    status       "started" | "passed" | "failed" | "skipped" | "warn"
    detail       error message / reason (nullable)
    duration_sec how long the phase took (null on "started")
    context      jsonb — extensible key-value for phase-specific data
    created_at   timestamptz (NOT NULL, default now())
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision: str = "add_ralph_pipeline_events"
down_revision: Union[str, None] = "add_code_language_to_scenes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create ralph_pipeline_events table + indexes."""
    conn = op.get_bind()
    dialect = conn.dialect.name

    def _table_exists() -> bool:
        if dialect == "postgresql":
            result = conn.execute(
                sa.text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = 'ralph_pipeline_events'"
                )
            ).fetchone()
            return result is not None
        return False

    if _table_exists():
        return

    jsonb_col = sa.dialects.postgresql.JSONB if dialect == "postgresql" else sa.JSON

    op.create_table(
        "ralph_pipeline_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("ticket_id", sa.String(32), nullable=False),
        sa.Column("iteration", sa.Integer, nullable=False),
        sa.Column("loop_run_id", sa.String(64), nullable=False),
        sa.Column("pr_number", sa.Integer, nullable=True),
        sa.Column("phase", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("duration_sec", sa.Integer, nullable=True),
        sa.Column("context", jsonb_col, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()") if dialect == "postgresql" else sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_ralph_pipeline_events_ticket_created",
        "ralph_pipeline_events",
        ["ticket_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_ralph_pipeline_events_loop_run",
        "ralph_pipeline_events",
        ["loop_run_id"],
    )
    op.create_index(
        "ix_ralph_pipeline_events_phase_status",
        "ralph_pipeline_events",
        ["phase", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_ralph_pipeline_events_phase_status", table_name="ralph_pipeline_events")
    op.drop_index("ix_ralph_pipeline_events_loop_run", table_name="ralph_pipeline_events")
    op.drop_index("ix_ralph_pipeline_events_ticket_created", table_name="ralph_pipeline_events")
    op.drop_table("ralph_pipeline_events")
