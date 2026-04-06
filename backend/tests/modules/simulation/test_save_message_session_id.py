"""
Tests for save_message session ID resolution in SimulationService.

Verifies the three-tier session ID priority:
1. Caller-provided session_id
2. Active session from user_progress.orchestrator_data
3. Synthetic fallback
"""

import pytest
from unittest.mock import MagicMock, patch

from modules.simulation.service import SimulationService


def _make_user_progress(user_id, simulation_id, orchestrator_data=None):
    """Create a mock UserProgress with the given orchestrator_data."""
    up = MagicMock()
    up.user_id = user_id
    up.simulation_id = simulation_id
    up.orchestrator_data = orchestrator_data
    return up


def _make_scene(simulation_id):
    """Create a mock scene belonging to the given simulation."""
    scene = MagicMock()
    scene.simulation_id = simulation_id
    return scene


def _make_log(log_id=1, message_order=1):
    """Create a mock conversation log."""
    log = MagicMock()
    log.id = log_id
    log.message_order = message_order
    return log


class TestSaveMessageSessionIdResolution:
    """Verify that save_message resolves session_id with correct priority."""

    def _call_save_message(self, db_session, orchestrator_data=None, session_id=None):
        """Helper: call save_message and return the session_id passed to create_conversation_log."""
        service = SimulationService(db_session)

        user_progress = _make_user_progress(
            user_id=10, simulation_id=100, orchestrator_data=orchestrator_data
        )
        scene = _make_scene(simulation_id=100)

        service.repository.get_user_progress_by_id = MagicMock(return_value=user_progress)
        service.repository.get_scene_by_id = MagicMock(return_value=scene)
        service.repository.get_next_message_order = MagicMock(return_value=1)
        service.repository.create_conversation_log = MagicMock(return_value=_make_log())
        service.repository.db = MagicMock()

        service.save_message(
            user_id=10,
            user_progress_id=1,
            scene_id=5,
            sender_name="system",
            message_content="Hello",
            message_type="system",
            session_id=session_id,
        )

        call_kwargs = service.repository.create_conversation_log.call_args
        return call_kwargs.kwargs.get("session_id") or call_kwargs[1].get("session_id")

    def test_caller_provided_session_id_takes_priority(self, db_session):
        """When caller provides session_id, it should be used regardless of orchestrator_data."""
        result = self._call_save_message(
            db_session,
            orchestrator_data={"state": {"session_id": "orch-session-123"}},
            session_id="caller-session-456",
        )
        assert result == "caller-session-456"

    def test_orchestrator_data_session_id_used_when_no_caller_id(self, db_session):
        """When no caller session_id, should use the active session from orchestrator_data."""
        result = self._call_save_message(
            db_session,
            orchestrator_data={"state": {"session_id": "orch-session-123"}},
            session_id=None,
        )
        assert result == "orch-session-123"

    def test_synthetic_fallback_when_no_session_available(self, db_session):
        """When no caller session_id and no orchestrator_data session, should generate synthetic ID."""
        result = self._call_save_message(
            db_session,
            orchestrator_data=None,
            session_id=None,
        )
        assert result.startswith("system_1_5_")

    def test_synthetic_fallback_when_orchestrator_data_has_no_state(self, db_session):
        """When orchestrator_data exists but has no 'state' key, should fall back to synthetic."""
        result = self._call_save_message(
            db_session,
            orchestrator_data={"some_other_key": "value"},
            session_id=None,
        )
        assert result.startswith("system_1_5_")

    def test_synthetic_fallback_when_state_has_no_session_id(self, db_session):
        """When orchestrator_data has 'state' but no 'session_id', should fall back to synthetic."""
        result = self._call_save_message(
            db_session,
            orchestrator_data={"state": {"turn_count": 3}},
            session_id=None,
        )
        assert result.startswith("system_1_5_")

    def test_empty_orchestrator_data_dict(self, db_session):
        """When orchestrator_data is an empty dict, should fall back to synthetic."""
        result = self._call_save_message(
            db_session,
            orchestrator_data={},
            session_id=None,
        )
        assert result.startswith("system_1_5_")
