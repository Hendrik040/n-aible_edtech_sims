"""Add code_language column to simulation_scenes

Revision ID: add_code_language_to_scenes
Revises: add_prompt_traces
Create Date: 2026-04-06 10:00:00.000000

Adds a code_language column to simulation_scenes so each code challenge
scene can specify whether it uses Python or R. Defaults to 'python' for
backward compatibility with all existing scenes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision: str = "add_code_language_to_scenes"
down_revision: Union[str, None] = "add_prompt_traces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "simulation_scenes",
        sa.Column("code_language", sa.String(20), nullable=False, server_default="python"),
    )


def downgrade() -> None:
    op.drop_column("simulation_scenes", "code_language")
