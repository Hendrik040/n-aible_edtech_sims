"""
Student cohort management API endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func
from sqlalchemy.sql.functions import coalesce
from typing import List, Dict, Any
import logging

from database.connection import get_db
from database.models import User, Cohort, CohortStudent, CohortSimulation, Scenario
from database.schemas import CohortResponse
from utilities.auth import require_student

router = APIRouter(prefix="/student", tags=["Student Cohorts"])
logger = logging.getLogger(__name__)

@router.get("/cohorts", response_model=List[Dict[str, Any]])
async def get_student_cohorts(
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Get cohorts that the current student is enrolled in"""
    
    # Create subqueries for counts to optimize performance
    student_count_subquery = db.query(
        CohortStudent.cohort_id,
        func.count(CohortStudent.id).label('student_count')
    ).filter(
        CohortStudent.status == "approved"
    ).group_by(CohortStudent.cohort_id).subquery()
    
    simulation_count_subquery = db.query(
        CohortSimulation.cohort_id,
        func.count(CohortSimulation.id).label('simulation_count')
    ).join(
        Scenario, CohortSimulation.simulation_id == Scenario.id
    ).filter(
        Scenario.is_draft == False,
        Scenario.status == "active"
    ).group_by(CohortSimulation.cohort_id).subquery()
    
    # Get cohorts where the student is enrolled with counts
    # Use selectinload to eager load creator data to avoid N+1 queries
    cohorts_query = db.query(Cohort, CohortStudent).options(
        selectinload(Cohort.creator)
    ).join(
        CohortStudent, Cohort.id == CohortStudent.cohort_id
    ).outerjoin(
        student_count_subquery,
        Cohort.id == student_count_subquery.c.cohort_id
    ).outerjoin(
        simulation_count_subquery,
        Cohort.id == simulation_count_subquery.c.cohort_id
    ).add_columns(
        coalesce(student_count_subquery.c.student_count, 0).label('student_count'),
        coalesce(simulation_count_subquery.c.simulation_count, 0).label('simulation_count')
    ).filter(
        CohortStudent.student_id == current_user.id,
        CohortStudent.status == "approved"
    )
    
    cohorts = []
    for row in cohorts_query:
        cohort = row[0]  # The Cohort object
        cohort_student = row[1]  # The CohortStudent object
        student_count = row[2]  # student_count from coalesce
        simulation_count = row[3]  # simulation_count from coalesce
        
        # Get professor info from the loaded relationship
        professor = cohort.creator
        
        cohorts.append({
            "id": cohort.id,
            "unique_id": cohort.unique_id,
            "title": cohort.title,
            "description": cohort.description,
            "course_code": cohort.course_code,
            "semester": cohort.semester,
            "year": cohort.year,
            "max_students": cohort.max_students,
            "is_active": cohort.is_active,
            "created_at": cohort.created_at,
            "enrollment_date": cohort_student.enrollment_date,
            "status": cohort_student.status,
            "professor": {
                "id": professor.id if professor else None,
                "name": professor.full_name if professor else "Unknown",
                "email": professor.email if professor else "Unknown"
            },
            "student_count": student_count,
            "simulation_count": simulation_count
        })
    
    return cohorts

@router.get("/cohorts/{cohort_unique_id}/simulations", response_model=List[Dict[str, Any]])
async def get_cohort_simulations(
    cohort_unique_id: str,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Get simulations assigned to a cohort that the student is enrolled in"""
    
    # Verify student is enrolled in the cohort
    cohort = db.query(Cohort).filter(Cohort.unique_id == cohort_unique_id).first()
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    # Check if student is enrolled
    enrollment = db.query(CohortStudent).filter(
        CohortStudent.cohort_id == cohort.id,
        CohortStudent.student_id == current_user.id,
        CohortStudent.status == "approved"
    ).first()
    
    if not enrollment:
        raise HTTPException(status_code=403, detail="Not enrolled in this cohort")
    
    # Get simulations assigned to this cohort (only published/active simulations)
    simulations_query = db.query(CohortSimulation, Scenario).join(
        Scenario, CohortSimulation.simulation_id == Scenario.id
    ).filter(
        CohortSimulation.cohort_id == cohort.id,
        Scenario.is_draft == False,  # Only show published simulations to students
        Scenario.status == "active"   # Ensure status is active (not draft or archived)
    )
    
    simulations = []
    for cohort_simulation, scenario in simulations_query:
        simulations.append({
            "id": cohort_simulation.id,
            "simulation_id": scenario.id,
            "title": scenario.title,
            "description": scenario.description,
            "assigned_at": cohort_simulation.assigned_at,
            "due_date": cohort_simulation.due_date,
            "is_required": cohort_simulation.is_required,
            "assigned_by": cohort_simulation.assigned_by
        })
    
    return simulations
