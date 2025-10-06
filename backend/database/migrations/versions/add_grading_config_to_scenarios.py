"""add_grading_config_to_scenarios

Revision ID: 8a1b2c3d4e5f
Revises: 7fcfe7937fd1
Create Date: 2025-01-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8a1b2c3d4e5f'
down_revision = '7fcfe7937fd1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add grading_config column to scenarios table
    op.add_column('scenarios', sa.Column('grading_config', sa.JSON(), nullable=True))
    
    # Add grading_config_completed column to scenarios table
    op.add_column('scenarios', sa.Column('grading_config_completed', sa.Boolean(), nullable=True, default=False))


def downgrade() -> None:
    # Remove grading_config_completed column from scenarios table
    op.drop_column('scenarios', 'grading_config_completed')
    
    # Remove grading_config column from scenarios table
    op.drop_column('scenarios', 'grading_config')
