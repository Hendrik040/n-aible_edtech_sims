"""make_user_progress_id_nullable_in_student_instances

Revision ID: make_user_progress_nullable
Revises: add_cascade_delete_user_progress
Create Date: 2025-12-19 06:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
import logging


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
    dialect_name = conn.dialect.name
    
    # 1. Make user_progress_id nullable in student_simulation_instances
    if dialect_name == 'postgresql':
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
    elif dialect_name == 'sqlite':
        # SQLite: Use batch_alter_table for column modifications
        with op.batch_alter_table('student_simulation_instances', schema=None) as batch_op:
            batch_op.alter_column(
                'user_progress_id',
                existing_type=sa.Integer(),
                nullable=True
            )
    else:
        # For other databases, try direct alter
        op.alter_column(
            'student_simulation_instances',
            'user_progress_id',
            existing_type=sa.Integer(),
            nullable=True
        )
    
    # 2. Ensure progress_data column exists in scene_progress table
    # This migration might not be in the chain, so we ensure it exists here
    if dialect_name == 'postgresql':
        # PostgreSQL: Use DO block for conditional column addition
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
    elif dialect_name == 'sqlite':
        # SQLite: Check if column exists using PRAGMA table_info
        result = conn.execute(sa.text("PRAGMA table_info(scene_progress)"))
        columns = [row[1] for row in result.fetchall()]  # Column name is at index 1
        
        if 'progress_data' not in columns:
            # SQLite doesn't support JSON type directly, use TEXT
            with op.batch_alter_table('scene_progress', schema=None) as batch_op:
                batch_op.add_column(sa.Column('progress_data', sa.Text(), nullable=True))
    else:
        # For other databases, check if column exists before adding
        column_exists = False
        try:
            inspector = inspect(conn)
            columns = [col['name'] for col in inspector.get_columns('scene_progress')]
            column_exists = 'progress_data' in columns
        except Exception as e:
            # If inspector fails, fall back to narrow exception handling
            # Log the error but try to add column anyway (will catch specific errors)
            logging.warning(f"Failed to check column existence using inspector: {e!s}")
            column_exists = False  # Assume column doesn't exist, try to add it
        
        if not column_exists:
            try:
                op.add_column('scene_progress', sa.Column('progress_data', sa.JSON(), nullable=True))
            except Exception as e:
                # Only catch specific "column already exists" errors
                error_msg = str(e).lower()
                if 'already exists' in error_msg or 'duplicate column' in error_msg:
                    # Column already exists, which is fine - migration can continue
                    logging.info("Column progress_data already exists in scene_progress, skipping")
                else:
                    # Unexpected error (permission, syntax, connection, etc.) - log and re-raise
                    logging.error(f"Unexpected error adding progress_data column: {e!r}", exc_info=True)
                    raise


def downgrade() -> None:
    """
    Revert user_progress_id to NOT NULL.
    
    WARNING: This will fail if there are any NULL values in the column.
    """
    conn = op.get_bind()
    dialect_name = conn.dialect.name
    
    if dialect_name == 'sqlite':
        # SQLite: Use batch_alter_table for column modifications
        with op.batch_alter_table('student_simulation_instances', schema=None) as batch_op:
            batch_op.alter_column(
                'user_progress_id',
                existing_type=sa.Integer(),
                nullable=False,
                existing_nullable=True
            )
    else:
        # PostgreSQL and other databases: direct alter
        op.alter_column(
            'student_simulation_instances',
            'user_progress_id',
            existing_type=sa.Integer(),
            nullable=False,
            existing_nullable=True  # Current state is nullable, we're changing it back
        )
