"""fix_cohort_table_constraints

Revision ID: 6f6b3caca601
Revises: d8d9e0ec814b
Create Date: 2025-12-07 13:48:04.347580

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6f6b3caca601'
down_revision: Union[str, None] = 'd8d9e0ec814b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Fix NOT NULL constraints on cohort tables
    # Note: Using server_default to handle existing NULL values
    
    # cohorts table - set defaults for boolean fields
    op.alter_column('cohorts', 'auto_approve',
                   existing_type=sa.BOOLEAN(),
                   nullable=False,
                   server_default=sa.text('true'))
    op.alter_column('cohorts', 'allow_self_enrollment',
                   existing_type=sa.BOOLEAN(),
                   nullable=False,
                   server_default=sa.text('false'))
    op.alter_column('cohorts', 'is_active',
                   existing_type=sa.BOOLEAN(),
                   nullable=False,
                   server_default=sa.text('true'))
    op.alter_column('cohorts', 'created_at',
                   existing_type=postgresql.TIMESTAMP(timezone=True),
                   nullable=False,
                   existing_server_default=sa.text('now()'))
    op.alter_column('cohorts', 'updated_at',
                   existing_type=postgresql.TIMESTAMP(timezone=True),
                   nullable=False,
                   existing_server_default=sa.text('now()'))
    
    # cohort_students table
    op.alter_column('cohort_students', 'status',
                   existing_type=sa.VARCHAR(),
                   nullable=False,
                   server_default=sa.text("'pending'::character varying"))
    op.alter_column('cohort_students', 'enrollment_date',
                   existing_type=postgresql.TIMESTAMP(timezone=True),
                   nullable=False,
                   existing_server_default=sa.text('now()'))
    op.alter_column('cohort_students', 'created_at',
                   existing_type=postgresql.TIMESTAMP(timezone=True),
                   nullable=False,
                   existing_server_default=sa.text('now()'))
    op.alter_column('cohort_students', 'updated_at',
                   existing_type=postgresql.TIMESTAMP(timezone=True),
                   nullable=False,
                   existing_server_default=sa.text('now()'))
    
    # cohort_simulations table
    op.alter_column('cohort_simulations', 'assigned_at',
                   existing_type=postgresql.TIMESTAMP(timezone=True),
                   nullable=False,
                   existing_server_default=sa.text('now()'))
    op.alter_column('cohort_simulations', 'is_required',
                   existing_type=sa.BOOLEAN(),
                   nullable=False,
                   server_default=sa.text('false'))
    op.alter_column('cohort_simulations', 'created_at',
                   existing_type=postgresql.TIMESTAMP(timezone=True),
                   nullable=False,
                   existing_server_default=sa.text('now()'))
    op.alter_column('cohort_simulations', 'updated_at',
                   existing_type=postgresql.TIMESTAMP(timezone=True),
                   nullable=False,
                   existing_server_default=sa.text('now()'))


def downgrade() -> None:
    # Revert NOT NULL constraints back to nullable
    op.alter_column('cohort_simulations', 'updated_at', nullable=True)
    op.alter_column('cohort_simulations', 'created_at', nullable=True)
    op.alter_column('cohort_simulations', 'is_required', nullable=True)
    op.alter_column('cohort_simulations', 'assigned_at', nullable=True)
    op.alter_column('cohort_students', 'updated_at', nullable=True)
    op.alter_column('cohort_students', 'created_at', nullable=True)
    op.alter_column('cohort_students', 'enrollment_date', nullable=True)
    op.alter_column('cohort_students', 'status', nullable=True)
    op.alter_column('cohorts', 'updated_at', nullable=True)
    op.alter_column('cohorts', 'created_at', nullable=True)
    op.alter_column('cohorts', 'is_active', nullable=True)
    op.alter_column('cohorts', 'allow_self_enrollment', nullable=True)
    op.alter_column('cohorts', 'auto_approve', nullable=True)

