"""make_cohort_assignment_id_nullable_in_student_simulation_instances

Revision ID: a4de75a977bc
Revises: 2140addprogdata
Create Date: 2025-12-12 22:32:30.468996

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4de75a977bc'
down_revision: Union[str, None] = '2140addprogdata'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make cohort_assignment_id nullable to support test simulations
    # Test simulations (professor/test-simulations) don't have cohort assignments
    
    # Use raw SQL to find and drop FK constraint, then alter column
    connection = op.get_bind()
    
    # Find foreign key constraint name
    fk_result = connection.execute(
        sa.text("""
            SELECT tc.constraint_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'student_simulation_instances'
                AND tc.constraint_type = 'FOREIGN KEY'
                AND kcu.column_name = 'cohort_assignment_id'
        """)
    )
    fk_row = fk_result.fetchone()
    
    if fk_row:
        fk_name = fk_row[0]
        # Drop foreign key constraint
        op.execute(f"ALTER TABLE student_simulation_instances DROP CONSTRAINT IF EXISTS {fk_name}")
    
    # Alter column to be nullable using raw SQL (more reliable)
    # Note: We're NOT creating a foreign key constraint because:
    # 1. Test simulations don't use cohort assignments
    # 2. The cohort_simulations table may not exist yet
    # 3. Application logic can handle the relationship when needed
    op.execute("ALTER TABLE student_simulation_instances ALTER COLUMN cohort_assignment_id DROP NOT NULL")
    
    # Create index if it doesn't exist
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_student_simulation_instances_cohort_assignment_id
        ON student_simulation_instances(cohort_assignment_id)
    """)


def downgrade() -> None:
    # Make the column NOT NULL again (this will fail if there are NULL values)
    op.alter_column('student_simulation_instances', 'cohort_assignment_id',
                   existing_type=sa.Integer(),
                   nullable=False)

