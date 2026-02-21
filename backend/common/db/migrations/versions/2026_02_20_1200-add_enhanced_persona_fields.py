"""Add enhanced persona fields (current_context, knowledge_areas, communication_style)
and migrate personality_traits to Big Five model.

Revision ID: add_enhanced_persona_fields
Revises: add_conv_logs_indexes
Create Date: 2026-02-20

Changes:
- Adds current_context (Text): persona's current responsibilities/challenges in the case
- Adds knowledge_areas (JSON/Array): specific facts and data the persona knows
- Adds communication_style (Text): how this persona communicates
- Resets personality_traits to NULL for rows using the old trait schema
  (old keys: analytical, creative, assertive, etc.) so the new Big Five schema
  (openness, conscientiousness, extraversion, agreeableness, neuroticism) is used
  consistently. Only rows that already contain Big Five keys are left untouched.
"""
from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision = 'add_enhanced_persona_fields'
down_revision = 'add_conv_logs_indexes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Add new columns ---
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

    # --- Migrate old personality_traits to NULL ---
    # Rows that already contain at least one Big Five key are left untouched.
    # All other rows (old 8-trait schema: analytical, creative, etc.) are reset
    # to NULL so they pick up default values when next edited or re-extracted.
    #
    # Note: the ? operator (JSON key existence) requires jsonb, not json.
    # We cast personality_traits to jsonb for the check only; the column type
    # itself remains json (no structural migration needed).
    op.execute("""
        UPDATE simulation_personas
        SET personality_traits = NULL
        WHERE personality_traits IS NOT NULL
          AND NOT (
              personality_traits::jsonb ? 'openness'
              OR personality_traits::jsonb ? 'conscientiousness'
              OR personality_traits::jsonb ? 'extraversion'
              OR personality_traits::jsonb ? 'agreeableness'
              OR personality_traits::jsonb ? 'neuroticism'
          )
    """)


def downgrade() -> None:
    op.drop_column('simulation_personas', 'communication_style')
    op.drop_column('simulation_personas', 'knowledge_areas')
    op.drop_column('simulation_personas', 'current_context')
    # Note: personality_traits data reset is intentionally not reversed on downgrade.
