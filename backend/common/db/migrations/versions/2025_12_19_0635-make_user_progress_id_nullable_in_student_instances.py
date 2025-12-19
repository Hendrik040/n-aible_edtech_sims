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
    Also ensure progress_data column exists in scene_progress table.
    
    Instances are created when simulations are assigned to cohorts, but
    user_progress_id is only set when a student actually starts the simulation.
    Therefore, this column must be nullable.
    """
    conn = op.get_bind()
    
    # 1. Make user_progress_id nullable in student_simulation_instances
    # Check if column exists and is NOT NULL before altering
    result = conn.execute(sa.text("""
        SELECT is_nullable 
        FROM information_schema.columns 
        WHERE table_name = 'student_simulation_instances' 
        AND column_name = 'user_progress_id'
    """))
    row = result.first()
    if row and row[0] == 'NO':  # Column exists and is NOT NULL
        op.alter_column(
            'student_simulation_instances',
            'user_progress_id',
            existing_type=sa.Integer(),
            nullable=True
        )
    
    # 2. Ensure progress_data column exists in scene_progress table
    # This migration might not be in the chain, so we ensure it exists here
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'scene_progress' AND column_name = 'progress_data'
            ) THEN
                ALTER TABLE scene_progress ADD COLUMN progress_data JSON;
            END IF;
        END $$;
    """))


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
