"""
Analytics API endpoints for professors

All endpoints are scoped to the authenticated professor: a cohort that exists
but belongs to another professor returns 404, never 403, so cohort IDs are
not enumerable.
"""
import logging
from fastapi import APIRouter, HTTPException, Depends, Query, status
from sqlalchemy.orm import Session

from common.db.core import get_db
from common.db.models import User
from app.dependencies import require_professor
from modules.analytics.service import (
    AnalyticsService,
    CohortNotFoundError,
    AssignmentNotFoundError,
    DEFAULT_RISK_THRESHOLD,
    DEFAULT_ENGAGEMENT_WEEKS,
    MAX_ENGAGEMENT_WEEKS,
)
from modules.analytics.schemas import (
    CohortAnalyticsOverview,
    CohortEngagementResponse,
    AtRiskReportResponse,
    AssignmentAnalyticsResponse,
    AssignmentDetailResponse,
    ProfessorDashboardResponse,
    GradeExportResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/professor/analytics", tags=["Professor Analytics"])


def get_analytics_service(db: Session = Depends(get_db)) -> AnalyticsService:
    """Dependency to get the analytics service."""
    return AnalyticsService(db)


@router.get("/dashboard", response_model=ProfessorDashboardResponse)
async def get_professor_dashboard(
    current_user: User = Depends(require_professor),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Cross-cohort analytics rollup for the professor landing page."""
    try:
        return service.get_professor_dashboard(current_user.id)
    except Exception as e:
        logger.error(f"Failed to build professor dashboard for user {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build analytics dashboard",
        )


@router.get("/cohorts/{cohort_id}/overview", response_model=CohortAnalyticsOverview)
async def get_cohort_overview(
    cohort_id: int,
    current_user: User = Depends(require_professor),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Headline metrics, completion funnel, and grade distribution for a cohort."""
    try:
        return service.get_cohort_overview(cohort_id, current_user.id)
    except CohortNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cohort not found",
        )
    except Exception as e:
        logger.error(f"Failed to build overview for cohort {cohort_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build cohort overview",
        )


@router.get("/cohorts/{cohort_id}/engagement", response_model=CohortEngagementResponse)
async def get_cohort_engagement(
    cohort_id: int,
    weeks: int = Query(
        DEFAULT_ENGAGEMENT_WEEKS,
        ge=1,
        le=MAX_ENGAGEMENT_WEEKS,
        description="Number of trailing ISO weeks to include",
    ),
    current_user: User = Depends(require_professor),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Weekly engagement trend (active students, sessions, submissions)."""
    try:
        return service.get_engagement_trend(cohort_id, current_user.id, weeks=weeks)
    except CohortNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cohort not found",
        )
    except Exception as e:
        logger.error(f"Failed to build engagement trend for cohort {cohort_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build engagement trend",
        )


@router.get("/cohorts/{cohort_id}/assignments", response_model=AssignmentAnalyticsResponse)
async def get_cohort_assignment_analytics(
    cohort_id: int,
    current_user: User = Depends(require_professor),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Per-assignment performance breakdown for a cohort."""
    try:
        return service.get_assignment_analytics(cohort_id, current_user.id)
    except CohortNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cohort not found",
        )
    except Exception as e:
        logger.error(f"Failed to build assignment analytics for cohort {cohort_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build assignment analytics",
        )


@router.get(
    "/cohorts/{cohort_id}/assignments/{cohort_simulation_id}",
    response_model=AssignmentDetailResponse,
)
async def get_assignment_detail(
    cohort_id: int,
    cohort_simulation_id: int,
    current_user: User = Depends(require_professor),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Deep-dive analytics for a single assignment within a cohort."""
    try:
        return service.get_assignment_detail(
            cohort_id, cohort_simulation_id, current_user.id
        )
    except CohortNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cohort not found",
        )
    except AssignmentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found in this cohort",
        )
    except Exception as e:
        logger.error(
            f"Failed to build assignment detail for assignment {cohort_simulation_id}: {e}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build assignment detail",
        )


@router.get("/cohorts/{cohort_id}/at-risk", response_model=AtRiskReportResponse)
async def get_at_risk_report(
    cohort_id: int,
    threshold: float = Query(
        DEFAULT_RISK_THRESHOLD,
        ge=0.0,
        le=1.0,
        description="Minimum risk score for a student to be included",
    ),
    current_user: User = Depends(require_professor),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Students flagged by the at-risk heuristic, highest risk first."""
    try:
        return service.get_at_risk_report(cohort_id, current_user.id, threshold=threshold)
    except CohortNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cohort not found",
        )
    except Exception as e:
        logger.error(f"Failed to build at-risk report for cohort {cohort_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build at-risk report",
        )


@router.get("/cohorts/{cohort_id}/grade-export", response_model=GradeExportResponse)
async def get_grade_export(
    cohort_id: int,
    current_user: User = Depends(require_professor),
    service: AnalyticsService = Depends(get_analytics_service),
):
    """Flat grade rows for every student x assignment cell, for CSV download."""
    try:
        return service.get_grade_export(cohort_id, current_user.id)
    except CohortNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cohort not found",
        )
    except Exception as e:
        logger.error(f"Failed to build grade export for cohort {cohort_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build grade export",
        )
