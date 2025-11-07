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
    # Add case_study_url column to scenarios table
    op.add_column('scenarios', sa.Column('case_study_url', sa.String(), nullable=True))


def downgrade() -> None:
    # Remove case_study_url column from scenarios table
    op.drop_column('scenarios', 'case_study_url')
