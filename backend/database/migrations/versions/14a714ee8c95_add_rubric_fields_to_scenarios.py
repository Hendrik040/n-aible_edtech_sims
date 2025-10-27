"""add_rubric_fields_to_scenarios

Revision ID: 14a714ee8c95
Revises: 93db1708c703
Create Date: 2025-10-19 15:14:02.351734

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '14a714ee8c95'
down_revision = '93db1708c703'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add rubric-specific fields to scenarios table
    op.add_column('scenarios', sa.Column('rubric_title', sa.String(), nullable=True))
    op.add_column('scenarios', sa.Column('rubric_criteria', sa.JSON(), nullable=True))
    op.add_column('scenarios', sa.Column('rubric_performance_levels', sa.JSON(), nullable=True))
    op.add_column('scenarios', sa.Column('rubric_total_points', sa.Integer(), nullable=True, default=100))


def downgrade() -> None:
    # Remove rubric-specific fields from scenarios table
    op.drop_column('scenarios', 'rubric_total_points')
    op.drop_column('scenarios', 'rubric_performance_levels')
    op.drop_column('scenarios', 'rubric_criteria')
    op.drop_column('scenarios', 'rubric_title')
