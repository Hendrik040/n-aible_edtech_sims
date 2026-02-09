"""add code challenge fields to simulation_scenes and user_progress

Revision ID: add_code_challenge_fields
Revises: add_conv_logs_indexes
Create Date: 2026-02-08

Adds fields for Daytona code sandbox integration:
- simulation_scenes: scene_type, data_files, starter_code, code_grading_criteria, reference_files
- user_progress: sandbox_id
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_code_challenge_fields'
down_revision = 'add_conv_logs_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add code challenge columns to simulation_scenes
    op.add_column('simulation_scenes', sa.Column('scene_type', sa.String(50), server_default='conversation', nullable=False))
    op.add_column('simulation_scenes', sa.Column('data_files', sa.JSON(), nullable=True))
    op.add_column('simulation_scenes', sa.Column('starter_code', sa.Text(), nullable=True))
    op.add_column('simulation_scenes', sa.Column('code_grading_criteria', sa.JSON(), nullable=True))
    op.add_column('simulation_scenes', sa.Column('reference_files', sa.JSON(), nullable=True))

    # Add sandbox_id to user_progress
    op.add_column('user_progress', sa.Column('sandbox_id', sa.String(255), nullable=True))


def downgrade() -> None:
    # Remove sandbox_id from user_progress
    op.drop_column('user_progress', 'sandbox_id')

    # Remove code challenge columns from simulation_scenes
    op.drop_column('simulation_scenes', 'reference_files')
    op.drop_column('simulation_scenes', 'code_grading_criteria')
    op.drop_column('simulation_scenes', 'starter_code')
    op.drop_column('simulation_scenes', 'data_files')
    op.drop_column('simulation_scenes', 'scene_type')
