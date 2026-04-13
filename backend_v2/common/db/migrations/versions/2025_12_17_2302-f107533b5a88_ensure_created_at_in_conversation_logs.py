"""ensure_created_at_in_conversation_logs

Revision ID: f107533b5a88
Revises: 40301e215452
Create Date: 2025-12-17 23:02:30.196653

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f107533b5a88'
down_revision: Union[str, None] = '40301e215452'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ensure created_at column exists in conversation_logs table.
    
    This migration is idempotent and safe to run multiple times.
    It adds the created_at column if it doesn't exist, which may have been
    missed if the database was migrated through a different path.
    """
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
    """Remove created_at column from conversation_logs table if it exists."""
    conn = op.get_bind()
    
    # Check if column exists
    result = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'conversation_logs' AND column_name = 'created_at'
    """))
    column_exists = result.fetchone() is not None
    
    if column_exists:
        conn.execute(sa.text("""
            ALTER TABLE conversation_logs 
            DROP COLUMN created_at
        """))

