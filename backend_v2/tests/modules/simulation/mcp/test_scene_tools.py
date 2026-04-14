"""Unit tests for ``advance_scene`` and ``complete_scene`` MCP tools.

All tests run against the in-memory SQLite session from ``tests/conftest.py``.
A ``patched_session_factory`` fixture routes the tool's DB work through the
test session so commits land in the same transaction the test observes.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from common.db.models import (
    SceneProgress,
    SimulationScene,
    Simulation,
    UserProgress,
    User,
)
from modules.simulation.mcp import scene_tools
from modules.simulation.mcp.scene_tools import (
    _advance_scene_sync,
    _complete_scene_sync,
)


@pytest.fixture
def patched_session_factory(db_session: Session):
    """Route tool DB work through the test session."""

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

    with patch.object(scene_tools, "SessionLocal", factory):
        yield factory


@pytest.fixture
def simulation(db_session: Session) -> Simulation:
    user = User(
        user_id="prof-scene",
        email="prof-scene@example.com",
        full_name="Scene Professor",
        username="prof-scene",
        role="professor",
    )
    db_session.add(user)
    db_session.flush()

    sim = Simulation(
        unique_id="sim-scene-tools",
        title="Scene Tools Sim",
        description="Fixture simulation for scene tool tests",
        created_by=user.id,
    )
    db_session.add(sim)
    db_session.flush()
    return sim


@pytest.fixture
def three_scenes(db_session: Session, simulation: Simulation) -> list[SimulationScene]:
    scenes = []
    for i in range(1, 4):
        scene = SimulationScene(
            simulation_id=simulation.id,
            title=f"Scene {i}",
            description=f"Description for scene {i}",
            scene_order=i,
        )
        db_session.add(scene)
        scenes.append(scene)
    db_session.flush()
    return scenes


@pytest.fixture
def user_progress_at_scene1(
    db_session: Session,
    simulation: Simulation,
    three_scenes: list[SimulationScene],
) -> UserProgress:
    user = User(
        user_id="student-1",
        email="student-1@example.com",
        full_name="Student One",
        username="student-1",
        role="student",
    )
    db_session.add(user)
    db_session.flush()

    up = UserProgress(
        user_id=user.id,
        simulation_id=simulation.id,
        current_scene_id=three_scenes[0].id,
        simulation_status="in_progress",
        scenes_completed=[],
    )
    db_session.add(up)
    db_session.flush()
    return up


@pytest.fixture
def user_progress_at_final_scene(
    db_session: Session,
    simulation: Simulation,
    three_scenes: list[SimulationScene],
) -> UserProgress:
    user = User(
        user_id="student-final",
        email="student-final@example.com",
        full_name="Student Final",
        username="student-final",
        role="student",
    )
    db_session.add(user)
    db_session.flush()

    up = UserProgress(
        user_id=user.id,
        simulation_id=simulation.id,
        current_scene_id=three_scenes[2].id,
        simulation_status="in_progress",
        scenes_completed=[three_scenes[0].id, three_scenes[1].id],
    )
    db_session.add(up)
    db_session.flush()
    return up


@pytest.fixture
def user_progress_at_scene2(
    db_session: Session,
    simulation: Simulation,
    three_scenes: list[SimulationScene],
) -> UserProgress:
    user = User(
        user_id="student-2",
        email="student-2@example.com",
        full_name="Student Two",
        username="student-2",
        role="student",
    )
    db_session.add(user)
    db_session.flush()

    up = UserProgress(
        user_id=user.id,
        simulation_id=simulation.id,
        current_scene_id=three_scenes[1].id,
        simulation_status="in_progress",
        scenes_completed=[three_scenes[0].id],
    )
    db_session.add(up)
    db_session.flush()

    db_session.add(
        SceneProgress(
            user_progress_id=up.id,
            scene_id=three_scenes[1].id,
            status="in_progress",
        )
    )
    db_session.flush()
    return up


# ---------- advance_scene tests ----------


def test_advance_scene_moves_to_next_in_order(
    patched_session_factory,
    db_session: Session,
    user_progress_at_scene1: UserProgress,
    three_scenes: list[SimulationScene],
):
    result = _advance_scene_sync(
        user_progress_at_scene1.id,
        session_factory=patched_session_factory,
    )

    assert result["is_error"] is False
    assert str(three_scenes[1].id) in result["content"][0]["text"]

    db_session.refresh(user_progress_at_scene1)
    assert user_progress_at_scene1.current_scene_id == three_scenes[1].id
    assert three_scenes[0].id in user_progress_at_scene1.scenes_completed

    new_progress = db_session.execute(
        select(SceneProgress)
        .where(SceneProgress.user_progress_id == user_progress_at_scene1.id)
        .where(SceneProgress.scene_id == three_scenes[1].id)
    ).scalar_one_or_none()
    assert new_progress is not None
    assert new_progress.status == "in_progress"


def test_advance_scene_noop_on_final_scene(
    patched_session_factory,
    db_session: Session,
    user_progress_at_final_scene: UserProgress,
    three_scenes: list[SimulationScene],
):
    result = _advance_scene_sync(
        user_progress_at_final_scene.id,
        session_factory=patched_session_factory,
    )

    assert result["is_error"] is False
    assert "final scene" in result["content"][0]["text"].lower()

    db_session.refresh(user_progress_at_final_scene)
    assert user_progress_at_final_scene.current_scene_id == three_scenes[2].id


def test_advance_scene_error_user_progress_not_found(patched_session_factory):
    result = _advance_scene_sync(
        999999,
        session_factory=patched_session_factory,
    )
    assert result["is_error"] is True
    assert "999999" in result["content"][0]["text"]


def test_advance_scene_error_simulation_completed(
    patched_session_factory,
    db_session: Session,
    user_progress_at_scene1: UserProgress,
):
    user_progress_at_scene1.simulation_status = "completed"
    db_session.flush()

    result = _advance_scene_sync(
        user_progress_at_scene1.id,
        session_factory=patched_session_factory,
    )
    assert result["is_error"] is True
    assert "completed" in result["content"][0]["text"].lower()


# ---------- complete_scene tests ----------


def test_complete_scene_marks_completed(
    patched_session_factory,
    db_session: Session,
    user_progress_at_scene2: UserProgress,
    three_scenes: list[SimulationScene],
):
    scene_id = three_scenes[1].id
    summary = "Student demonstrated strong analytical skills."

    result = _complete_scene_sync(
        user_progress_at_scene2.id,
        scene_id,
        summary,
        session_factory=patched_session_factory,
    )

    assert result["is_error"] is False

    db_session.refresh(user_progress_at_scene2)
    assert scene_id in user_progress_at_scene2.scenes_completed

    sp = db_session.execute(
        select(SceneProgress)
        .where(SceneProgress.user_progress_id == user_progress_at_scene2.id)
        .where(SceneProgress.scene_id == scene_id)
    ).scalar_one()
    assert sp.status == "completed"
    assert sp.completed_at is not None
    assert sp.progress_data["summary"] == summary


def test_complete_scene_rejects_wrong_current_scene(
    patched_session_factory,
    user_progress_at_scene2: UserProgress,
    three_scenes: list[SimulationScene],
):
    wrong_scene_id = three_scenes[2].id

    result = _complete_scene_sync(
        user_progress_at_scene2.id,
        wrong_scene_id,
        "some summary",
        session_factory=patched_session_factory,
    )

    assert result["is_error"] is True
    text = result["content"][0]["text"]
    assert f"cannot complete scene {wrong_scene_id}" in text
    assert str(three_scenes[1].id) in text


def test_complete_scene_rejects_already_completed(
    patched_session_factory,
    db_session: Session,
    user_progress_at_scene2: UserProgress,
    three_scenes: list[SimulationScene],
):
    scene_id = three_scenes[0].id
    user_progress_at_scene2.current_scene_id = scene_id
    db_session.flush()

    result = _complete_scene_sync(
        user_progress_at_scene2.id,
        scene_id,
        "re-completing",
        session_factory=patched_session_factory,
    )

    assert result["is_error"] is True
    assert "already completed" in result["content"][0]["text"].lower()


def test_complete_scene_error_user_progress_not_found(patched_session_factory):
    result = _complete_scene_sync(
        999999,
        1,
        "summary",
        session_factory=patched_session_factory,
    )
    assert result["is_error"] is True
    assert "999999" in result["content"][0]["text"]


def test_advance_scene_reuses_existing_scene_progress(
    patched_session_factory,
    db_session: Session,
    user_progress_at_scene1: UserProgress,
    three_scenes: list[SimulationScene],
):
    """When a SceneProgress row already exists for the next scene, advance_scene
    should update it to in_progress rather than creating a duplicate."""
    db_session.add(
        SceneProgress(
            user_progress_id=user_progress_at_scene1.id,
            scene_id=three_scenes[1].id,
            status="not_started",
        )
    )
    db_session.flush()

    result = _advance_scene_sync(
        user_progress_at_scene1.id,
        session_factory=patched_session_factory,
    )

    assert result["is_error"] is False

    sp = db_session.execute(
        select(SceneProgress)
        .where(SceneProgress.user_progress_id == user_progress_at_scene1.id)
        .where(SceneProgress.scene_id == three_scenes[1].id)
    ).scalar_one()
    assert sp.status == "in_progress"


def test_complete_scene_creates_progress_when_missing(
    patched_session_factory,
    db_session: Session,
    simulation: Simulation,
    three_scenes: list[SimulationScene],
):
    """When no SceneProgress row exists, complete_scene should create one."""
    user = User(
        user_id="student-no-sp",
        email="no-sp@example.com",
        full_name="No SP",
        username="student-no-sp",
        role="student",
    )
    db_session.add(user)
    db_session.flush()

    up = UserProgress(
        user_id=user.id,
        simulation_id=simulation.id,
        current_scene_id=three_scenes[0].id,
        simulation_status="in_progress",
        scenes_completed=[],
    )
    db_session.add(up)
    db_session.flush()

    result = _complete_scene_sync(
        up.id,
        three_scenes[0].id,
        "created fresh",
        session_factory=patched_session_factory,
    )

    assert result["is_error"] is False

    sp = db_session.execute(
        select(SceneProgress)
        .where(SceneProgress.user_progress_id == up.id)
        .where(SceneProgress.scene_id == three_scenes[0].id)
    ).scalar_one()
    assert sp.status == "completed"
    assert sp.progress_data["summary"] == "created fresh"


