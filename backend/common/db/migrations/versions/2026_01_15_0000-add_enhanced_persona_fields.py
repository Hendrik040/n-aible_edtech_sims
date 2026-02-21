"""add enhanced persona fields

Revision ID: add_enhanced_persona_fields
Revises: add_conv_logs_indexes
Create Date: 2026-01-15

Note: This migration was applied directly to the database before the migration
file was committed. The schema already contains all expected columns, so
upgrade/downgrade are no-ops to keep the Alembic revision history consistent.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_enhanced_persona_fields'
down_revision = 'add_conv_logs_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Schema changes were already applied to the database.
    # This stub exists to keep the Alembic revision chain intact.
    pass


def downgrade() -> None:
    # No-op: original changes were applied outside of Alembic.
    pass
