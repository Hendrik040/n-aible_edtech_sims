"""add_case_study_url_to_scenarios

Revision ID: 67222605a644
Revises: 9f8e7d6c5b4a
Create Date: 2025-11-06 23:06:12.418166

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.exc import ProgrammingError


# revision identifiers, used by Alembic.
revision = '67222605a644'
down_revision = '9f8e7d6c5b4a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if column already exists before adding
    connection = op.get_bind()
    inspector = inspect(connection)
    
    # Get existing columns in scenarios table
    existing_columns = [col['name'] for col in inspector.get_columns('scenarios')]
    
    # Only add column if it doesn't exist
    if 'case_study_url' not in existing_columns:
        op.add_column('scenarios', sa.Column('case_study_url', sa.String(), nullable=True))
    else:
        print("✅ Column 'case_study_url' already exists in scenarios table, skipping migration")


def downgrade() -> None:
    # Check if column exists before removing
    connection = op.get_bind()
    inspector = inspect(connection)
    
    # Get existing columns in scenarios table
    existing_columns = [col['name'] for col in inspector.get_columns('scenarios')]
    
    # Only remove column if it exists
    if 'case_study_url' in existing_columns:
        op.drop_column('scenarios', 'case_study_url')
    else:
        print("⚠️  Column 'case_study_url' does not exist in scenarios table, skipping downgrade")
