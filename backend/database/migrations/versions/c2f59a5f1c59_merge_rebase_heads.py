"""merge_rebase_heads

Revision ID: c2f59a5f1c59
Revises: 5e4ae4632a4a, 9df1112bf896
Create Date: 2025-10-27 10:16:41.998276

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c2f59a5f1c59'
down_revision = ('5e4ae4632a4a', '9df1112bf896')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
