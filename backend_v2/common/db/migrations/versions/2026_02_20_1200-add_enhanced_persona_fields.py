"""Add enhanced persona fields (current_context, knowledge_areas, communication_style).

Revision ID: add_enhanced_persona_fields
Revises: add_conv_logs_indexes
Create Date: 2026-02-20

Changes:
- Adds current_context (Text): persona's current responsibilities/challenges in the case
- Adds knowledge_areas (JSON/Array): specific facts and data the persona knows
- Adds communication_style (Text): how this persona communicates

The schema transition from the legacy 8-trait personality model to the Big Five
model is handled by a separate, reversible backfill job — this migration is
purely additive so downgrade is safe and no user data is destroyed.
"""
from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision = 'add_enhanced_persona_fields'
down_revision = 'add_conv_logs_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'simulation_personas',
        sa.Column('current_context', sa.Text(), nullable=True,
                  comment='Current responsibilities and challenges in the case narrative')
    )
    op.add_column(
        'simulation_personas',
        sa.Column('knowledge_areas', sa.JSON(), nullable=True,
                  comment='List of specific facts, data points, and domain knowledge this persona possesses')
    )
    op.add_column(
        'simulation_personas',
        sa.Column('communication_style', sa.Text(), nullable=True,
                  comment='How this persona communicates: tone, register, approach')
    )


def downgrade() -> None:
    op.drop_column('simulation_personas', 'communication_style')
    op.drop_column('simulation_personas', 'knowledge_areas')
    op.drop_column('simulation_personas', 'current_context')
