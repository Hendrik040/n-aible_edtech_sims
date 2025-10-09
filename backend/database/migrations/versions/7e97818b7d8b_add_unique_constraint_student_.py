"""add_unique_constraint_student_simulation_instances

Revision ID: 7e97818b7d8b
Revises: da4c671ffd49
Create Date: 2025-10-08 16:17:28.846789

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7e97818b7d8b'
down_revision = 'da4c671ffd49'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add unique constraint to prevent duplicate student simulation instances
    op.create_unique_constraint(
        'unique_student_cohort_assignment',
        'student_simulation_instances',
        ['student_id', 'cohort_assignment_id']
    )


def downgrade() -> None:
    # Remove unique constraint
    op.drop_constraint(
        'unique_student_cohort_assignment',
        'student_simulation_instances',
        type_='unique'
    )
