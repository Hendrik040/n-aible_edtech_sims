"""fix_scenes_completed_column_type

Revision ID: fix_scenes_type
Revises: a4de75a977bc
Create Date: 2025-12-13

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'fix_scenes_type'
down_revision: Union[str, None] = 'a4de75a977bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Change scenes_completed from INTEGER to JSON."""
    # First drop the default value (INTEGER default 0 can't cast to JSON)
    op.execute("ALTER TABLE user_progress ALTER COLUMN scenes_completed DROP DEFAULT")
    # Change the column type
    op.execute("ALTER TABLE user_progress ALTER COLUMN scenes_completed TYPE JSON USING NULL")


def downgrade() -> None:
    """Revert scenes_completed back to INTEGER."""
    op.execute("ALTER TABLE user_progress ALTER COLUMN scenes_completed TYPE INTEGER USING 0")
    op.execute("ALTER TABLE user_progress ALTER COLUMN scenes_completed SET DEFAULT 0")

