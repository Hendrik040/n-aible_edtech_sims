"""
Tests for turn-count reset / scene-transition persistence (Issue #368).

Verifies that:
1. `handle_timeout` triggers `progress_to_next_scene` and returns a scene
   transition payload when turn_count >= timeout_turns.
2. `handle_timeout` persists `turn_count=0` via `save_orchestrator_state`
   EVEN when `progress_to_next_scene` raises an exception AFTER the reset
   (the try/finally safety net).
3. `handle_timeout` returns None and does NOT call `progress_to_next_scene`
   when the turn limit has not been reached.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from modules.simulation.handlers.commands.timeout_handler import handle_timeout


def _make_orchestrator(turn_count: int):
    """Build a minimal orchestrator stand-in with a mutable state object."""
    state = SimpleNamespace(
        turn_count=turn_count,
        current_scene_index=0,
        current_scene_id=1,
        scene_completed=False,
        session_id="sess-1",
    )
    return SimpleNamespace(state=state, user_progress_id=1, simulation={"scenes": []})


@pytest.mark.asyncio
async def test_handle_timeout_progresses_scene_when_limit_reached():
    orchestrator = _make_orchestrator(turn_count=15)
    user_progress = MagicMock()
    current_scene = {"timeout_turns": 15, "max_turns": 15}

    scene_progression_handler = MagicMock()
    # Simulate reset-to-zero inside progress_to_next_scene (real behavior).
    def _progress(**kwargs):
        orchestrator.state.turn_count = 0
        orchestrator.state.current_scene_index = 1
        return {
            "next_scene_id": 2,
            "next_scene": {"id": 2},
            "scene_intro_message": "Welcome to scene 2",
        }
    scene_progression_handler.progress_to_next_scene.side_effect = _progress

    orchestrator_manager = MagicMock()

    result = await handle_timeout(
        orchestrator=orchestrator,
        user_progress=user_progress,
        current_scene=current_scene,
        current_scene_id=1,
        full_response="Some response",
        persona_name="Alice",
        persona_id=42,
        scene_progression_handler=scene_progression_handler,
        orchestrator_manager=orchestrator_manager,
        generate_scene_intro_fn=None,
    )

    assert result is not None, "Expected a timeout result when turn limit reached"
    payload = json.loads(result)
    assert payload["scene_completed"] is True
    assert payload["next_scene_id"] == 2
    assert payload["turn_count"] == 0
    scene_progression_handler.progress_to_next_scene.assert_called_once()
    # The fix: save_orchestrator_state MUST be called so the reset persists.
    orchestrator_manager.save_orchestrator_state.assert_called_once_with(
        orchestrator, user_progress
    )


@pytest.mark.asyncio
async def test_handle_timeout_returns_none_when_below_limit():
    orchestrator = _make_orchestrator(turn_count=5)
    user_progress = MagicMock()
    current_scene = {"timeout_turns": 15}

    scene_progression_handler = MagicMock()
    orchestrator_manager = MagicMock()

    result = await handle_timeout(
        orchestrator=orchestrator,
        user_progress=user_progress,
        current_scene=current_scene,
        current_scene_id=1,
        full_response="Some response",
        persona_name="Alice",
        persona_id=42,
        scene_progression_handler=scene_progression_handler,
        orchestrator_manager=orchestrator_manager,
        generate_scene_intro_fn=None,
    )

    assert result is None
    scene_progression_handler.progress_to_next_scene.assert_not_called()
    orchestrator_manager.save_orchestrator_state.assert_not_called()


@pytest.mark.asyncio
async def test_handle_timeout_persists_state_when_progression_raises_after_reset():
    """
    Regression for issue #368 phase 3: if progress_to_next_scene resets
    turn_count and then raises (e.g., scene intro generation fails), the
    in-memory reset must still be persisted via save_orchestrator_state so
    that the DB does not diverge from in-memory state.
    """
    orchestrator = _make_orchestrator(turn_count=15)
    user_progress = MagicMock()
    current_scene = {"timeout_turns": 15}

    scene_progression_handler = MagicMock()

    def _progress_then_raise(**kwargs):
        # Reset happens BEFORE the exception, matching real code path.
        orchestrator.state.turn_count = 0
        orchestrator.state.current_scene_index = 1
        raise RuntimeError("scene intro generation failed")

    scene_progression_handler.progress_to_next_scene.side_effect = _progress_then_raise
    orchestrator_manager = MagicMock()

    with pytest.raises(RuntimeError, match="scene intro generation failed"):
        await handle_timeout(
            orchestrator=orchestrator,
            user_progress=user_progress,
            current_scene=current_scene,
            current_scene_id=1,
            full_response="Some response",
            persona_name="Alice",
            persona_id=42,
            scene_progression_handler=scene_progression_handler,
            orchestrator_manager=orchestrator_manager,
            generate_scene_intro_fn=None,
        )

    # Critical assertion: state was saved even though progression raised.
    orchestrator_manager.save_orchestrator_state.assert_called_once_with(
        orchestrator, user_progress
    )
    # And the in-memory reset took effect before the raise.
    assert orchestrator.state.turn_count == 0


@pytest.mark.asyncio
async def test_handle_timeout_uses_max_turns_fallback():
    """When timeout_turns is missing, the function falls back to max_turns."""
    orchestrator = _make_orchestrator(turn_count=10)
    user_progress = MagicMock()
    current_scene = {"max_turns": 10}  # no timeout_turns key

    scene_progression_handler = MagicMock()
    scene_progression_handler.progress_to_next_scene.return_value = {
        "next_scene_id": 2,
        "next_scene": {"id": 2},
        "scene_intro_message": None,
    }
    orchestrator_manager = MagicMock()

    result = await handle_timeout(
        orchestrator=orchestrator,
        user_progress=user_progress,
        current_scene=current_scene,
        current_scene_id=1,
        full_response="resp",
        persona_name="Bob",
        persona_id=None,
        scene_progression_handler=scene_progression_handler,
        orchestrator_manager=orchestrator_manager,
        generate_scene_intro_fn=None,
    )

    assert result is not None
    scene_progression_handler.progress_to_next_scene.assert_called_once()
    # Persistence must also fire on the max_turns fallback path.
    orchestrator_manager.save_orchestrator_state.assert_called_once_with(
        orchestrator, user_progress
    )
