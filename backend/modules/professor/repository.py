"""
Professor repository - Database operations for professor dashboard stats.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc

logger = logging.getLogger(__name__)

# Import models
try:
    from common.db.models import (
        Simulation, Cohort, CohortStudent, CohortSimulation, 
        StudentSimulationInstance, User
    )
    MODELS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Models not available: {e}")
    MODELS_AVAILABLE = False
    Simulation = None
    Cohort = None
    CohortStudent = None
    CohortSimulation = None
    StudentSimulationInstance = None
    User = None


class ProfessorRepository:
    """Repository for professor dashboard statistics."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_dashboard_stats(self, professor_id: int) -> Dict:
        """
        Get dashboard statistics for a professor.
        
        OPTIMIZATION: Uses batched queries to avoid N+1 problems.
        All stats calculated in minimal queries following the architecture pattern.
        """
        if not MODELS_AVAILABLE:
            return self._empty_stats()
        
        # Get current month boundaries
        now = datetime.now(timezone.utc)
        current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
        last_month_end = current_month_start - timedelta(seconds=1)
        
        # 1. Total simulations (owned by professor)
        total_simulations = self.db.query(func.count(Simulation.id)).filter(
            Simulation.created_by == professor_id,
            Simulation.deleted_at.is_(None)
        ).scalar() or 0
        
        # 2. Simulations created this month
        simulations_this_month = self.db.query(func.count(Simulation.id)).filter(
            Simulation.created_by == professor_id,
            Simulation.deleted_at.is_(None),
            Simulation.created_at >= current_month_start
        ).scalar() or 0
        
        # 3. Get all cohorts owned by professor
        professor_cohorts = self.db.query(Cohort.id).filter(
            Cohort.created_by == professor_id
        ).all()
        cohort_ids = [c[0] for c in professor_cohorts]
        
        # 4. Active students (approved students in professor's cohorts)
        active_students = 0
        students_last_month = 0
        if cohort_ids:
            active_students = self.db.query(func.count(func.distinct(CohortStudent.student_id))).filter(
                CohortStudent.cohort_id.in_(cohort_ids),
                CohortStudent.status == "approved"
            ).scalar() or 0
            
            # Students last month (for growth calculation)
            students_last_month = self.db.query(func.count(func.distinct(CohortStudent.student_id))).filter(
                CohortStudent.cohort_id.in_(cohort_ids),
                CohortStudent.status == "approved",
                CohortStudent.created_at <= last_month_end
            ).scalar() or 0
        
        # 5. Average completion rate and time (from StudentSimulationInstance)
        # Get all instances for simulations in professor's cohorts
        avg_completion = None
        avg_time_seconds = None
        completion_last_month = None
        
        if cohort_ids:
            # Get instances linked to professor's cohorts
            instances_query = self.db.query(
                StudentSimulationInstance.completion_percentage,
                StudentSimulationInstance.total_time_spent,
                StudentSimulationInstance.created_at
            ).join(
                CohortSimulation, 
                StudentSimulationInstance.cohort_assignment_id == CohortSimulation.id
            ).filter(
                CohortSimulation.cohort_id.in_(cohort_ids),
                StudentSimulationInstance.status.in_(["in_progress", "completed", "submitted", "graded"])
            )
            
            instances = instances_query.all()
            
            if instances:
                # Calculate average completion rate
                completion_values = [inst.completion_percentage for inst in instances if inst.completion_percentage is not None]
                if completion_values:
                    avg_completion = sum(completion_values) / len(completion_values)
                
                # Calculate average time (in seconds)
                time_values = [inst.total_time_spent for inst in instances if inst.total_time_spent is not None and inst.total_time_spent > 0]
                if time_values:
                    avg_time_seconds = sum(time_values) / len(time_values)
                
                # Completion rate last month (for improvement calculation)
                instances_last_month = [
                    inst for inst in instances 
                    if inst.created_at and inst.created_at <= last_month_end
                ]
                if instances_last_month:
                    completion_values_last = [
                        inst.completion_percentage 
                        for inst in instances_last_month 
                        if inst.completion_percentage is not None
                    ]
                    if completion_values_last:
                        completion_last_month = sum(completion_values_last) / len(completion_values_last)
        
        # Calculate growth percentages
        students_growth_percent = None
        if students_last_month > 0:
            students_growth_percent = ((active_students - students_last_month) / students_last_month) * 100
        
        completion_improvement_percent = None
        if avg_completion is not None and completion_last_month is not None and completion_last_month > 0:
            completion_improvement_percent = avg_completion - completion_last_month
        
        # Format average time
        avg_time_formatted = None
        typical_range = None
        if avg_time_seconds is not None:
            hours = avg_time_seconds / 3600
            avg_time_formatted = f"{hours:.1f} hrs"
            # Calculate typical range (mean ± 0.5 hours)
            min_hours = max(0, hours - 0.5)
            max_hours = hours + 0.5
            typical_range = f"{min_hours:.1f}-{max_hours:.1f} hrs"
        
        return {
            "total_simulations": total_simulations,
            "active_students": active_students,
            "avg_completion_rate": avg_completion or 0.0,
            "avg_time_per_simulation": avg_time_formatted,
            "simulations_this_month": simulations_this_month,
            "students_growth_percent": students_growth_percent,
            "completion_improvement_percent": completion_improvement_percent,
            "typical_time_range": typical_range
        }
    
    def _empty_stats(self) -> Dict:
        """Return empty stats when models are not available."""
        return {
            "total_simulations": 0,
            "active_students": 0,
            "avg_completion_rate": 0.0,
            "avg_time_per_simulation": None,
            "simulations_this_month": 0,
            "students_growth_percent": None,
            "completion_improvement_percent": None,
            "typical_time_range": None
        }
    
    def get_recent_activity(self, professor_id: int, limit: int = 10) -> List[Dict]:
        """
        Get recent activity for professor's dashboard.
        
        Returns a mix of:
        - Student completions (grouped by simulation)
        - New student enrollments (grouped by cohort)
        - New simulations created
        
        OPTIMIZATION: Uses batched queries to avoid N+1.
        """
        if not MODELS_AVAILABLE:
            return []
        
        activities = []
        
        # Get professor's cohort IDs
        cohort_ids = [c[0] for c in self.db.query(Cohort.id).filter(
            Cohort.created_by == professor_id
        ).all()]
        
        # 1. Recent completions (last 7 days, grouped by simulation)
        if cohort_ids:
            # Get recent completions with simulation info, grouped by simulation
            recent_completions = self.db.query(
                Simulation.id.label('simulation_id'),
                Simulation.title.label('simulation_title'),
                func.count(StudentSimulationInstance.id).label('completion_count'),
                func.max(StudentSimulationInstance.completed_at).label('latest_completion')
            ).join(
                CohortSimulation,
                StudentSimulationInstance.cohort_assignment_id == CohortSimulation.id
            ).join(
                Simulation,
                CohortSimulation.simulation_id == Simulation.id
            ).filter(
                CohortSimulation.cohort_id.in_(cohort_ids),
                StudentSimulationInstance.status.in_(["completed", "submitted", "graded"]),
                StudentSimulationInstance.completed_at.isnot(None),
                StudentSimulationInstance.completed_at >= datetime.now(timezone.utc) - timedelta(days=7)
            ).group_by(
                Simulation.id,
                Simulation.title
            ).order_by(
                desc(func.max(StudentSimulationInstance.completed_at))
            ).limit(limit).all()
            
            for completion in recent_completions:
                activities.append({
                    "type": "completion",
                    "title": f'{completion.completion_count} student{"s" if completion.completion_count > 1 else ""} completed "{completion.simulation_title}"',
                    "description": f'{completion.completion_count} student{"s" if completion.completion_count > 1 else ""} completed "{completion.simulation_title}"',
                    "timestamp": completion.latest_completion,
                    "count": completion.completion_count,
                    "simulation_id": completion.simulation_id,
                    "cohort_id": None
                })
        
        # 2. Recent enrollments (last 7 days, grouped by cohort)
        if cohort_ids:
            recent_enrollments = self.db.query(
                Cohort.id.label('cohort_id'),
                Cohort.title.label('cohort_title'),
                func.count(CohortStudent.id).label('enrollment_count'),
                func.max(CohortStudent.created_at).label('latest_enrollment')
            ).join(
                Cohort,
                CohortStudent.cohort_id == Cohort.id
            ).filter(
                CohortStudent.cohort_id.in_(cohort_ids),
                CohortStudent.status == "approved",
                CohortStudent.created_at >= datetime.now(timezone.utc) - timedelta(days=7)
            ).group_by(
                Cohort.id,
                Cohort.title
            ).order_by(
                desc(func.max(CohortStudent.created_at))
            ).limit(limit).all()
            
            for enrollment in recent_enrollments:
                activities.append({
                    "type": "enrollment",
                    "title": f'{enrollment.enrollment_count} new student{"s" if enrollment.enrollment_count > 1 else ""} enrolled',
                    "description": f'{enrollment.enrollment_count} new student{"s" if enrollment.enrollment_count > 1 else ""} enrolled in "{enrollment.cohort_title}"',
                    "timestamp": enrollment.latest_enrollment,
                    "count": enrollment.enrollment_count,
                    "simulation_id": None,
                    "cohort_id": enrollment.cohort_id
                })
        
        # 3. Recent simulations created by professor (last 7 days)
        recent_simulations = self.db.query(
            Simulation.id,
            Simulation.title,
            Simulation.created_at
        ).filter(
            Simulation.created_by == professor_id,
            Simulation.deleted_at.is_(None),
            Simulation.created_at >= datetime.now(timezone.utc) - timedelta(days=7)
        ).order_by(
            desc(Simulation.created_at)
        ).limit(limit).all()
        
        for sim in recent_simulations:
            activities.append({
                "type": "simulation_created",
                "title": f'New simulation "{sim.title}" created',
                "description": f'New simulation "{sim.title}" created',
                "timestamp": sim.created_at,
                "count": None,
                "simulation_id": sim.id,
                "cohort_id": None
            })
        
        # Sort all activities by timestamp (most recent first) and limit
        activities.sort(key=lambda x: x["timestamp"], reverse=True)
        return activities[:limit]
