"""add_missing_columns_to_agent_sessions

Revision ID: c49f8a04ceb1
Revises: 14eb31ccda01
Create Date: 2025-12-12 20:50:43.869443

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c49f8a04ceb1'
down_revision: Union[str, None] = '14eb31ccda01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add missing columns to agent_sessions table
    # Check if columns exist first to avoid errors if migration is run multiple times
    op.execute("""
        DO $$
        BEGIN
            -- Add persona_id column if it doesn't exist
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='agent_sessions' AND column_name='persona_id'
            ) THEN
                ALTER TABLE agent_sessions 
                ADD COLUMN persona_id INTEGER 
                REFERENCES scenario_personas(id);
            END IF;
            
            -- Add session_type column if it doesn't exist
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='agent_sessions' AND column_name='session_type'
            ) THEN
                ALTER TABLE agent_sessions 
                ADD COLUMN session_type VARCHAR;
            END IF;
            
            -- Add last_accessed_at column if it doesn't exist
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='agent_sessions' AND column_name='last_accessed_at'
            ) THEN
                ALTER TABLE agent_sessions 
                ADD COLUMN last_accessed_at TIMESTAMP WITH TIME ZONE;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Remove the columns we added
    op.drop_column('agent_sessions', 'last_accessed_at', if_exists=True)
    op.drop_column('agent_sessions', 'session_type', if_exists=True)
    op.drop_column('agent_sessions', 'persona_id', if_exists=True)
