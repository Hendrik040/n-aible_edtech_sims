"""add composite indexes for performance

Revision ID: add_composite_indexes
Revises: 7f4569889848
Create Date: 2025-12-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_composite_indexes'
down_revision = '7f4569889848'  # Revises the add_session_id_to_conversation_logs migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add composite indexes for CohortStudent to optimize common queries
    # These indexes help with queries that filter by student_id + status or cohort_id + status
    op.create_index(
        'idx_cohort_students_student_status',
        'cohort_students',
        ['student_id', 'status'],
        unique=False
    )
    op.create_index(
        'idx_cohort_students_cohort_status',
        'cohort_students',
        ['cohort_id', 'status'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('idx_cohort_students_cohort_status', table_name='cohort_students')
    op.drop_index('idx_cohort_students_student_status', table_name='cohort_students')

