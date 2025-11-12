"""add_case_study_url_to_scenarios

Revision ID: 67222605a644
Revises: 9f8e7d6c5b4a
Create Date: 2025-11-06 23:06:12.418166

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '67222605a644'
down_revision = '9f8e7d6c5b4a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect
    
    # Get connection to check existing columns
    connection = op.get_bind()
    inspector = inspect(connection)
    
    # Check which columns already exist in scenarios table
    existing_columns = [col['name'] for col in inspector.get_columns('scenarios')]
    
    # Add case_study_url column to scenarios table if it doesn't exist
    if 'case_study_url' not in existing_columns:
        op.add_column('scenarios', sa.Column('case_study_url', sa.String(), nullable=True))


def downgrade() -> None:
    from sqlalchemy import inspect
    
    # Get connection to check existing columns
    connection = op.get_bind()
    inspector = inspect(connection)
    
    # Check which columns already exist in scenarios table
    existing_columns = [col['name'] for col in inspector.get_columns('scenarios')]
    
    # Remove case_study_url column from scenarios table if it exists
    if 'case_study_url' in existing_columns:
        op.drop_column('scenarios', 'case_study_url')
