"""User ID generation utilities for role-based system."""

import secrets
import string
from sqlalchemy.orm import Session

from modules.auth import models


def generate_user_id(role: str) -> str:
    """
    Generate a role-based user ID.
    
    Args:
        role: User role ('student', 'professor', or 'admin')
        
    Returns:
        Formatted user ID (STUD-XXXXX, INSTR-XXXXX, or ADMIN-XXXXX)
        
    Raises:
        ValueError: If role is not 'student', 'professor', or 'admin'
    """
    if role not in ['student', 'professor', 'admin']:
        raise ValueError(f"Invalid role: {role}. Must be 'student', 'professor', or 'admin'")
    
    # Generate 9 alphanumeric characters
    random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(9))
    
    if role == 'student':
        return f"STUD-{random_part}"
    elif role == 'professor':
        return f"INSTR-{random_part}"
    else:  # admin
        return f"ADMIN-{random_part}"


def generate_unique_user_id(db: Session, role: str) -> str:
    """
    Generate a unique user ID that doesn't exist in the database.
    
    Args:
        db: Database session
        role: User role ('student', 'professor', or 'admin')
        
    Returns:
        Unique formatted user ID
        
    Raises:
        RuntimeError: If unable to generate unique ID after max attempts
    """
    max_attempts = 100
    attempts = 0
    
    while attempts < max_attempts:
        user_id = generate_user_id(role)
        
        # Check if ID already exists
        existing_user = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not existing_user:
            return user_id
        
        attempts += 1
    
    raise RuntimeError(f"Failed to generate unique user ID for role '{role}' after {max_attempts} attempts")


def extract_role_from_user_id(user_id: str) -> str | None:
    """
    Extract role from user ID.
    
    Args:
        user_id: User ID to extract role from
        
    Returns:
        Role ('student', 'professor', or 'admin') or None if invalid format
    """
    if not user_id or not isinstance(user_id, str):
        return None
    
    if user_id.startswith('STUD-') and len(user_id) == 14:
        return 'student'
    elif user_id.startswith('INSTR-') and len(user_id) == 15:
        return 'professor'
    elif user_id.startswith('ADMIN-') and len(user_id) == 15:
        return 'admin'
    
    return None


def is_valid_user_id_format(user_id: str) -> bool:
    """
    Check if user ID follows the correct format.
    
    Args:
        user_id: User ID to validate
        
    Returns:
        True if valid format, False otherwise
    """
    return extract_role_from_user_id(user_id) is not None


__all__ = [
    "generate_user_id",
    "generate_unique_user_id",
    "extract_role_from_user_id",
    "is_valid_user_id_format",
]
