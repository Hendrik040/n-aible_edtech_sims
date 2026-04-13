"""add_progress_data_to_scene_progress

Revision ID: add_progress_data_to_scene_progress
Revises: fba7dd523816
Create Date: 2025-12-12 21:40:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2140addprogdata'
down_revision: Union[str, None] = 'fba7dd523816'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add progress_data column to scene_progress table if it doesn't exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'scene_progress' AND column_name = 'progress_data'
            ) THEN
                ALTER TABLE scene_progress ADD COLUMN progress_data JSON;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Remove progress_data column
    op.drop_column('scene_progress', 'progress_data')

