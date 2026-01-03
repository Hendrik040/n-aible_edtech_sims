"""
Professor module schemas for API request/response models.
"""
from pydantic import BaseModel
from typing import Optional, List, Literal
from datetime import datetime


class DashboardStatsResponse(BaseModel):
    """Dashboard statistics response model."""
    total_simulations: int
    active_students: int
    avg_completion_rate: float  # Percentage (0-100)
    avg_time_per_simulation: Optional[str]  # Formatted time string like "2.4 hrs"
    simulations_this_month: int
    students_growth_percent: Optional[float]  # Percentage growth from last month
    completion_improvement_percent: Optional[float]  # Percentage improvement
    typical_time_range: Optional[str]  # e.g., "2-3 hrs"


class ActivityItem(BaseModel):
    """Single activity item in recent activity feed."""
    type: Literal["completion", "enrollment", "simulation_created"]
    title: str
    description: str
    timestamp: datetime
    count: Optional[int] = None  # For grouped activities like "3 students completed"
    simulation_id: Optional[int] = None
    cohort_id: Optional[int] = None


class RecentActivityResponse(BaseModel):
    """Recent activity response model."""
    activities: List[ActivityItem]

