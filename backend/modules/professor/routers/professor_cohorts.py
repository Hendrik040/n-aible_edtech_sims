"""
Professor cohorts router - Thin HTTP layer for cohort management
"""
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from common.db.core import get_db
from common.db.models import User
from app.dependencies import require_professor
from modules.cohorts.service import CohortService
from modules.cohorts.schemas import (
    CohortCreate, CohortUpdate, CohortResponse, CohortListResponse,
    CohortStudentCreate, CohortStudentUpdate, CohortStudentResponse,
    CohortSimulationCreate, CohortSimulationResponse, BulkRemoveStudentsRequest,
    InviteLinkCreate, InviteLinkResponse, InviteLinksListResponse, ClearExpiredResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/professor/cohorts", tags=["Professor Cohorts"])


def get_cohort_service(db: Session = Depends(get_db)) -> CohortService:
    """Dependency to get cohort service"""
    return CohortService(db)


# --- COHORT CRUD ENDPOINTS ---

@router.get("", response_model=List[CohortListResponse])
@router.get("/", response_model=List[CohortListResponse])
async def get_cohorts(
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: str = Query(None),
    status: str = Query(None),
    service: CohortService = Depends(get_cohort_service)
):
    """Get all cohorts with optional filtering"""
    try:
        return service.get_cohorts(
            user_id=current_user.id,
            user_role=current_user.role,
            skip=skip,
            limit=limit,
            search=search,
            status=status
        )
    except ImportError as e:
        logger.error(f"Error in get_cohorts: {str(e)}")
        raise HTTPException(status_code=500, detail="Cohort models not available. Please add them to common/db/models.py")
    except Exception as e:
        logger.error(f"Error in get_cohorts: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.post("/refresh-assignments")
async def refresh_assigned_simulations(
    current_user: User = Depends(require_professor),
    service: CohortService = Depends(get_cohort_service)
):
    """Recalculate time_spent for all student instances in the professor's cohorts."""
    try:
        result = service.refresh_assigned_simulations(current_user.id)
        return {"status": "ok", **result}
    except Exception as e:
        logger.error(f"Error in refresh_assigned_simulations: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to refresh assignments")


@router.get("/admin/all", response_model=List[CohortListResponse])
async def get_all_cohorts_admin(
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    service: CohortService = Depends(get_cohort_service)
):
    """Admin-only endpoint to get all cohorts across all users"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        return service.get_cohorts(
            user_id=current_user.id,
            user_role="admin",  # Force admin role to see all
            skip=skip,
            limit=limit
        )
    except Exception as e:
        logger.error(f"Error in get_all_cohorts_admin: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/{cohort_unique_id}", response_model=CohortResponse)
async def get_cohort(
    cohort_unique_id: str,
    current_user: User = Depends(require_professor),
    service: CohortService = Depends(get_cohort_service)
):
    """Get a specific cohort with students and simulations"""
    try:
        return service.get_cohort(
            unique_id=cohort_unique_id,
            user_id=current_user.id,
            user_role=current_user.role
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error in get_cohort: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=CohortResponse)
@router.post("/", response_model=CohortResponse)
async def create_cohort(
    cohort_data: CohortCreate,
    current_user: User = Depends(require_professor),
    service: CohortService = Depends(get_cohort_service)
):
    """Create a new cohort"""
    try:
        return service.create_cohort(cohort_data, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error in create_cohort: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{cohort_unique_id}", response_model=CohortResponse)
async def update_cohort(
    cohort_unique_id: str,
    cohort_data: CohortUpdate,
    current_user: User = Depends(require_professor),
    service: CohortService = Depends(get_cohort_service)
):
    """Update a cohort"""
    try:
        return service.update_cohort(
            unique_id=cohort_unique_id,
            cohort_data=cohort_data,
            user_id=current_user.id,
            user_role=current_user.role
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error in update_cohort: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{cohort_unique_id}")
async def delete_cohort(
    cohort_unique_id: str,
    current_user: User = Depends(require_professor),
    service: CohortService = Depends(get_cohort_service)
):
    """Delete a cohort and all related data"""
    try:
        deletion_info = service.delete_cohort(
            unique_id=cohort_unique_id,
            user_id=current_user.id,
            user_role=current_user.role
        )
        return {
            "message": "Cohort deleted successfully",
            **deletion_info
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting cohort: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete cohort. Please try again.")


# --- STUDENT MANAGEMENT ENDPOINTS ---

@router.get("/{cohort_unique_id}/students", response_model=List[CohortStudentResponse])
async def get_cohort_students(
    cohort_unique_id: str,
    current_user: User = Depends(require_professor),
    service: CohortService = Depends(get_cohort_service)
):
    """Get all students in a cohort"""
    try:
        return service.get_cohort_students(
            unique_id=cohort_unique_id,
            user_id=current_user.id,
            user_role=current_user.role
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error in get_cohort_students: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{cohort_id}/students", response_model=CohortStudentResponse)
async def add_student_to_cohort(
    cohort_id: int,
    student_data: CohortStudentCreate,
    current_user: User = Depends(require_professor),
    service: CohortService = Depends(get_cohort_service)
):
    """Add a student to a cohort"""
    try:
        return service.add_student_to_cohort(
            cohort_id=cohort_id,
            student_data=student_data,
            user_id=current_user.id,
            user_role=current_user.role
        )
    except ValueError as e:
        raise HTTPException(status_code=400 if "already enrolled" in str(e).lower() else 404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error in add_student_to_cohort: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{cohort_unique_id}/students/{student_id}", response_model=CohortStudentResponse)
async def update_student_enrollment(
    cohort_unique_id: str,
    student_id: int,
    student_data: CohortStudentUpdate,
    current_user: User = Depends(require_professor),
    service: CohortService = Depends(get_cohort_service)
):
    """Update a student's enrollment status in a cohort"""
    try:
        return service.update_student_enrollment(
            unique_id=cohort_unique_id,
            student_id=student_id,
            student_data=student_data,
            user_id=current_user.id,
            user_role=current_user.role
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error in update_student_enrollment: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{cohort_unique_id}/students/{student_id}")
async def remove_student_from_cohort(
    cohort_unique_id: str,
    student_id: int,
    current_user: User = Depends(require_professor),
    service: CohortService = Depends(get_cohort_service)
):
    """Remove a student from a cohort"""
    try:
        return service.remove_student_from_cohort(
            unique_id=cohort_unique_id,
            student_id=student_id,
            user_id=current_user.id,
            user_role=current_user.role
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error removing student from cohort: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to remove student: {str(e)}")


@router.post("/{cohort_unique_id}/students/remove")
async def remove_multiple_students_from_cohort(
    cohort_unique_id: str,
    request: BulkRemoveStudentsRequest,
    current_user: User = Depends(require_professor),
    service: CohortService = Depends(get_cohort_service)
):
    """Remove multiple students from a cohort"""
    try:
        return service.remove_multiple_students_from_cohort(
            unique_id=cohort_unique_id,
            student_ids=request.student_ids,
            user_id=current_user.id,
            user_role=current_user.role
        )
    except ValueError as e:
        raise HTTPException(status_code=400 if "no student" in str(e).lower() else 404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error removing students from cohort: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to remove students: {str(e)}")


# --- SIMULATION MANAGEMENT ENDPOINTS ---

@router.get("/{cohort_unique_id}/simulations", response_model=List[CohortSimulationResponse])
async def get_cohort_simulations(
    cohort_unique_id: str,
    current_user: User = Depends(require_professor),
    service: CohortService = Depends(get_cohort_service)
):
    """Get all simulations assigned to a cohort"""
    try:
        return service.get_cohort_simulations(
            unique_id=cohort_unique_id,
            user_id=current_user.id,
            user_role=current_user.role
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error in get_cohort_simulations: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{cohort_id}/simulations", response_model=CohortSimulationResponse)
async def assign_simulation_to_cohort(
    cohort_id: int,
    simulation_data: CohortSimulationCreate,
    current_user: User = Depends(require_professor),
    service: CohortService = Depends(get_cohort_service)
):
    """Assign a simulation to a cohort"""
    try:
        return service.assign_simulation_to_cohort(
            cohort_id=cohort_id,
            simulation_data=simulation_data,
            user_id=current_user.id,
            user_role=current_user.role
        )
    except ValueError as e:
        status_code = 400 if "draft" in str(e).lower() or "not found" in str(e).lower() else 404
        raise HTTPException(status_code=status_code, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error in assign_simulation_to_cohort: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{cohort_id}/simulations/{simulation_assignment_id}")
async def remove_simulation_from_cohort(
    cohort_id: int,
    simulation_assignment_id: int,
    current_user: User = Depends(require_professor),
    service: CohortService = Depends(get_cohort_service)
):
    """Remove a simulation assignment from a cohort"""
    try:
        return service.remove_simulation_from_cohort(
            cohort_id=cohort_id,
            simulation_assignment_id=simulation_assignment_id,
            user_id=current_user.id,
            user_role=current_user.role
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error removing simulation from cohort: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to remove simulation: {str(e)}")


# --- INVITE LINK ENDPOINTS ---

@router.get("/{cohort_id}/invites", response_model=InviteLinksListResponse)
async def get_invite_links(
    cohort_id: int,
    current_user: User = Depends(require_professor),
    service: CohortService = Depends(get_cohort_service)
):
    """Get all invite links for a cohort"""
    try:
        return service.get_invite_links(
            cohort_id=cohort_id,
            user_id=current_user.id,
            user_role=current_user.role
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting invite links: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{cohort_id}/invites", response_model=InviteLinkResponse)
async def create_invite_link(
    cohort_id: int,
    invite_data: InviteLinkCreate,
    current_user: User = Depends(require_professor),
    service: CohortService = Depends(get_cohort_service)
):
    """Create a new invite link for a cohort"""
    try:
        return service.create_invite_link(
            cohort_id=cohort_id,
            invite_data=invite_data,
            user_id=current_user.id,
            user_role=current_user.role
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating invite link: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{cohort_id}/invites/clear-expired", response_model=ClearExpiredResponse)
async def clear_expired_invites(
    cohort_id: int,
    current_user: User = Depends(require_professor),
    service: CohortService = Depends(get_cohort_service)
):
    """Clear all expired and used invite links for a cohort"""
    try:
        return service.clear_expired_invites(
            cohort_id=cohort_id,
            user_id=current_user.id,
            user_role=current_user.role
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error clearing expired invites: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{cohort_id}/invites/{invite_id}")
async def delete_invite_link(
    cohort_id: int,
    invite_id: int,
    current_user: User = Depends(require_professor),
    service: CohortService = Depends(get_cohort_service)
):
    """Delete a specific invite link"""
    try:
        return service.delete_invite_link(
            cohort_id=cohort_id,
            invite_id=invite_id,
            user_id=current_user.id,
            user_role=current_user.role
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting invite link: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
