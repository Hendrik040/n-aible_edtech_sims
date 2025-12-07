"""
Student cohort router - Thin HTTP layer for student cohort views
"""
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from common.db.core import get_db
from common.db.models import User
from modules.auth.dependencies import require_student
from modules.cohorts.service import CohortService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/student", tags=["Student Cohorts"])


def get_cohort_service(db: Session = Depends(get_db)) -> CohortService:
    """Dependency to get cohort service"""
    return CohortService(db)


@router.get("/cohorts", response_model=List[Dict[str, Any]])
async def get_student_cohorts(
    current_user: User = Depends(require_student),
    service: CohortService = Depends(get_cohort_service)
):
    """Get cohorts that the current student is enrolled in"""
    try:
        return service.get_student_cohorts(current_user.id)
    except Exception as e:
        logger.error(f"Error in get_student_cohorts: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch cohorts")


@router.get("/cohorts/{cohort_unique_id}/simulations", response_model=List[Dict[str, Any]])
async def get_cohort_simulations(
    cohort_unique_id: str,
    current_user: User = Depends(require_student),
    service: CohortService = Depends(get_cohort_service)
):
    """Get simulations assigned to a cohort that the student is enrolled in"""
    try:
        return service.get_student_cohort_simulations(cohort_unique_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error in get_cohort_simulations: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch simulations")
