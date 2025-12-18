"""merge_all_heads

Revision ID: ee4609cea88e
Revises: 9f0b2b0c2f0f
Create Date: 2025-12-16 13:06:17.046981

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ee4609cea88e'
down_revision: Union[str, Sequence[str], None] = ('6f6b3caca601', '9f0b2b0c2f0f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

