"""Add notifications table

Revision ID: add_notifications_table
Revises: add_cascade_delete_to_user_progress_fks
Create Date: 2025-12-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_notifications_table'
down_revision: Union[str, None] = 'add_cascade_delete_to_user_progress_fks'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
    
    # Create indexes
    op.create_index('ix_notifications_id', 'notifications', ['id'])
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    op.create_index('ix_notifications_type', 'notifications', ['type'])
    op.create_index('ix_notifications_is_read', 'notifications', ['is_read'])
    op.create_index('ix_notifications_created_at', 'notifications', ['created_at'])
    op.create_index('idx_notifications_user_read', 'notifications', ['user_id', 'is_read'])
    op.create_index('idx_notifications_user_created', 'notifications', ['user_id', 'created_at'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_notifications_user_created', 'notifications')
    op.drop_index('idx_notifications_user_read', 'notifications')
    op.drop_index('ix_notifications_created_at', 'notifications')
    op.drop_index('ix_notifications_is_read', 'notifications')
    op.drop_index('ix_notifications_type', 'notifications')
    op.drop_index('ix_notifications_user_id', 'notifications')
    op.drop_index('ix_notifications_id', 'notifications')
    
    # Drop table
    op.drop_table('notifications')

