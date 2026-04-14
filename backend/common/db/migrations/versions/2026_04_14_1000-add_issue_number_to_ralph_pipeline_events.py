"""Add issue_number to ralph_pipeline_events

Revision ID: add_issue_number_to_ralph_pipeline_events
Revises: add_ralph_pipeline_events
Create Date: 2026-04-14 10:00:00.000000

Adds a nullable ``issue_number`` column to ``ralph_pipeline_events`` so
the admin dashboard can link each ticket row back to its GitHub plan
issue. No backfill — rows predating this column render as plain text
in the grid.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision: str = "add_issue_number_to_ralph_pipeline_events"
down_revision: Union[str, None] = "add_ralph_pipeline_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name

    if dialect == "postgresql":
        existing = conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'ralph_pipeline_events' "
                "AND column_name = 'issue_number'"
            )
        ).fetchone()
        if existing:
            return

    op.add_column(
        "ralph_pipeline_events",
        sa.Column("issue_number", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ralph_pipeline_events", "issue_number")
