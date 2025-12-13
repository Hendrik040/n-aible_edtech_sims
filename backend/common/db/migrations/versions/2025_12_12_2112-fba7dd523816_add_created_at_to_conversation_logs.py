"""add_created_at_to_conversation_logs

Revision ID: fba7dd523816
Revises: c49f8a04ceb1
Create Date: 2025-12-12 21:12:14.472667

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'fba7dd523816'
down_revision: Union[str, None] = 'c49f8a04ceb1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add created_at column to conversation_logs table if it doesn't exist
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('conversation_logs')]
    
    if 'created_at' not in columns:
        # Add column as nullable first
        op.add_column('conversation_logs', 
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True)
        )
        # Update existing rows to have created_at = timestamp
        op.execute("""
            UPDATE conversation_logs 
            SET created_at = timestamp 
            WHERE created_at IS NULL
        """)
        # Now make it NOT NULL
        op.alter_column('conversation_logs', 'created_at', nullable=False)


def downgrade() -> None:
    # Remove created_at column from conversation_logs table if it exists
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('conversation_logs')]

    if 'created_at' in columns:
        op.drop_column('conversation_logs', 'created_at')
