"""add_unique_id_to_student_simulation_instances

Revision ID: 82345087346c
Revises: 1a44d8443d3f
Create Date: 2025-10-08 16:49:31.836379

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '82345087346c'
down_revision = '1a44d8443d3f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add unique_id column (nullable temporarily)
    op.add_column('student_simulation_instances', 
                  sa.Column('unique_id', sa.String(), nullable=True))
    
    # Generate unique IDs for existing rows
    import secrets
    from sqlalchemy import text
    
    # Get connection
    connection = op.get_bind()
    
    # Fetch all existing instances
    result = connection.execute(text("SELECT id FROM student_simulation_instances"))
    rows = result.fetchall()
    
    # Update each row with a unique ID
    for row in rows:
        unique_id = f"SSI-{secrets.token_urlsafe(8).upper()}"
        connection.execute(
            text("UPDATE student_simulation_instances SET unique_id = :unique_id WHERE id = :id"),
            {"unique_id": unique_id, "id": row[0]}
        )
    
    # Now make the column non-nullable and add unique constraint
    op.alter_column('student_simulation_instances', 'unique_id',
                    existing_type=sa.String(),
                    nullable=False)
    op.create_index(op.f('ix_student_simulation_instances_unique_id'), 
                    'student_simulation_instances', ['unique_id'], unique=True)


def downgrade() -> None:
    # Remove unique_id column
    op.drop_index(op.f('ix_student_simulation_instances_unique_id'), 
                  table_name='student_simulation_instances')
    op.drop_column('student_simulation_instances', 'unique_id')
