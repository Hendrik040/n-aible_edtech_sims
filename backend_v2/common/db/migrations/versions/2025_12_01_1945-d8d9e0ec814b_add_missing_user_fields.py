"""add_missing_user_fields

Revision ID: d8d9e0ec814b
Revises: 176865001670
Create Date: 2025-12-01 19:45:24.330116

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8d9e0ec814b'
down_revision: Union[str, None] = '176865001670'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('profile_public', sa.Boolean(), server_default='1', nullable=False))
    op.add_column('users', sa.Column('allow_contact', sa.Boolean(), server_default='1', nullable=False))
    op.add_column('users', sa.Column('provider', sa.String(length=50), nullable=True))
    op.add_column('users', sa.Column('google_id', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('reputation_score', sa.Integer(), server_default='0', nullable=False))
    op.add_column('users', sa.Column('total_simulations', sa.Integer(), server_default='0', nullable=False))
    op.add_column('users', sa.Column('published_scenarios', sa.Integer(), server_default='0', nullable=False))
    op.create_index(op.f('ix_users_google_id'), 'users', ['google_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_users_google_id'), table_name='users')
    op.drop_column('users', 'published_scenarios')
    op.drop_column('users', 'total_simulations')
    op.drop_column('users', 'reputation_score')
    op.drop_column('users', 'google_id')
    op.drop_column('users', 'provider')
    op.drop_column('users', 'allow_contact')
    op.drop_column('users', 'profile_public')

