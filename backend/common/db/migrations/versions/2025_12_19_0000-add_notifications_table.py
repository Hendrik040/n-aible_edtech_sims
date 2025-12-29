"""Add notifications table

Revision ID: add_notifications_table
Revises: add_cascade_delete_user_progress
Create Date: 2025-12-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_notifications_table'
down_revision: Union[str, None] = 'add_cascade_delete_user_progress'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create notifications table if it doesn't already exist.
    
    This migration is idempotent - it checks if the table exists before creating it
    to handle cases where the table was created manually or in a previous migration attempt.
    """
    conn = op.get_bind()
    
    # Check if table already exists
    result = conn.execute(
        sa.text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'notifications'
            )
        """)
    )
    table_exists = result.scalar()
    
    if not table_exists:
        # Create notifications table
        op.create_table(
            'notifications',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('type', sa.String(50), nullable=False),
            sa.Column('title', sa.String(255), nullable=False),
            sa.Column('message', sa.Text(), nullable=False),
            sa.Column('data', sa.JSON(), nullable=True),
            sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
    
    # Create indexes if they don't exist
    indexes_to_create = [
        ('ix_notifications_user_id', ['user_id']),
        ('ix_notifications_type', ['type']),
        ('ix_notifications_is_read', ['is_read']),
        ('ix_notifications_created_at', ['created_at']),
        ('idx_notifications_user_read', ['user_id', 'is_read']),
        ('idx_notifications_user_created', ['user_id', 'created_at']),
    ]
    
    for index_name, columns in indexes_to_create:
        # Check if index exists
        result = conn.execute(
            sa.text(f"""
                SELECT EXISTS (
                    SELECT 1 FROM pg_indexes 
                    WHERE indexname = '{index_name}'
                )
            """)
        )
        index_exists = result.scalar()
        
        if not index_exists:
            op.create_index(index_name, 'notifications', columns)


def downgrade() -> None:
    """Remove notifications table and indexes."""
    conn = op.get_bind()
    
    # Check if table exists before dropping
    result = conn.execute(
        sa.text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'notifications'
            )
        """)
    )
    table_exists = result.scalar()
    
    if table_exists:
        # Drop indexes first (use IF EXISTS for safety)
        indexes_to_drop = [
            'idx_notifications_user_created',
            'idx_notifications_user_read',
            'ix_notifications_created_at',
            'ix_notifications_is_read',
            'ix_notifications_type',
            'ix_notifications_user_id',
        ]
        
        for index_name in indexes_to_drop:
            conn.execute(sa.text(f"DROP INDEX IF EXISTS {index_name}"))
        
        # Drop table
        op.drop_table('notifications')
