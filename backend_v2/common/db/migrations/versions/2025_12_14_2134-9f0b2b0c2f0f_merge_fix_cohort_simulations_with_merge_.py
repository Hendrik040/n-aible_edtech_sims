"""merge_fix_cohort_simulations_with_merge_heads

Revision ID: 9f0b2b0c2f0f
Revises: 97a4c4205c1b, fix_cohort_simulations_fk
Create Date: 2025-12-14 21:34:58.006154

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = '9f0b2b0c2f0f'
down_revision: Union[str, None] = ('97a4c4205c1b', 'fix_cohort_simulations_fk')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

