"""Add code_language column to simulation_scenes

Revision ID: add_code_language
Revises: add_prompt_traces
Create Date: 2026-04-06 00:00:00.000000

Adds a code_language column to simulation_scenes so each code challenge
scene can specify which language to use (python or r). Defaults to 'python'
for backward compatibility.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_code_language"
down_revision: Union[str, None] = "add_prompt_traces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table: str, column: str) -> bool:
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ),
        {"table": table, "column": column},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "simulation_scenes", "code_language"):
        op.add_column(
            "simulation_scenes",
            sa.Column("code_language", sa.String(20), server_default="python", nullable=False),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "simulation_scenes", "code_language"):
        op.drop_column("simulation_scenes", "code_language")
