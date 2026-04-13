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
    # Use raw SQL to safely check and add column to avoid transaction issues
    conn = op.get_bind()
    
    # Check if column exists using raw SQL
    result = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'conversation_logs' AND column_name = 'created_at'
    """))
    column_exists = result.fetchone() is not None
    
    if not column_exists:
        # Add column as nullable first with default
        conn.execute(sa.text("""
            ALTER TABLE conversation_logs 
            ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        """))
        
        # Update existing rows to have created_at = timestamp (if timestamp column exists)
        try:
            conn.execute(sa.text("""
                UPDATE conversation_logs 
                SET created_at = timestamp 
                WHERE created_at IS NULL
            """))
        except Exception:
            # If timestamp column doesn't exist or update fails, created_at will use default
            pass
        
        # Now make it NOT NULL
        conn.execute(sa.text("""
            ALTER TABLE conversation_logs 
            ALTER COLUMN created_at SET NOT NULL
        """))


def downgrade() -> None:
    # Remove created_at column from conversation_logs table if it exists
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('conversation_logs')]

    if 'created_at' in columns:
        op.drop_column('conversation_logs', 'created_at')
