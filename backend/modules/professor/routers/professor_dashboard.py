"""
Professor dashboard router - Dashboard statistics endpoints
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from common.db.core import get_db
from common.db.models import User
from app.dependencies import require_professor
from modules.professor.service import ProfessorService
from modules.professor.schemas import DashboardStatsResponse, RecentActivityResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/professor/dashboard", tags=["Professor Dashboard"])


def get_professor_service(db: Session = Depends(get_db)) -> ProfessorService:
    """Dependency to get professor service"""
    return ProfessorService(db)


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    current_user: User = Depends(require_professor),
    service: ProfessorService = Depends(get_professor_service)
):
    """
    Get dashboard statistics for the current professor.
    
    Returns:
        - total_simulations: Total number of simulations created by professor
        - active_students: Number of approved students in professor's cohorts
        - avg_completion_rate: Average completion percentage across all simulations
        - avg_time_per_simulation: Average time spent per simulation (formatted)
        - simulations_this_month: Number of simulations created this month
        - students_growth_percent: Percentage growth in students from last month
        - completion_improvement_percent: Improvement in completion rate
        - typical_time_range: Typical time range for simulations
    
    OPTIMIZATION: Uses Redis caching (5 min TTL) and batched queries.
    """
    try:
        return service.get_dashboard_stats(current_user.id)
    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch dashboard stats: {str(e)}")


@router.get("/recent-activity", response_model=RecentActivityResponse)
async def get_recent_activity(
    limit: int = Query(10, ge=1, le=50, description="Number of activities to return"),
    current_user: User = Depends(require_professor),
    service: ProfessorService = Depends(get_professor_service)
):
    """
    Get recent activity for the current professor.
    
    Returns a mix of:
    - Student completions (grouped by simulation)
    - New student enrollments (grouped by cohort)
    - New simulations created
    
    OPTIMIZATION: Uses Redis caching (2 min TTL) and batched queries.
    """
    try:
        activities = service.get_recent_activity(current_user.id, limit)
        return RecentActivityResponse(activities=activities)
    except Exception as e:
        logger.error(f"Error fetching recent activity: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch recent activity: {str(e)}")

