"""add_instance_data_to_student_simulation_instances

Revision ID: 3f9b0c4b2e1d
Revises: 7099884d5945
Create Date: 2025-12-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f9b0c4b2e1d'
down_revision: Union[str, None] = '7099884d5945'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add instance_data JSON column to student_simulation_instances."""
    op.add_column(
        'student_simulation_instances',
        sa.Column('instance_data', sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    """Remove instance_data column from student_simulation_instances."""
    op.drop_column('student_simulation_instances', 'instance_data')

