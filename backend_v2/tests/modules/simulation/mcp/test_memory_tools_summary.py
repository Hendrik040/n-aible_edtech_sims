"""Unit tests for the ``write_summary`` MCP tool (phase-2.5).

Covers three ticket-required cases:

* inserting a new ``conversation_summaries`` row,
* updating an existing row for the same (user_progress_id, scene_id), and
* rejecting empty / whitespace-only ``summary_text``.

All tests run against the in-memory SQLite session from
``tests/conftest.py``. A ``patched_session_factory`` fixture makes the
tool reuse that session so commits land in the same transaction the test
observes before teardown.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from common.db.models import (
    ConversationSummaries,
    Simulation,
    SimulationScene,
    User,
    UserProgress,
)
from modules.simulation.mcp import memory_tools
from modules.simulation.mcp.memory_tools import write_summary


@pytest.fixture
def patched_session_factory(db_session: Session):
    """Route ``write_summary``'s DB work through the test's session."""

    class _NoCloseSession:
        def __init__(self, inner: Session) -> None:
            self._inner = inner

        def __getattr__(self, name: str):
            return getattr(self._inner, name)

        def close(self) -> None:
            pass

        def commit(self) -> None:
            self._inner.flush()

        def rollback(self) -> None:
            self._inner.rollback()

    def factory() -> Session:  # type: ignore[return-value]
        return _NoCloseSession(db_session)  # type: ignore[return-value]

    with patch.object(memory_tools, "SessionLocal", factory):
        yield factory


@pytest.fixture
def simulation(db_session: Session) -> Simulation:
    user = User(
        user_id="prof-summary",
        email="prof-summary@example.com",
        full_name="Phase 2.5 Professor",
        username="prof-phase-2-5",
        role="professor",
    )
    db_session.add(user)
    db_session.flush()

    sim = Simulation(
        unique_id="sim-phase-2-5",
        title="Phase 2.5 Sim",
        description="Fixture simulation",
        created_by=user.id,
    )
    db_session.add(sim)
    db_session.flush()
    return sim


@pytest.fixture
def scene(db_session: Session, simulation: Simulation) -> SimulationScene:
    scene_row = SimulationScene(
        simulation_id=simulation.id,
        title="Scene 1",
        description="",
        scene_order=1,
    )
    db_session.add(scene_row)
    db_session.flush()
    return scene_row


@pytest.fixture
def user_progress(
    db_session: Session, simulation: Simulation, scene: SimulationScene
) -> UserProgress:
    student = User(
        user_id="stud-summary",
        email="stud-summary@example.com",
        full_name="Phase 2.5 Student",
        username="stud-phase-2-5",
        role="student",
    )
    db_session.add(student)
    db_session.flush()

    progress = UserProgress(
        user_id=student.id,
        simulation_id=simulation.id,
        current_scene_id=scene.id,
    )
    db_session.add(progress)
    db_session.flush()
    return progress


@pytest.mark.asyncio
async def test_write_summary_inserts_new_row(
    db_session: Session,
    patched_session_factory,
    scene: SimulationScene,
    user_progress: UserProgress,
) -> None:
    """A valid call creates a new ``conversation_summaries`` row."""
    result = await write_summary.handler(
        {
            "user_progress_id": user_progress.id,
            "scene_id": scene.id,
            "summary_text": "The student demonstrated strong analytical skills.",
        }
    )

    assert result["is_error"] is False
    assert result["content"][0]["text"] == "summary saved"

    row = db_session.execute(
        select(ConversationSummaries)
        .where(ConversationSummaries.user_progress_id == user_progress.id)
        .where(ConversationSummaries.scene_id == scene.id)
    ).scalar_one()
    assert row.summary_text == "The student demonstrated strong analytical skills."
    assert row.summary_type == "scene"
    assert result["structuredContent"]["id"] == row.id


@pytest.mark.asyncio
async def test_write_summary_updates_existing_row(
    db_session: Session,
    patched_session_factory,
    scene: SimulationScene,
    user_progress: UserProgress,
) -> None:
    """A second call for the same (user_progress, scene) updates in place."""
    await write_summary.handler(
        {
            "user_progress_id": user_progress.id,
            "scene_id": scene.id,
            "summary_text": "Original summary text.",
        }
    )

    result = await write_summary.handler(
        {
            "user_progress_id": user_progress.id,
            "scene_id": scene.id,
            "summary_text": "Updated summary text.",
        }
    )

    assert result["is_error"] is False

    rows = db_session.execute(
        select(ConversationSummaries)
        .where(ConversationSummaries.user_progress_id == user_progress.id)
        .where(ConversationSummaries.scene_id == scene.id)
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].summary_text == "Updated summary text."


@pytest.mark.asyncio
async def test_write_summary_rejects_empty_text(
    patched_session_factory,
) -> None:
    """Empty and whitespace-only ``summary_text`` raises ``ValueError``."""
    with pytest.raises(ValueError, match="non-empty"):
        await write_summary.handler(
            {
                "user_progress_id": 1,
                "scene_id": 1,
                "summary_text": "",
            }
        )

    with pytest.raises(ValueError, match="non-empty"):
        await write_summary.handler(
            {
                "user_progress_id": 1,
                "scene_id": 1,
                "summary_text": "   \t\n  ",
            }
        )
