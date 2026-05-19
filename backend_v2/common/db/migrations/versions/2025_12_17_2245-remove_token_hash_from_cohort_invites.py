"""remove_token_hash_from_cohort_invites

Revision ID: a1b2c3d4e5f6
Revises: 7b0d3fcaa371
Create Date: 2025-12-17 22:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '7b0d3fcaa371'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use raw SQL with IF EXISTS to safely drop constraints and indexes
    # This avoids transaction abort issues if objects don't exist
    conn = op.get_bind()
    
    # Drop unique constraint if it exists
    conn.execute(sa.text("""
        DO $$ 
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint 
                WHERE conname = 'unique_token_hash' 
                AND conrelid = 'cohort_invites'::regclass
            ) THEN
                ALTER TABLE cohort_invites DROP CONSTRAINT unique_token_hash;
            END IF;
        END $$;
    """))
    
    # Drop indexes if they exist
    conn.execute(sa.text("""
        DO $$ 
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE tablename = 'cohort_invites' 
                AND indexname = 'idx_cohort_invites_token_hash'
            ) THEN
                DROP INDEX idx_cohort_invites_token_hash;
            END IF;
        END $$;
    """))
    
    conn.execute(sa.text("""
        DO $$ 
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_indexes 
                WHERE tablename = 'cohort_invites' 
                AND indexname = 'ix_cohort_invites_token_hash'
            ) THEN
                DROP INDEX ix_cohort_invites_token_hash;
            END IF;
        END $$;
    """))
    
    # Drop the token_hash column if it exists
    conn.execute(sa.text("""
        DO $$ 
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'cohort_invites' 
                AND column_name = 'token_hash'
            ) THEN
                ALTER TABLE cohort_invites DROP COLUMN token_hash;
            END IF;
        END $$;
    """))


def downgrade() -> None:
    # Re-add the token_hash column
    op.add_column(
        'cohort_invites',
        sa.Column('token_hash', sa.String(length=64), nullable=False, server_default='')
    )
    
    # Re-add indexes
    op.create_index('idx_cohort_invites_token_hash', 'cohort_invites', ['token_hash'], unique=False)
    op.create_index(op.f('ix_cohort_invites_token_hash'), 'cohort_invites', ['token_hash'], unique=True)
    
    # Re-add unique constraint
    op.create_unique_constraint('unique_token_hash', 'cohort_invites', ['token_hash'])
