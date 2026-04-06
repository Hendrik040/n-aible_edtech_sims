"""
Tests for professor_regrade_simulation cohort-based authorization.

Verifies that:
1. Professors can regrade simulations for students in their own cohorts
2. Professors cannot regrade simulations for students in other professors' cohorts
3. Missing cohort assignment results in access denied
4. Missing instance returns 404
5. Missing user progress returns 404
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone


class TestProfessorRegradeAuthorization:
    """Tests for cohort-based auth in professor_regrade_simulation endpoint."""

    def _make_user(self, id=1, role="professor", email="prof@test.com"):
        user = MagicMock()
        user.id = id
        user.role = role
        user.email = email
        return user

    def _make_user_progress(self, id=1, user_id=10, simulation_id=100):
        up = MagicMock()
        up.id = id
        up.user_id = user_id
        up.simulation_id = simulation_id
        return up

    def _make_instance(self, cohort_created_by=None, has_cohort_assignment=True, has_cohort=True):
        instance = MagicMock()
        instance.ai_grade = 85.0
        instance.ai_feedback = "Good work"
        instance.ai_graded_at = datetime.now(timezone.utc)
        instance.user_progress_id = 1

        if not has_cohort_assignment:
            instance.cohort_assignment = None
        elif not has_cohort:
            instance.cohort_assignment = MagicMock()
            instance.cohort_assignment.cohort = None
        else:
            instance.cohort_assignment = MagicMock()
            instance.cohort_assignment.cohort = MagicMock()
            instance.cohort_assignment.cohort.created_by = cohort_created_by

        return instance

    @pytest.mark.asyncio
    async def test_regrade_allowed_for_cohort_owner(self):
        """Professor who owns the cohort can regrade."""
        from modules.professor.routers.professor_grading import professor_regrade_simulation

        professor = self._make_user(id=1)
        user_progress = self._make_user_progress()
        instance = self._make_instance(cohort_created_by=1)

        mock_db = MagicMock()

        # First query returns user_progress, second returns instance
        def query_side_effect(model):
            q = MagicMock()
            if model.__name__ == "UserProgress":
                q.filter.return_value.first.return_value = user_progress
            elif model.__name__ == "StudentSimulationInstance":
                q.options.return_value.filter.return_value.first.return_value = instance
            return q

        mock_db.query.side_effect = query_side_effect

        mock_grading = {"overall_score": 90, "overall_feedback": "Great", "scenes": []}

        with patch("modules.professor.routers.professor_grading.redis_manager") as mock_redis, \
             patch("modules.simulation.services.grading_service.GradingService") as MockGS, \
             patch("modules.simulation.repository.SimulationRepository"):
            mock_gs_instance = MockGS.return_value
            mock_gs_instance.get_simulation_grading = AsyncMock(return_value=mock_grading)

            result = await professor_regrade_simulation(
                user_progress_id=1,
                current_user=professor,
                db=mock_db
            )

        assert result["success"] is True
        assert result["new_grade"] == 90

    @pytest.mark.asyncio
    async def test_regrade_denied_for_non_cohort_owner(self):
        """Professor who does NOT own the cohort is denied."""
        from fastapi import HTTPException
        from modules.professor.routers.professor_grading import professor_regrade_simulation

        professor = self._make_user(id=1)
        user_progress = self._make_user_progress()
        instance = self._make_instance(cohort_created_by=999)  # Different professor

        mock_db = MagicMock()

        def query_side_effect(model):
            q = MagicMock()
            if model.__name__ == "UserProgress":
                q.filter.return_value.first.return_value = user_progress
            elif model.__name__ == "StudentSimulationInstance":
                q.options.return_value.filter.return_value.first.return_value = instance
            return q

        mock_db.query.side_effect = query_side_effect

        with pytest.raises(HTTPException) as exc_info:
            await professor_regrade_simulation(
                user_progress_id=1,
                current_user=professor,
                db=mock_db
            )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Access denied"

    @pytest.mark.asyncio
    async def test_regrade_denied_when_no_cohort_assignment(self):
        """Access denied when instance has no cohort_assignment."""
        from fastapi import HTTPException
        from modules.professor.routers.professor_grading import professor_regrade_simulation

        professor = self._make_user(id=1)
        user_progress = self._make_user_progress()
        instance = self._make_instance(has_cohort_assignment=False)

        mock_db = MagicMock()

        def query_side_effect(model):
            q = MagicMock()
            if model.__name__ == "UserProgress":
                q.filter.return_value.first.return_value = user_progress
            elif model.__name__ == "StudentSimulationInstance":
                q.options.return_value.filter.return_value.first.return_value = instance
            return q

        mock_db.query.side_effect = query_side_effect

        with pytest.raises(HTTPException) as exc_info:
            await professor_regrade_simulation(
                user_progress_id=1,
                current_user=professor,
                db=mock_db
            )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Access denied"

    @pytest.mark.asyncio
    async def test_regrade_denied_when_cohort_is_none(self):
        """Access denied when cohort_assignment.cohort is None."""
        from fastapi import HTTPException
        from modules.professor.routers.professor_grading import professor_regrade_simulation

        professor = self._make_user(id=1)
        user_progress = self._make_user_progress()
        instance = self._make_instance(has_cohort=False)

        mock_db = MagicMock()

        def query_side_effect(model):
            q = MagicMock()
            if model.__name__ == "UserProgress":
                q.filter.return_value.first.return_value = user_progress
            elif model.__name__ == "StudentSimulationInstance":
                q.options.return_value.filter.return_value.first.return_value = instance
            return q

        mock_db.query.side_effect = query_side_effect

        with pytest.raises(HTTPException) as exc_info:
            await professor_regrade_simulation(
                user_progress_id=1,
                current_user=professor,
                db=mock_db
            )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Access denied"

    @pytest.mark.asyncio
    async def test_regrade_404_when_no_instance(self):
        """404 when no StudentSimulationInstance found for user_progress_id."""
        from fastapi import HTTPException
        from modules.professor.routers.professor_grading import professor_regrade_simulation

        professor = self._make_user(id=1)
        user_progress = self._make_user_progress()

        mock_db = MagicMock()

        def query_side_effect(model):
            q = MagicMock()
            if model.__name__ == "UserProgress":
                q.filter.return_value.first.return_value = user_progress
            elif model.__name__ == "StudentSimulationInstance":
                q.options.return_value.filter.return_value.first.return_value = None
            return q

        mock_db.query.side_effect = query_side_effect

        with pytest.raises(HTTPException) as exc_info:
            await professor_regrade_simulation(
                user_progress_id=1,
                current_user=professor,
                db=mock_db
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Simulation instance not found"

    @pytest.mark.asyncio
    async def test_regrade_404_when_no_user_progress(self):
        """404 when user_progress_id doesn't exist."""
        from fastapi import HTTPException
        from modules.professor.routers.professor_grading import professor_regrade_simulation

        professor = self._make_user(id=1)

        mock_db = MagicMock()

        def query_side_effect(model):
            q = MagicMock()
            if model.__name__ == "UserProgress":
                q.filter.return_value.first.return_value = None
            return q

        mock_db.query.side_effect = query_side_effect

        with pytest.raises(HTTPException) as exc_info:
            await professor_regrade_simulation(
                user_progress_id=999,
                current_user=professor,
                db=mock_db
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "User progress not found"
