"""merge_heads_with_token_hash_removal

Revision ID: 40301e215452
Revises: ee4609cea88e, a1b2c3d4e5f6
Create Date: 2025-12-17 22:50:08.604456

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = '40301e215452'
down_revision: Union[str, None] = ('ee4609cea88e', 'a1b2c3d4e5f6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

