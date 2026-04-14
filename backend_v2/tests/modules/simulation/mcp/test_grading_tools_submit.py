"""Unit tests for the ``submit_grade`` MCP tool (phase-2.3).

The tool has three moving parts we care about:

* rubric-key validation against ``Simulation.grading_config``,
* writing the grading payload into the scene's ``progress_data`` column
  under the ``"grading_result"`` key, and
* inserting / updating a single ``grading_materials`` row per
  ``(user_progress_id, scene_id)``.

All tests run against the in-memory SQLite session from
``tests/conftest.py``. A ``patched_session_factory`` fixture makes the
tool reuse that session so commits land in the same transaction the test
observes before teardown.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from common.db.models import (
    GradingMaterial,
    SceneProgress,
    Simulation,
    SimulationScene,
    UserProgress,
    User,
)
from modules.simulation.mcp import grading_tools
from modules.simulation.mcp.grading_tools import submit_grade


@pytest.fixture
def patched_session_factory(db_session: Session):
    """Route ``submit_grade``'s DB work through the test's session.

    The tool builds its own session via ``SessionLocal()`` by default;
    patching the module-level ``SessionLocal`` to a factory that returns
    a wrapper session — with ``close()`` / ``commit()`` neutralised so the
    fixture's rollback-on-teardown still wins — makes all writes visible
    to assertions without escaping the transaction.
    """
    class _NoCloseSession:
        def __init__(self, inner: Session) -> None:
            self._inner = inner

        def __getattr__(self, name: str):
            return getattr(self._inner, name)

        def close(self) -> None:  # tests own the session lifecycle
            pass

        def commit(self) -> None:
            # Flush so follow-up selects see pending inserts/updates,
            # but defer the real commit to the test's teardown rollback.
            self._inner.flush()

        def rollback(self) -> None:
            self._inner.rollback()

    def factory() -> Session:  # type: ignore[return-value]
        return _NoCloseSession(db_session)  # type: ignore[return-value]

    with patch.object(grading_tools, "SessionLocal", factory):
        yield factory


@pytest.fixture
def simulation(db_session: Session) -> Simulation:
    """Simulation with a two-criterion rubric keyed by ``description``."""
    user = User(
        user_id="prof-1",
        email="prof@example.com",
        full_name="Phase 2.3 Professor",
        username="prof-phase-2-3",
        role="professor",
    )
    db_session.add(user)
    db_session.flush()

    sim = Simulation(
        unique_id="sim-phase-2-3",
        title="Phase 2.3 Sim",
        description="Fixture simulation",
        created_by=user.id,
        grading_config={
            "title": "Rubric",
            "criteria": [
                {"description": "Analysis"},
                {"description": "Communication"},
            ],
            "performance_levels": [],
            "strictness_level": 3,
        },
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
        user_id="stud-1",
        email="stud@example.com",
        full_name="Phase 2.3 Student",
        username="stud-phase-2-3",
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


def _valid_scores() -> dict[str, int]:
    return {"Analysis": 8, "Communication": 7}


@pytest.mark.asyncio
async def test_submit_grade_writes_scene_progress_row(
    db_session: Session,
    patched_session_factory,
    simulation: Simulation,
    scene: SimulationScene,
    user_progress: UserProgress,
) -> None:
    """A valid submission persists the payload to ``scene_progress.progress_data``."""
    result = await submit_grade.handler(
        {
            "user_progress_id": user_progress.id,
            "scene_id": scene.id,
            "rubric_scores": _valid_scores(),
            "strictness": "balanced",
        }
    )

    assert result["is_error"] is False
    assert result["structuredContent"]["rubric_scores"] == _valid_scores()
    assert result["structuredContent"]["strictness"] == "balanced"

    row = db_session.execute(
        select(SceneProgress)
        .where(SceneProgress.user_progress_id == user_progress.id)
        .where(SceneProgress.scene_id == scene.id)
    ).scalar_one()
    assert row.progress_data is not None
    grading = row.progress_data["grading_result"]
    assert grading["rubric_scores"] == _valid_scores()
    assert grading["strictness"] == "balanced"
    assert grading["simulation_id"] == simulation.id


@pytest.mark.asyncio
async def test_submit_grade_inserts_grading_materials_row(
    db_session: Session,
    patched_session_factory,
    simulation: Simulation,
    scene: SimulationScene,
    user_progress: UserProgress,
) -> None:
    """A valid submission inserts exactly one ``grading_materials`` row."""
    await submit_grade.handler(
        {
            "user_progress_id": user_progress.id,
            "scene_id": scene.id,
            "rubric_scores": _valid_scores(),
            "strictness": "balanced",
        }
    )

    materials = db_session.execute(
        select(GradingMaterial).where(
            GradingMaterial.simulation_id == simulation.id
        )
    ).scalars().all()
    assert len(materials) == 1
    material = materials[0]
    assert material.filename == f"grade_{user_progress.id}_{scene.id}.json"
    assert material.processing_status == "completed"
    payload = json.loads(material.content)
    assert payload["rubric_scores"] == _valid_scores()
    assert payload["strictness"] == "balanced"


@pytest.mark.asyncio
async def test_submit_grade_rejects_unknown_rubric_keys(
    db_session: Session,
    patched_session_factory,
    simulation: Simulation,
    scene: SimulationScene,
    user_progress: UserProgress,
) -> None:
    """Unknown rubric keys short-circuit to ``is_error=True`` with no DB writes."""
    result = await submit_grade.handler(
        {
            "user_progress_id": user_progress.id,
            "scene_id": scene.id,
            "rubric_scores": {
                "Analysis": 8,
                "NotARealCriterion": 5,
                "AlsoFake": 3,
            },
            "strictness": "balanced",
        }
    )

    assert result["is_error"] is True
    text = result["content"][0]["text"]
    assert "NotARealCriterion" in text
    assert "AlsoFake" in text

    # Nothing was persisted — validation runs before writes.
    assert (
        db_session.execute(
            select(SceneProgress).where(
                SceneProgress.user_progress_id == user_progress.id
            )
        ).scalar_one_or_none()
        is None
    )
    assert (
        db_session.execute(
            select(GradingMaterial).where(
                GradingMaterial.simulation_id == simulation.id
            )
        ).scalar_one_or_none()
        is None
    )


@pytest.mark.asyncio
async def test_submit_grade_idempotent_on_same_user_progress(
    db_session: Session,
    patched_session_factory,
    simulation: Simulation,
    scene: SimulationScene,
    user_progress: UserProgress,
) -> None:
    """Resubmitting for the same (user_progress, scene) updates in place."""
    first = await submit_grade.handler(
        {
            "user_progress_id": user_progress.id,
            "scene_id": scene.id,
            "rubric_scores": {"Analysis": 5, "Communication": 5},
            "strictness": "balanced",
        }
    )
    assert first["is_error"] is False

    second = await submit_grade.handler(
        {
            "user_progress_id": user_progress.id,
            "scene_id": scene.id,
            "rubric_scores": {"Analysis": 9, "Communication": 9},
            "strictness": "strict",
        }
    )
    assert second["is_error"] is False

    scene_progress_rows = db_session.execute(
        select(SceneProgress)
        .where(SceneProgress.user_progress_id == user_progress.id)
        .where(SceneProgress.scene_id == scene.id)
    ).scalars().all()
    assert len(scene_progress_rows) == 1
    latest = scene_progress_rows[0].progress_data["grading_result"]
    assert latest["rubric_scores"] == {"Analysis": 9, "Communication": 9}
    assert latest["strictness"] == "strict"

    materials = db_session.execute(
        select(GradingMaterial).where(
            GradingMaterial.simulation_id == simulation.id
        )
    ).scalars().all()
    assert len(materials) == 1
    assert json.loads(materials[0].content)["strictness"] == "strict"


@pytest.mark.asyncio
async def test_submit_grade_missing_user_progress_returns_error(
    db_session: Session, patched_session_factory
) -> None:
    """An unknown ``user_progress_id`` produces an error envelope, not an exception."""
    result = await submit_grade.handler(
        {
            "user_progress_id": 999_999,
            "scene_id": 1,
            "rubric_scores": _valid_scores(),
            "strictness": "balanced",
        }
    )

    assert result["is_error"] is True
    assert "999999" in result["content"][0]["text"]
    assert (
        db_session.execute(select(GradingMaterial)).scalar_one_or_none()
        is None
    )


@pytest.mark.asyncio
async def test_submit_grade_simulation_without_rubric_returns_error(
    db_session: Session,
    patched_session_factory,
    simulation: Simulation,
    scene: SimulationScene,
    user_progress: UserProgress,
) -> None:
    """A simulation whose ``grading_config`` has no criteria is rejected."""
    simulation.grading_config = {"title": "Empty", "criteria": []}
    db_session.flush()

    result = await submit_grade.handler(
        {
            "user_progress_id": user_progress.id,
            "scene_id": scene.id,
            "rubric_scores": {"Analysis": 8},
            "strictness": "balanced",
        }
    )

    assert result["is_error"] is True
    assert f"Simulation {simulation.id}" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_submit_grade_missing_required_field_returns_error(
    patched_session_factory,
) -> None:
    """Dropping a required arg falls through to the generic error envelope."""
    result = await submit_grade.handler(
        {
            "user_progress_id": 1,
            "scene_id": 1,
            "rubric_scores": _valid_scores(),
            # no strictness
        }
    )

    assert result == {
        "content": [{"type": "text", "text": "Failed to submit grade"}],
        "is_error": True,
    }


@pytest.mark.asyncio
async def test_submit_grade_non_dict_rubric_scores_returns_error(
    patched_session_factory,
) -> None:
    """A list / string in ``rubric_scores`` is rejected before touching the DB."""
    result = await submit_grade.handler(
        {
            "user_progress_id": 1,
            "scene_id": 1,
            "rubric_scores": ["not", "a", "dict"],
            "strictness": "balanced",
        }
    )

    assert result["is_error"] is True
    assert "dict" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_submit_grade_rejects_non_dict_args(
    patched_session_factory,
) -> None:
    """A non-mapping ``args`` collapses to the generic error envelope."""
    result = await submit_grade.handler(["not", "a", "dict"])  # type: ignore[arg-type]

    assert result == {
        "content": [{"type": "text", "text": "Failed to submit grade"}],
        "is_error": True,
    }


@pytest.mark.asyncio
async def test_submit_grade_missing_field_does_not_log_full_args(
    patched_session_factory, caplog: pytest.LogCaptureFixture
) -> None:
    """On missing required fields we log only field names, not the payload.

    This guards the finding that logger.exception previously echoed the
    entire request — including per-criterion grade data and identifiers
    — into structured logs.
    """
    import logging

    sensitive_score = 0xBADC0FFEE
    with caplog.at_level(logging.WARNING, logger="modules.simulation.mcp.grading_tools"):
        result = await submit_grade.handler(
            {
                "user_progress_id": 42,
                "scene_id": 7,
                "rubric_scores": {"Analysis": sensitive_score},
                # strictness intentionally omitted
            }
        )

    assert result["is_error"] is True
    combined = " ".join(record.getMessage() for record in caplog.records)
    assert "strictness" in combined
    assert str(sensitive_score) not in combined
    assert "'rubric_scores'" not in combined
    assert "Analysis" not in combined


@pytest.mark.asyncio
async def test_submit_grade_unknown_scene_returns_error(
    db_session: Session,
    patched_session_factory,
    simulation: Simulation,
    scene: SimulationScene,
    user_progress: UserProgress,
) -> None:
    """A ``scene_id`` that doesn't map to any scene surfaces as is_error."""
    result = await submit_grade.handler(
        {
            "user_progress_id": user_progress.id,
            "scene_id": 999_999,
            "rubric_scores": _valid_scores(),
            "strictness": "balanced",
        }
    )

    assert result["is_error"] is True
    assert "999999" in result["content"][0]["text"]
    assert (
        db_session.execute(select(GradingMaterial)).scalar_one_or_none()
        is None
    )


@pytest.mark.asyncio
async def test_submit_grade_rejects_scene_from_other_simulation(
    db_session: Session,
    patched_session_factory,
    simulation: Simulation,
    user_progress: UserProgress,
) -> None:
    """A scene belonging to a different simulation is rejected without writes.

    Guards against a caller passing a scene_id from an unrelated simulation
    and silently corrupting the wrong simulation's scene_progress.
    """
    other_prof = User(
        user_id="prof-other",
        email="other@example.com",
        full_name="Other Professor",
        username="prof-other",
        role="professor",
    )
    db_session.add(other_prof)
    db_session.flush()
    other_sim = Simulation(
        unique_id="sim-other",
        title="Other Sim",
        description="Different simulation",
        created_by=other_prof.id,
        grading_config={
            "title": "Rubric",
            "criteria": [{"description": "Analysis"}],
            "performance_levels": [],
            "strictness_level": 3,
        },
    )
    db_session.add(other_sim)
    db_session.flush()
    foreign_scene = SimulationScene(
        simulation_id=other_sim.id,
        title="Foreign",
        description="",
        scene_order=1,
    )
    db_session.add(foreign_scene)
    db_session.flush()

    result = await submit_grade.handler(
        {
            "user_progress_id": user_progress.id,
            "scene_id": foreign_scene.id,
            "rubric_scores": _valid_scores(),
            "strictness": "balanced",
        }
    )

    assert result["is_error"] is True
    text = result["content"][0]["text"]
    assert str(foreign_scene.id) in text
    assert str(simulation.id) in text
    # No scene_progress written for the foreign scene.
    assert (
        db_session.execute(
            select(SceneProgress).where(SceneProgress.scene_id == foreign_scene.id)
        ).scalar_one_or_none()
        is None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("strictness", ["lenient", "balanced", "strict"])
async def test_submit_grade_accepts_various_strictness_values(
    db_session: Session,
    patched_session_factory,
    simulation: Simulation,
    scene: SimulationScene,
    user_progress: UserProgress,
    strictness: str,
) -> None:
    """Every declared strictness value round-trips into the stored payload."""
    result = await submit_grade.handler(
        {
            "user_progress_id": user_progress.id,
            "scene_id": scene.id,
            "rubric_scores": _valid_scores(),
            "strictness": strictness,
        }
    )
    assert result["is_error"] is False
    assert result["structuredContent"]["strictness"] == strictness

    row = db_session.execute(
        select(SceneProgress)
        .where(SceneProgress.user_progress_id == user_progress.id)
        .where(SceneProgress.scene_id == scene.id)
    ).scalar_one()
    assert row.progress_data["grading_result"]["strictness"] == strictness


@pytest.mark.asyncio
async def test_submit_grade_updates_existing_scene_progress(
    db_session: Session,
    patched_session_factory,
    simulation: Simulation,
    scene: SimulationScene,
    user_progress: UserProgress,
) -> None:
    """Pre-existing ``progress_data`` keys survive; only ``grading_result`` changes."""
    existing = SceneProgress(
        user_progress_id=user_progress.id,
        scene_id=scene.id,
        progress_data={"turn_count": 7, "some_other_key": "preserved"},
    )
    db_session.add(existing)
    db_session.flush()

    result = await submit_grade.handler(
        {
            "user_progress_id": user_progress.id,
            "scene_id": scene.id,
            "rubric_scores": _valid_scores(),
            "strictness": "balanced",
        }
    )

    assert result["is_error"] is False
    row = db_session.execute(
        select(SceneProgress).where(SceneProgress.id == existing.id)
    ).scalar_one()
    assert row.progress_data["turn_count"] == 7
    assert row.progress_data["some_other_key"] == "preserved"
    assert row.progress_data["grading_result"]["rubric_scores"] == _valid_scores()


def test_extract_rubric_keys_handles_malformed_configs() -> None:
    """Non-dict configs, non-list criteria, and structurally broken criteria all yield ``[]``."""
    assert grading_tools._extract_rubric_keys(None) == []
    assert grading_tools._extract_rubric_keys("not a dict") == []  # type: ignore[arg-type]
    assert grading_tools._extract_rubric_keys({}) == []
    assert grading_tools._extract_rubric_keys({"criteria": "not-a-list"}) == []
    # Items without any known key field are skipped, not errored on.
    assert grading_tools._extract_rubric_keys(
        {"criteria": [{"foo": "bar"}, {"description": "   "}, {"description": "ok"}]}
    ) == ["ok"]
    # Non-dict entries inside the criteria list are skipped without error.
    assert grading_tools._extract_rubric_keys(
        {"criteria": ["just a string", 42, None, {"description": "kept"}]}
    ) == ["kept"]
    # Prefers ``description`` when multiple fields are present.
    assert grading_tools._extract_rubric_keys(
        {"criteria": [{"description": "A", "name": "B", "criterion_name": "C"}]}
    ) == ["A"]
    # Falls back to ``name`` and then ``criterion_name``.
    assert grading_tools._extract_rubric_keys(
        {"criteria": [{"name": "just-name"}, {"criterion_name": "just-cn"}]}
    ) == ["just-name", "just-cn"]


@pytest.mark.asyncio
async def test_submit_grade_database_error_returns_error_envelope() -> None:
    """An unexpected DB exception collapses to a generic error envelope.

    We patch the session factory so ``_submit_grade_sync`` gets a session
    whose ``get`` explodes. The tool must catch, log, rollback, and return
    the generic error envelope — not propagate the exception to the MCP
    runtime.
    """
    class _ExplodingSession:
        def get(self, *_a, **_kw):
            raise RuntimeError("synthetic db failure")

        def execute(self, *_a, **_kw):
            raise RuntimeError("synthetic db failure")

        def rollback(self) -> None:
            pass

        def close(self) -> None:
            pass

    with patch.object(grading_tools, "SessionLocal", lambda: _ExplodingSession()):
        result = await submit_grade.handler(
            {
                "user_progress_id": 1,
                "scene_id": 1,
                "rubric_scores": _valid_scores(),
                "strictness": "balanced",
            }
        )

    assert result == {
        "content": [{"type": "text", "text": "Failed to submit grade"}],
        "is_error": True,
    }
