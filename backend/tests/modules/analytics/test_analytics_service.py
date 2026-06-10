"""
Tests for the analytics service layer.

These tests cover the pure-Python aggregation logic in AnalyticsService.
Database-backed query methods are covered indirectly through the cohort
fixtures; the heavier statistical helpers are tested directly.
"""
import pytest
from datetime import datetime, timedelta, timezone

from modules.analytics.service import (
    AnalyticsService,
    DEFAULT_RISK_THRESHOLD,
    PASSING_GRADE,
    INACTIVITY_WINDOW_DAYS,
)


class FakeInstance:
    """Lightweight stand-in for StudentSimulationInstance."""

    def __init__(
        self,
        status="not_started",
        grade=None,
        is_overdue=False,
        total_time_spent=0,
        student_id=1,
    ):
        self.status = status
        self.grade = grade
        self.is_overdue = is_overdue
        self.total_time_spent = total_time_spent
        self.student_id = student_id


@pytest.fixture
def service():
    """AnalyticsService with no live DB session (pure-logic tests only)."""
    return AnalyticsService(db=None)


# ---------------------------------------------------------------------------
# Grade distribution
# ---------------------------------------------------------------------------

class TestGradeDistribution:
    def test_empty_grades_returns_zeroed_buckets(self, service):
        dist = service.build_grade_distribution([])
        assert dist.total_graded == 0
        assert dist.mean is None
        assert dist.median is None
        assert len(dist.buckets) == 10
        assert all(bucket.count == 0 for bucket in dist.buckets)

    def test_bucket_labels_cover_full_scale(self, service):
        dist = service.build_grade_distribution([])
        assert dist.buckets[0].label == "0-9"
        assert dist.buckets[5].label == "50-59"
        assert dist.buckets[9].label == "90-100"

    def test_grades_land_in_expected_buckets(self, service):
        dist = service.build_grade_distribution([5.0, 55.0, 59.9, 95.0])
        assert dist.buckets[0].count == 1
        assert dist.buckets[5].count == 2
        assert dist.buckets[9].count == 1
        assert dist.total_graded == 4

    def test_summary_statistics(self, service):
        grades = [60.0, 70.0, 80.0, 90.0]
        dist = service.build_grade_distribution(grades)
        assert dist.mean == 75.0
        assert dist.median == 75.0
        assert dist.min_grade == 60.0
        assert dist.max_grade == 90.0

    def test_single_grade_has_zero_std_dev(self, service):
        dist = service.build_grade_distribution([85.0])
        assert dist.std_dev == 0.0
        assert dist.total_graded == 1

    def test_negative_grade_is_clamped_into_first_bucket(self, service):
        dist = service.build_grade_distribution([-5.0])
        assert dist.buckets[0].count == 1

    def test_boundary_grades(self, service):
        dist = service.build_grade_distribution([0.0, 9.0, 10.0, 89.9, 90.0, 99.0])
        assert dist.buckets[0].count == 2
        assert dist.buckets[1].count == 1
        assert dist.buckets[8].count == 1
        assert dist.buckets[9].count == 2


# ---------------------------------------------------------------------------
# Risk scoring
# ---------------------------------------------------------------------------

class TestRiskScoring:
    def _now(self):
        return datetime(2026, 6, 1, tzinfo=timezone.utc)

    def test_no_instances_and_no_activity_is_high_risk(self, service):
        score, factors, signals = service._score_student_risk(
            instances=[],
            assigned_count=3,
            last_activity=None,
            now=self._now(),
        )
        # inactivity (0.25) + ungraded uncertainty (0.25 * 0.3) + not started (0.15)
        assert score == pytest.approx(0.475)
        assert "no recorded activity" in factors
        assert signals["inactivity"] == 1.0
        assert signals["not_started"] == 1.0

    def test_healthy_student_scores_low(self, service):
        now = self._now()
        instances = [
            FakeInstance(status="graded", grade=92.0),
            FakeInstance(status="graded", grade=88.0),
            FakeInstance(status="submitted"),
        ]
        score, factors, signals = service._score_student_risk(
            instances=instances,
            assigned_count=3,
            last_activity=now - timedelta(days=1),
            now=now,
        )
        assert score < 0.2
        assert signals["overdue"] == 0.0
        assert signals["low_grade"] == 0.0

    def test_failing_average_grade_raises_score(self, service):
        now = self._now()
        instances = [
            FakeInstance(status="graded", grade=30.0),
            FakeInstance(status="graded", grade=40.0),
        ]
        score, factors, signals = service._score_student_risk(
            instances=instances,
            assigned_count=2,
            last_activity=now - timedelta(days=2),
            now=now,
        )
        assert signals["low_grade"] > 0.0
        assert any("below passing" in f for f in factors)
        average = (30.0 + 40.0) / 2
        assert average < PASSING_GRADE

    def test_overdue_assignments_raise_score(self, service):
        now = self._now()
        instances = [
            FakeInstance(status="in_progress", is_overdue=True),
            FakeInstance(status="in_progress", is_overdue=True),
        ]
        score, factors, signals = service._score_student_risk(
            instances=instances,
            assigned_count=2,
            last_activity=now - timedelta(days=1),
            now=now,
        )
        assert signals["overdue"] == 1.0
        assert any("overdue" in f for f in factors)

    def test_inactivity_signal_caps_at_window(self, service):
        now = self._now()
        instances = [FakeInstance(status="in_progress")]
        _, _, signals_at_window = service._score_student_risk(
            instances=instances,
            assigned_count=1,
            last_activity=now - timedelta(days=INACTIVITY_WINDOW_DAYS),
            now=now,
        )
        _, _, signals_beyond = service._score_student_risk(
            instances=instances,
            assigned_count=1,
            last_activity=now - timedelta(days=INACTIVITY_WINDOW_DAYS * 3),
            now=now,
        )
        assert signals_at_window["inactivity"] == 1.0
        assert signals_beyond["inactivity"] == 1.0

    def test_naive_last_activity_is_treated_as_utc(self, service):
        now = self._now()
        naive = (now - timedelta(days=3)).replace(tzinfo=None)
        score, factors, signals = service._score_student_risk(
            instances=[FakeInstance(status="in_progress")],
            assigned_count=1,
            last_activity=naive,
            now=now,
        )
        assert 0.0 < signals["inactivity"] < 1.0

    def test_score_is_bounded(self, service):
        score, _, _ = service._score_student_risk(
            instances=[FakeInstance(status="graded", grade=0.0, is_overdue=True)],
            assigned_count=1,
            last_activity=None,
            now=self._now(),
        )
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_safe_rate_handles_zero_denominator(self, service):
        assert service._safe_rate(5, 0) == 0.0
        assert service._safe_rate(0, 0) == 0.0

    def test_safe_rate_rounds(self, service):
        assert service._safe_rate(1, 3) == 0.3333

    def test_as_minutes_converts_seconds(self, service):
        assert service._as_minutes(90) == 1.5
        assert service._as_minutes(None) == 0.0
        assert service._as_minutes(0) == 0.0
