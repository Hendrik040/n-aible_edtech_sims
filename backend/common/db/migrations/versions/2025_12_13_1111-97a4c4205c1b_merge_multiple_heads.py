"""merge_multiple_heads

Revision ID: 97a4c4205c1b
Revises: fix_scenes_type, 3f9b0c4b2e1d
Create Date: 2025-12-13 11:11:35.298862

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '97a4c4205c1b'
down_revision: Union[str, None] = ('fix_scenes_type', '3f9b0c4b2e1d')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

