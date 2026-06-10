"""
Analytics module - Cohort and simulation analytics for professors

Provides aggregated performance metrics, grade distributions, engagement
trends, and at-risk student detection across cohorts and assignments.
"""
from .repository import AnalyticsRepository
from .service import AnalyticsService

__all__ = ["AnalyticsRepository", "AnalyticsService"]
