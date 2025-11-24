"""
Role-based authentication middleware for the AI Agent Education Platform
"""
from fastapi import HTTPException, status, Depends
from sqlalchemy.orm import Session
from database.connection import get_db
from database.models import User
from common.utilities.auth import get_current_user

def require_role(required_role: str):
    """
    Create a dependency that requires a specific role
    
    Args:
        required_role: The required role ('student', 'professor', 'admin')
        
    Returns:
        Dependency function that validates the user's role
    """
    def role_dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {required_role}, current role: {current_user.role}"
            )
        return current_user
    
    return role_dependency

def require_professor(current_user: User = Depends(get_current_user)) -> User:
    """Require professor role for access"""
    if current_user.role not in ['professor', 'admin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Professor or admin role required."
        )
    return current_user

def require_student(current_user: User = Depends(get_current_user)) -> User:
    """Require student role for access"""
    if current_user.role not in ['student', 'admin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Student or admin role required."
        )
    return current_user

def require_admin_or_professor(current_user: User = Depends(get_current_user)) -> User:
    """Require admin or professor role for access"""
    if current_user.role not in ['admin', 'professor']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin or professor role required."
        )
    return current_user

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require admin role for access"""
    if current_user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin role required."
        )
    return current_user

def get_user_role(current_user: User = Depends(get_current_user)) -> str:
    """Get the current user's role"""
    return current_user.role

def is_professor(current_user: User = Depends(get_current_user)) -> bool:
    """Check if current user is a professor or admin"""
    return current_user.role in ['professor', 'admin']

def is_student(current_user: User = Depends(get_current_user)) -> bool:
    """Check if current user is a student or admin"""
    return current_user.role in ['student', 'admin']

def is_admin(current_user: User = Depends(get_current_user)) -> bool:
    """Check if current user is an admin"""
    return current_user.role == 'admin'

def can_access_cohort(cohort_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> bool:
    """
    Check if user can access a specific cohort
    
    Args:
        cohort_id: ID of the cohort to check access for
        current_user: Current authenticated user
        db: Database session
        
    Returns:
        True if user can access the cohort, False otherwise
    """
    from database.models import Cohort
    
    # Admins can access all cohorts
    if current_user.role == 'admin':
        return True
    
    # Get the cohort
    cohort = db.query(Cohort).filter(Cohort.id == cohort_id).first()
    if not cohort:
        return False
    
    # Professors can access cohorts they created
    if current_user.role == 'professor' and cohort.created_by == current_user.id:
        return True
    
    # Students can access cohorts they're enrolled in
    if current_user.role == 'student':
        from database.models import CohortStudent
        enrollment = db.query(CohortStudent).filter(
            CohortStudent.cohort_id == cohort_id,
            CohortStudent.student_id == current_user.id,
            CohortStudent.status == 'approved'
        ).first()
        return enrollment is not None
    
    return False

def require_cohort_access(cohort_id: int):
    """
    Create a dependency that requires access to a specific cohort
    
    Args:
        cohort_id: ID of the cohort to check access for
        
    Returns:
        Dependency function that validates cohort access
    """
    def cohort_access_dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ) -> User:
        if not can_access_cohort(cohort_id, current_user, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You don't have permission to access this cohort."
            )
        return current_user
    
    return cohort_access_dependency

def require_ownership_or_admin(resource_owner_id: int):
    """
    Create a dependency that requires ownership of a resource or admin role
    
    Args:
        resource_owner_id: ID of the user who owns the resource
        
    Returns:
        Dependency function that validates ownership or admin access
    """
    def ownership_dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != 'admin' and current_user.id != resource_owner_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You don't have permission to access this resource."
            )
        return current_user
    
    return ownership_dependency
