"""make_user_progress_id_nullable_in_student_instances

Revision ID: make_user_progress_nullable
Revises: add_cascade_delete_user_progress
Create Date: 2025-12-19 06:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'make_user_progress_nullable'
down_revision: Union[str, None] = 'add_cascade_delete_user_progress'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Make user_progress_id nullable in student_simulation_instances table.
    
    Instances are created when simulations are assigned to cohorts, but
    user_progress_id is only set when a student actually starts the simulation.
    Therefore, this column must be nullable.
    """
    # Alter the column to allow NULL values
    op.alter_column(
        'student_simulation_instances',
        'user_progress_id',
        existing_type=sa.Integer(),
        nullable=True,
        existing_nullable=False  # Current state is NOT NULL, we're changing it
    )


def downgrade() -> None:
    """
    Revert user_progress_id to NOT NULL.
    
    WARNING: This will fail if there are any NULL values in the column.
    """
    # First, set any NULL values to a default (this will fail if there are NULLs and we can't set a default)
    # For safety, we'll just try to alter it back
    op.alter_column(
        'student_simulation_instances',
        'user_progress_id',
        existing_type=sa.Integer(),
        nullable=False,
        existing_nullable=True  # Current state is nullable, we're changing it back
    )
