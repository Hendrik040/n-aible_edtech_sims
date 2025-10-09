"""allow_null_user_progress_id_in_student_instances

Revision ID: 1a44d8443d3f
Revises: 7e97818b7d8b
Create Date: 2025-10-08 16:30:25.897849

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1a44d8443d3f'
down_revision = '7e97818b7d8b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Allow NULL values for user_progress_id since instances are created before simulation starts
    op.alter_column('student_simulation_instances', 'user_progress_id',
                    existing_type=sa.INTEGER(),
                    nullable=True)


def downgrade() -> None:
    # Revert to NOT NULL constraint
    op.alter_column('student_simulation_instances', 'user_progress_id',
                    existing_type=sa.INTEGER(),
                    nullable=False)
