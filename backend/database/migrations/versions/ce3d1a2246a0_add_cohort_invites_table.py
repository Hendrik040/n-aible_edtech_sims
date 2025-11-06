"""add_cohort_invites_table

Revision ID: ce3d1a2246a0
Revises: c2f59a5f1c59
Create Date: 2025-01-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ce3d1a2246a0'
down_revision = 'c2f59a5f1c59'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create cohort_invites table
    op.create_table(
        'cohort_invites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cohort_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=255), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('invite_type', sa.String(length=20), nullable=False, server_default='SINGLE_USE'),
        sa.Column('max_uses', sa.Integer(), nullable=True),
        sa.Column('uses_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('used_by', sa.Integer(), nullable=True),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['cohort_id'], ['cohorts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['used_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token', name='unique_token'),
        sa.UniqueConstraint('token_hash', name='unique_token_hash')
    )
    
    # Create indexes
    op.create_index('idx_cohort_invites_cohort_id', 'cohort_invites', ['cohort_id'])
    op.create_index('idx_cohort_invites_token', 'cohort_invites', ['token'])
    op.create_index('idx_cohort_invites_token_hash', 'cohort_invites', ['token_hash'])
    op.create_index('idx_cohort_invites_type', 'cohort_invites', ['invite_type'])
    op.create_index('idx_cohort_invites_created_by', 'cohort_invites', ['created_by'])
    op.create_index('idx_cohort_invites_expires_at', 'cohort_invites', ['expires_at'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('idx_cohort_invites_expires_at', table_name='cohort_invites')
    op.drop_index('idx_cohort_invites_created_by', table_name='cohort_invites')
    op.drop_index('idx_cohort_invites_type', table_name='cohort_invites')
    op.drop_index('idx_cohort_invites_token_hash', table_name='cohort_invites')
    op.drop_index('idx_cohort_invites_token', table_name='cohort_invites')
    op.drop_index('idx_cohort_invites_cohort_id', table_name='cohort_invites')
    
    # Drop table
    op.drop_table('cohort_invites')

