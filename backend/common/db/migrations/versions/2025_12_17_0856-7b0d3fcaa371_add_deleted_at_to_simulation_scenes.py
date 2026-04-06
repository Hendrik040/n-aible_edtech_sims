"""add_deleted_at_to_simulation_scenes

Revision ID: 7b0d3fcaa371
Revises: 9f0b2b0c2f0f
Create Date: 2025-12-17 08:56:10.673328

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7b0d3fcaa371'
down_revision: Union[str, None] = '9f0b2b0c2f0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add deleted_at column to simulation_scenes table for soft-delete support
    op.add_column(
        'simulation_scenes',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    # Remove deleted_at column from simulation_scenes table
    op.drop_column('simulation_scenes', 'deleted_at')

