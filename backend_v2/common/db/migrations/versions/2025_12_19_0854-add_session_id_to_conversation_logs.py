"""add_session_id_to_conversation_logs

Revision ID: 7f4569889848
Revises: make_user_progress_nullable
Create Date: 2025-12-19 08:54:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f4569889848'
down_revision: Union[str, None] = 'make_user_progress_nullable'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add session_id column to conversation_logs for session isolation.
    
    This migration adds session_id to enable proper session-based memory isolation
    and prevent concurrency issues when multiple users or sessions access the same
    user_progress_id and scene_id combination.
    
    For existing rows without session_id, we generate a unique session_id based on
    user_progress_id and scene_id to maintain data integrity.
    """
    conn = op.get_bind()
    
    # Check if column exists
    result = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'conversation_logs' AND column_name = 'session_id'
    """))
    column_exists = result.fetchone() is not None
    
    if not column_exists:
        # Step 1: Add session_id column as nullable first
        conn.execute(sa.text("""
            ALTER TABLE conversation_logs 
            ADD COLUMN session_id VARCHAR
        """))
        
        # Step 2: Generate session_ids for existing rows
        # Use a deterministic approach: user_progress_id_scene_id_timestamp
        # This ensures each user_progress+scene combination gets a unique session_id
        conn.execute(sa.text("""
            UPDATE conversation_logs
            SET session_id = 'legacy_' || COALESCE(user_progress_id::text, 'none') || '_' || COALESCE(scene_id::text, 'none') || '_' ||
                COALESCE(EXTRACT(EPOCH FROM timestamp)::bigint::text, EXTRACT(EPOCH FROM created_at)::bigint::text, '0')
            WHERE session_id IS NULL
        """))
        
        # Step 3: Make session_id NOT NULL
        conn.execute(sa.text("""
            ALTER TABLE conversation_logs 
            ALTER COLUMN session_id SET NOT NULL
        """))
        
        # Step 4: Create index for efficient session-based queries
        conn.execute(sa.text("""
            CREATE INDEX IF NOT EXISTS ix_conversation_logs_session_id 
            ON conversation_logs(session_id)
        """))
        
        # Step 5: Create composite index for common query pattern: user_progress_id + scene_id + session_id
        conn.execute(sa.text("""
            CREATE INDEX IF NOT EXISTS ix_conversation_logs_user_scene_session 
            ON conversation_logs(user_progress_id, scene_id, session_id)
        """))


def downgrade() -> None:
    """Remove session_id column from conversation_logs table."""
    conn = op.get_bind()
    
    # Check if column exists
    result = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'conversation_logs' AND column_name = 'session_id'
    """))
    column_exists = result.fetchone() is not None
    
    if column_exists:
        # Drop indexes first
        conn.execute(sa.text("""
            DROP INDEX IF EXISTS ix_conversation_logs_user_scene_session
        """))
        conn.execute(sa.text("""
            DROP INDEX IF EXISTS ix_conversation_logs_session_id
        """))
        
        # Drop column
        conn.execute(sa.text("""
            ALTER TABLE conversation_logs 
            DROP COLUMN session_id
        """))
