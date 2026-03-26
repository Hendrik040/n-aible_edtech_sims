"""
Professor grade export router - Export student grades for a cohort as CSV
"""
import os
import json
import csv
import io
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, selectinload

from common.db.core import get_db
from common.db.models import User, StudentSimulationInstance
from common.db.models.cohorts.cohort import Cohort, CohortStudent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/professor/grades", tags=["Professor Grade Export"])


@router.get("/cohorts/{cohort_id}/export")
async def export_cohort_grades(
    cohort_id: int,
    db: Session = Depends(get_db),
):
    """Export all student grades for a cohort as a CSV file."""

    cohort = db.query(Cohort).filter(Cohort.id == cohort_id).first()

    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")

    students = db.query(CohortStudent).options(
        selectinload(CohortStudent.student)
    ).filter(
        CohortStudent.cohort_id == cohort_id,
        CohortStudent.status == "approved",
    ).all()

    rows: List[Dict[str, Any]] = []

    for enrollment in students:
        instances = db.query(StudentSimulationInstance).options(
            selectinload(StudentSimulationInstance.simulation)
        ).filter(
            StudentSimulationInstance.student_id == enrollment.student_id,
        ).all()

        for instance in instances:
            rows.append({
                "student_id": enrollment.student_id,
                "student_email": enrollment.student.email if enrollment.student else "",
                "student_name": enrollment.student.full_name if enrollment.student else "",
                "simulation": instance.simulation.title if instance.simulation else "",
                "status": instance.status,
                "score": instance.final_score if instance.final_score is not None else "",
                "completion_percentage": instance.completion_percentage,
                "started_at": str(instance.started_at) if instance.started_at else "",
                "completed_at": str(instance.completed_at) if instance.completed_at else "",
            })

    output = io.StringIO()
    fieldnames = ["student_id", "student_email", "student_name", "simulation",
                  "status", "score", "completion_percentage", "started_at", "completed_at"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

    output.seek(0)
    filename = f"cohort_{cohort_id}_grades.csv"

    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
