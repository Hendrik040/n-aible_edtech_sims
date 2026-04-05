"""Add password_reset_tokens table

Revision ID: add_password_reset_tokens
Revises: add_enhanced_persona_fields
Create Date: 2026-04-05 12:00:00.000000

Adds the password_reset_tokens table used by the email-verified forgot
password flow. Tokens are single-use, expire after 1 hour, and are removed
automatically when the owning user is deleted (ON DELETE CASCADE).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision: str = "add_password_reset_tokens"
down_revision: Union[str, None] = "add_enhanced_persona_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create password_reset_tokens table if it doesn't already exist."""
    conn = op.get_bind()
    dialect = conn.dialect.name

    def _table_exists() -> bool:
        if dialect == "postgresql":
            result = conn.execute(
                sa.text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = 'password_reset_tokens')"
                )
            )
            return bool(result.scalar())
        # Fallback for sqlite and others
        return sa.inspect(conn).has_table("password_reset_tokens")

    if not _table_exists():
        op.create_table(
            "password_reset_tokens",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("token", sa.String(length=255), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token", name="uq_password_reset_tokens_token"),
        )

    # Indexes — create idempotently so this migration is safe to re-run.
    def _index_exists(name: str) -> bool:
        if dialect == "postgresql":
            result = conn.execute(
                sa.text(
                    "SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = :n)"
                ),
                {"n": name},
            )
            return bool(result.scalar())
        insp = sa.inspect(conn)
        return any(
            idx["name"] == name
            for idx in insp.get_indexes("password_reset_tokens")
        )

    for index_name, columns in (
        ("idx_password_reset_tokens_token", ["token"]),
        ("idx_password_reset_tokens_user_id", ["user_id"]),
    ):
        if not _index_exists(index_name):
            op.create_index(index_name, "password_reset_tokens", columns)


def downgrade() -> None:
    """Drop the password_reset_tokens table and its indexes."""
    conn = op.get_bind()
    dialect = conn.dialect.name

    for index_name in (
        "idx_password_reset_tokens_user_id",
        "idx_password_reset_tokens_token",
    ):
        if dialect == "postgresql":
            conn.execute(sa.text(f"DROP INDEX IF EXISTS {index_name}"))
        else:
            try:
                op.drop_index(index_name, table_name="password_reset_tokens")
            except Exception:
                pass

    if dialect == "postgresql":
        conn.execute(sa.text("DROP TABLE IF EXISTS password_reset_tokens"))
    else:
        try:
            op.drop_table("password_reset_tokens")
        except Exception:
            pass
