"""merge enhanced_persona_fields with code_challenge_fields

Revision ID: merge_enhanced_persona_with_code_challenge
Revises: add_enhanced_persona_fields, add_code_challenge_fields
Create Date: 2026-02-09

Merges the add_enhanced_persona_fields and add_code_challenge_fields branches.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'merge_persona_code_challenge'
down_revision = ('add_enhanced_persona_fields', 'add_code_challenge_fields')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
