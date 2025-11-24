"""
Data isolation utilities for role-based access control
"""
from typing import Any, Optional, List
from sqlalchemy.orm import Session, Query
from sqlalchemy import and_, or_
from database.models import User, Cohort, Scenario, UserProgress, CohortStudent

def filter_by_role(db_query: Query, current_user: User, target_role: Optional[str] = None) -> Query:
    """
    Filter database query based on user role and data isolation rules
    
    Args:
        db_query: SQLAlchemy query to filter
        current_user: Current authenticated user
        target_role: Optional target role to filter by
        
    Returns:
        Filtered query
    """
    # Admins can see everything
    if current_user.role == 'admin':
        return db_query
    
    # Role-based filtering
    if current_user.role == 'professor':
        # Professors can see their own data and student data within their cohorts
        if hasattr(db_query.column_descriptions[0]['entity'], 'created_by'):
            # Filter by ownership
            db_query = db_query.filter(
                or_(
                    db_query.column_descriptions[0]['entity'].created_by == current_user.id,
                    current_user.role == 'admin'
                )
            )
    
    elif current_user.role == 'student':
        # Students can only see their own data and public data
        if hasattr(db_query.column_descriptions[0]['entity'], 'user_id'):
            # Filter by user ownership
            db_query = db_query.filter(
                db_query.column_descriptions[0]['entity'].user_id == current_user.id
            )
        elif hasattr(db_query.column_descriptions[0]['entity'], 'student_id'):
            # Filter by student ownership
            db_query = db_query.filter(
                db_query.column_descriptions[0]['entity'].student_id == current_user.id
            )
    
    # Additional target role filtering
    if target_role and target_role != current_user.role:
        if hasattr(db_query.column_descriptions[0]['entity'], 'role'):
            db_query = db_query.filter(
                db_query.column_descriptions[0]['entity'].role == target_role
            )
    
    return db_query

def validate_data_access(user: User, resource_owner_id: int, allowed_roles: Optional[List[str]] = None) -> bool:
    """
    Validate if a user can access a specific resource
    
    Args:
        user: User requesting access
        resource_owner_id: ID of the user who owns the resource
        allowed_roles: Optional list of roles allowed to access the resource
        
    Returns:
        True if access is allowed, False otherwise
    """
    # Admins can access everything
    if user.role == 'admin':
        return True
    
    # Check role-based access
    if allowed_roles and user.role not in allowed_roles:
        return False
    
    # Ownership check
    if user.id == resource_owner_id:
        return True
    
    # Professor-specific access rules
    if user.role == 'professor':
        # Professors can access data from students in their cohorts
        # This would need to be implemented with cohort membership checks
        pass
    
    return False

def get_role_specific_data(user: User, data_type: str, db: Session) -> Query:
    """
    Get data specific to the user's role with proper isolation
    
    Args:
        user: Current user
        data_type: Type of data to retrieve ('scenarios', 'cohorts', 'progress', etc.)
        db: Database session
        
    Returns:
        Filtered query based on user role
    """
    if data_type == 'scenarios':
        query = db.query(Scenario)
        if user.role == 'professor':
            # Professors see their own scenarios and public scenarios
            query = query.filter(
                or_(
                    Scenario.created_by == user.id,
                    Scenario.is_public == True
                )
            )
        elif user.role == 'student':
            # Students see public scenarios and scenarios assigned to their cohorts
            query = query.filter(Scenario.is_public == True)
        return query
    
    elif data_type == 'cohorts':
        query = db.query(Cohort)
        if user.role == 'professor':
            # Professors see cohorts they created
            query = query.filter(Cohort.created_by == user.id)
        elif user.role == 'student':
            # Students see cohorts they're enrolled in
            cohort_ids = db.query(CohortStudent.cohort_id).filter(
                CohortStudent.student_id == user.id,
                CohortStudent.status == 'approved'
            ).subquery()
            query = query.filter(Cohort.id.in_(cohort_ids))
        return query
    
    elif data_type == 'progress':
        query = db.query(UserProgress)
        if user.role == 'student':
            # Students see their own progress
            query = query.filter(UserProgress.user_id == user.id)
        elif user.role == 'professor':
            # Professors see progress of students in their cohorts
            # This would need cohort membership checks
            pass
        return query
    
    else:
        # Default to empty query for unknown data types
        return db.query(User).filter(False)

def filter_cohort_access(user: User, cohort_id: int, db: Session) -> bool:
    """
    Check if user can access a specific cohort
    
    Args:
        user: Current user
        cohort_id: ID of the cohort to check
        db: Database session
        
    Returns:
        True if user can access the cohort, False otherwise
    """
    if user.role == 'admin':
        return True
    
    cohort = db.query(Cohort).filter(Cohort.id == cohort_id).first()
    if not cohort:
        return False
    
    if user.role == 'professor' and cohort.created_by == user.id:
        return True
    
    if user.role == 'student':
        enrollment = db.query(CohortStudent).filter(
            CohortStudent.cohort_id == cohort_id,
            CohortStudent.student_id == user.id,
            CohortStudent.status == 'approved'
        ).first()
        return enrollment is not None
    
    return False

def filter_scenario_access(user: User, scenario_id: int, db: Session) -> bool:
    """
    Check if user can access a specific scenario
    
    Args:
        user: Current user
        scenario_id: ID of the scenario to check
        db: Database session
        
    Returns:
        True if user can access the scenario, False otherwise
    """
    if user.role == 'admin':
        return True
    
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scenario:
        return False
    
    if user.role == 'professor' and scenario.created_by == user.id:
        return True
    
    if scenario.is_public:
        return True
    
    if user.role == 'student':
        # Check if scenario is assigned to user's cohorts
        cohort_ids = db.query(CohortStudent.cohort_id).filter(
            CohortStudent.student_id == user.id,
            CohortStudent.status == 'approved'
        ).subquery()
        
        from database.models import CohortSimulation
        assigned_scenario = db.query(CohortSimulation).filter(
            CohortSimulation.simulation_id == scenario_id,
            CohortSimulation.cohort_id.in_(cohort_ids)
        ).first()
        
        return assigned_scenario is not None
    
    return False

def get_accessible_users(user: User, db: Session) -> Query:
    """
    Get list of users that the current user can see/interact with
    
    Args:
        user: Current user
        db: Database session
        
    Returns:
        Query of accessible users
    """
    query = db.query(User)
    
    if user.role == 'admin':
        return query
    
    if user.role == 'professor':
        # Professors can see students in their cohorts
        cohort_ids = db.query(Cohort.id).filter(Cohort.created_by == user.id).subquery()
        student_ids = db.query(CohortStudent.student_id).filter(
            CohortStudent.cohort_id.in_(cohort_ids),
            CohortStudent.status == 'approved'
        ).subquery()
        
        query = query.filter(
            or_(
                User.id == user.id,  # Self
                User.id.in_(student_ids)  # Students in their cohorts
            )
        )
    
    elif user.role == 'student':
        # Students can see professors of their cohorts and other students in same cohorts
        cohort_ids = db.query(CohortStudent.cohort_id).filter(
            CohortStudent.student_id == user.id,
            CohortStudent.status == 'approved'
        ).subquery()
        
        professor_ids = db.query(Cohort.created_by).filter(Cohort.id.in_(cohort_ids)).subquery()
        student_ids = db.query(CohortStudent.student_id).filter(
            CohortStudent.cohort_id.in_(cohort_ids),
            CohortStudent.status == 'approved'
        ).subquery()
        
        query = query.filter(
            or_(
                User.id == user.id,  # Self
                User.id.in_(professor_ids),  # Professors of their cohorts
                User.id.in_(student_ids)  # Other students in same cohorts
            )
        )
    
    return query

def sanitize_user_data(user_data: dict, requesting_user: User) -> dict:
    """
    Sanitize user data based on the requesting user's role
    
    Args:
        user_data: User data to sanitize
        requesting_user: User requesting the data
        
    Returns:
        Sanitized user data
    """
    # Admins can see all data
    if requesting_user.role == 'admin':
        return user_data
    
    # Remove sensitive fields for non-admin users
    sensitive_fields = ['password_hash', 'google_id', 'provider']
    for field in sensitive_fields:
        user_data.pop(field, None)
    
    # Students can only see limited professor data
    if requesting_user.role == 'student':
        # Only show basic profile information
        allowed_fields = [
            'id', 'user_id', 'full_name', 'username', 'bio', 'avatar_url',
            'role', 'profile_public', 'created_at'
        ]
        return {k: v for k, v in user_data.items() if k in allowed_fields}
    
    # Professors can see more student data (for their cohorts)
    if requesting_user.role == 'professor':
        # Remove some sensitive fields but allow more than students
        restricted_fields = ['password_hash']
        for field in restricted_fields:
            user_data.pop(field, None)
    
    return user_data
