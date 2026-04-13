"""Add prompt_traces table

Revision ID: add_prompt_traces
Revises: add_password_reset_tokens
Create Date: 2026-04-05 14:00:00.000000

Adds the prompt_traces table for logging every LLM call with full
prompt context, response, token usage, and latency metrics.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# Revision identifiers, used by Alembic.
revision: str = "add_prompt_traces"
down_revision: Union[str, None] = "add_password_reset_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create prompt_traces table if it doesn't already exist."""
    conn = op.get_bind()
    dialect = conn.dialect.name

    def _table_exists() -> bool:
        if dialect == "postgresql":
            result = conn.execute(
                sa.text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = 'prompt_traces')"
                )
            )
            return bool(result.scalar())
        return sa.inspect(conn).has_table("prompt_traces")

    if not _table_exists():
        op.create_table(
            "prompt_traces",
            sa.Column("id", UUID(as_uuid=True), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            # Agent identification
            sa.Column("agent_type", sa.String(50), nullable=False),
            sa.Column("agent_name", sa.String(255), nullable=False),
            # Session / context identifiers
            sa.Column("session_id", sa.String(255), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("scenario_id", sa.Integer(), nullable=True),
            sa.Column("scene_id", sa.Integer(), nullable=True),
            # Prompt versioning
            sa.Column(
                "prompt_version", sa.String(20), nullable=False, server_default="v1"
            ),
            # Full prompt data
            sa.Column("system_prompt", sa.Text(), nullable=False),
            sa.Column("user_message", sa.Text(), nullable=False),
            sa.Column("context_injected", sa.Text(), nullable=True),
            sa.Column("assistant_response", sa.Text(), nullable=False),
            # Model info
            sa.Column("model_name", sa.String(100), nullable=False),
            # Token usage
            sa.Column("input_tokens", sa.Integer(), nullable=True),
            sa.Column("output_tokens", sa.Integer(), nullable=True),
            sa.Column("total_tokens", sa.Integer(), nullable=True),
            # Performance
            sa.Column("latency_ms", sa.Integer(), nullable=False),
            # Model params
            sa.Column("temperature", sa.Float(), nullable=True),
            # Extensible metadata
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="pk_prompt_traces"),
        )

    # Create indexes idempotently
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
            idx["name"] == name for idx in insp.get_indexes("prompt_traces")
        )

    for index_name, columns in (
        ("ix_prompt_traces_created_at", ["created_at"]),
        ("ix_prompt_traces_agent_type", ["agent_type"]),
        ("ix_prompt_traces_session_id", ["session_id"]),
        ("ix_prompt_traces_user_id", ["user_id"]),
        ("ix_prompt_traces_scenario_id", ["scenario_id"]),
        ("ix_prompt_traces_scene_id", ["scene_id"]),
    ):
        if not _index_exists(index_name):
            op.create_index(index_name, "prompt_traces", columns)


def downgrade() -> None:
    """Drop the prompt_traces table and its indexes."""
    conn = op.get_bind()
    dialect = conn.dialect.name

    for index_name in (
        "ix_prompt_traces_scene_id",
        "ix_prompt_traces_scenario_id",
        "ix_prompt_traces_user_id",
        "ix_prompt_traces_session_id",
        "ix_prompt_traces_agent_type",
        "ix_prompt_traces_created_at",
    ):
        if dialect == "postgresql":
            conn.execute(sa.text(f"DROP INDEX IF EXISTS {index_name}"))
        else:
            try:
                op.drop_index(index_name, table_name="prompt_traces")
            except Exception:
                pass

    if dialect == "postgresql":
        conn.execute(sa.text("DROP TABLE IF EXISTS prompt_traces"))
    elif sa.inspect(conn).has_table("prompt_traces"):
        op.drop_table("prompt_traces")
