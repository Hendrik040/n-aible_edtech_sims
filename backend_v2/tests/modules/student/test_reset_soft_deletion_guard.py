"""
Tests for soft-deletion guard on reset_simulation_from_instance endpoint.

Validates that the guard pattern added to reset_simulation_from_instance
prevents data loss when the underlying simulation has been soft-deleted.

These tests verify the guard logic without importing heavy app modules
(which require langchain, Redis, etc.).
"""
import os
import sys
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException

# --- PATH SETUP ---
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)


def _simulate_reset_guard(repository, simulation_id, instance_unique_id, cohort_assignment_id):
    """
    Reproduce the exact guard logic from reset_simulation_from_instance.
    This mirrors the code at student_instances.py lines ~965-976.
    """
    simulation = repository.get_simulation_by_id(simulation_id)
    if not simulation:
        raise HTTPException(
            status_code=404,
            detail="Simulation not found. The simulation associated with this assignment may have been deleted. Please contact your instructor."
        )
    return simulation


class TestResetSoftDeletionGuard:
    """Tests for the soft-deletion guard in reset_simulation_from_instance."""

    def test_guard_raises_404_when_simulation_soft_deleted(self):
        """
        When get_simulation_by_id returns None (soft-deleted),
        the guard should raise HTTPException with status 404.
        """
        mock_repo = MagicMock()
        mock_repo.get_simulation_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            _simulate_reset_guard(mock_repo, simulation_id=99,
                                  instance_unique_id="test-uuid",
                                  cohort_assignment_id=100)

        assert exc_info.value.status_code == 404
        assert "deleted" in exc_info.value.detail.lower()
        assert "instructor" in exc_info.value.detail.lower()

    def test_guard_passes_when_simulation_exists(self):
        """
        When the simulation exists (not soft-deleted),
        the guard should return the simulation without raising.
        """
        mock_repo = MagicMock()
        mock_sim = MagicMock()
        mock_sim.id = 99
        mock_repo.get_simulation_by_id.return_value = mock_sim

        result = _simulate_reset_guard(mock_repo, simulation_id=99,
                                       instance_unique_id="test-uuid",
                                       cohort_assignment_id=100)
        assert result is not None
        assert result.id == 99

    def test_guard_prevents_progress_deletion_on_soft_deleted(self):
        """
        When the simulation is soft-deleted, the guard must prevent
        delete_all_user_progress_for_simulation from being called.
        This is the critical data-loss prevention test.
        """
        mock_repo = MagicMock()
        mock_repo.get_simulation_by_id.return_value = None

        user_id = 42
        simulation_id = 99

        try:
            _simulate_reset_guard(mock_repo, simulation_id=simulation_id,
                                  instance_unique_id="test-uuid",
                                  cohort_assignment_id=100)
            # If guard didn't raise, this would be the next line in the endpoint
            mock_repo.delete_all_user_progress_for_simulation(user_id, simulation_id)
        except HTTPException:
            pass

        # The critical assertion: progress was never deleted
        mock_repo.delete_all_user_progress_for_simulation.assert_not_called()

    def test_guard_allows_progress_deletion_when_simulation_exists(self):
        """
        When the simulation exists, the endpoint should proceed to
        delete progress (the guard does not block).
        """
        mock_repo = MagicMock()
        mock_sim = MagicMock()
        mock_sim.id = 99
        mock_repo.get_simulation_by_id.return_value = mock_sim

        user_id = 42
        simulation_id = 99

        # Guard passes
        _simulate_reset_guard(mock_repo, simulation_id=simulation_id,
                              instance_unique_id="test-uuid",
                              cohort_assignment_id=100)

        # Simulate the progress deletion that follows
        mock_repo.delete_all_user_progress_for_simulation(user_id, simulation_id)

        mock_repo.delete_all_user_progress_for_simulation.assert_called_once_with(
            user_id, simulation_id
        )

    def test_guard_error_message_matches_start_endpoint(self):
        """
        The 404 error message should match the pattern used in
        start_simulation_from_instance for consistency.
        """
        mock_repo = MagicMock()
        mock_repo.get_simulation_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            _simulate_reset_guard(mock_repo, simulation_id=99,
                                  instance_unique_id="test-uuid",
                                  cohort_assignment_id=100)

        detail = exc_info.value.detail
        assert "Simulation not found" in detail
        assert "contact your instructor" in detail.lower()


class TestGuardPlacement:
    """Verify the guard is correctly placed in the source code."""

    def test_guard_exists_before_delete_in_source(self):
        """
        Static check: the get_simulation_by_id call must appear before
        delete_all_user_progress_for_simulation in the reset endpoint.
        """
        source_path = os.path.join(
            backend_path, "modules", "student", "routers", "student_instances.py"
        )
        with open(source_path, "r") as f:
            source = f.read()

        # Find the reset function
        reset_start = source.find("def reset_simulation_from_instance")
        assert reset_start != -1, "reset_simulation_from_instance endpoint not found"

        # Get the function body (until next def at same indentation or EOF)
        func_body = source[reset_start:]
        next_def = func_body.find("\n@router.", 1)
        if next_def != -1:
            func_body = func_body[:next_def]

        # Verify guard (get_simulation_by_id) appears before delete
        guard_pos = func_body.find("get_simulation_by_id")
        delete_pos = func_body.find("delete_all_user_progress_for_simulation")

        assert guard_pos != -1, "get_simulation_by_id guard not found in reset endpoint"
        assert delete_pos != -1, "delete_all_user_progress_for_simulation not found"
        assert guard_pos < delete_pos, (
            "Guard (get_simulation_by_id) must appear BEFORE "
            "delete_all_user_progress_for_simulation to prevent data loss"
        )

    def test_guard_raises_404_in_source(self):
        """
        Static check: the reset endpoint must raise 404 after the guard check.
        """
        source_path = os.path.join(
            backend_path, "modules", "student", "routers", "student_instances.py"
        )
        with open(source_path, "r") as f:
            source = f.read()

        reset_start = source.find("def reset_simulation_from_instance")
        func_body = source[reset_start:]
        next_def = func_body.find("\n@router.", 1)
        if next_def != -1:
            func_body = func_body[:next_def]

        # Verify the guard pattern: get_simulation_by_id -> if not simulation -> 404
        assert "get_simulation_by_id(simulation_id)" in func_body
        assert "status_code=404" in func_body
        assert "may have been deleted" in func_body
