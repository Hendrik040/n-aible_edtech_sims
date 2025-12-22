"""merge_notifications_with_main_chain

Revision ID: df3677caaba1
Revises: 1d832984f413
Create Date: 2025-12-21 21:32:15.942695

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'df3677caaba1'
down_revision: Union[str, Sequence[str], None] = ('add_notifications_table', 'add_composite_indexes')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

