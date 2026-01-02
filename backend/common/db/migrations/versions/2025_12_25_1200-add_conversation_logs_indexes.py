"""add conversation_logs indexes for TTFB optimization

Revision ID: add_conv_logs_indexes
Revises: df3677caaba1
Create Date: 2025-12-25

Optimizes conversation history queries by adding indexes for:
- Composite lookup (user_progress_id, scene_id, session_id)
- Message ordering (user_progress_id, message_order)
- Session ID prefix matching (session_id)

Expected improvement: 100-300ms → 5-20ms for conversation history queries.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_conv_logs_indexes'
down_revision = 'df3677caaba1'  # Latest migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if indexes already exist before creating
    conn = op.get_bind()
    
    # Index 1: Composite index for the main query pattern
    # Covers: WHERE user_progress_id = ? AND scene_id = ? AND session_id = ?
    result = conn.execute(
        sa.text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE indexname = 'idx_conversation_logs_progress_scene_session'
            )
        """)
    )
    if not result.scalar():
        op.create_index(
            'idx_conversation_logs_progress_scene_session',
            'conversation_logs',
            ['user_progress_id', 'scene_id', 'session_id'],
            unique=False
        )
    
    # Index 2: Index for ORDER BY message_order DESC queries
    result = conn.execute(
        sa.text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE indexname = 'idx_conversation_logs_progress_order'
            )
        """)
    )
    if not result.scalar():
        op.create_index(
            'idx_conversation_logs_progress_order',
            'conversation_logs',
            ['user_progress_id', 'message_order'],
            unique=False
        )
    
    # Index 3: Standalone session_id index for LIKE prefix queries
    # PostgreSQL can use btree indexes for prefix LIKE queries (e.g., 'abc%')
    result = conn.execute(
        sa.text("""
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE indexname = 'idx_conversation_logs_session_id'
            )
        """)
    )
    if not result.scalar():
        op.create_index(
            'idx_conversation_logs_session_id',
            'conversation_logs',
            ['session_id'],
            unique=False
        )


def downgrade() -> None:
    # Drop indexes in reverse order
    conn = op.get_bind()
    
    # Check and drop each index if it exists
    for index_name in [
        'idx_conversation_logs_session_id',
        'idx_conversation_logs_progress_order',
        'idx_conversation_logs_progress_scene_session'
    ]:
        result = conn.execute(
            sa.text(f"""
                SELECT EXISTS (
                    SELECT 1 FROM pg_indexes 
                    WHERE indexname = '{index_name}'
                )
            """)
        )
        if result.scalar():
            op.drop_index(index_name, table_name='conversation_logs')




