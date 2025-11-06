"""
User ID generation utilities for role-based system
"""
import secrets
import string
from typing import Literal
from sqlalchemy.orm import Session
from database.models import User
from database.models import StudentSimulationInstance

def generate_user_id(role: str) -> str:
    """
    Generate a role-based user ID
    
    Args:
        role: User role ('student' or 'professor')
        
    Returns:
        Formatted user ID (STUD-XXXXX or INSTR-XXXXX)
        
    Raises:
        ValueError: If role is not 'student' or 'professor'
    """
    if role not in ['student', 'professor']:
        raise ValueError(f"Invalid role: {role}. Must be 'student' or 'professor'")
    
    # Generate 9 alphanumeric characters
    random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(9))
    
    if role == 'student':
        return f"STUD-{random_part}"
    else:  # professor
        return f"INSTR-{random_part}"

def generate_unique_user_id(db: Session, role: str) -> str:
    """
    Generate a unique user ID that doesn't exist in the database
    
    Args:
        db: Database session
        role: User role ('student' or 'professor')
        
    Returns:
        Unique formatted user ID
        
    Raises:
        ValueError: If role is invalid
    """
    print(f"🔄 Generating unique user ID for role: {role}")
    max_attempts = 100  # Prevent infinite loops
    attempts = 0
    
    while attempts < max_attempts:
        user_id = generate_user_id(role)
        print(f"🎲 Generated ID attempt {attempts + 1}: {user_id}")
        
        # Check if ID already exists
        existing_user = db.query(User).filter(User.user_id == user_id).first()
        if not existing_user:
            print(f"✅ Unique ID found: {user_id}")
            return user_id
        
        print(f"⚠️ ID {user_id} already exists, trying again...")
        attempts += 1
    
    # If we couldn't generate a unique ID after max attempts, raise error
    print(f"❌ Failed to generate unique user ID for role '{role}' after {max_attempts} attempts")
    raise RuntimeError(f"Failed to generate unique user ID for role '{role}' after {max_attempts} attempts")

def validate_user_role(role: str) -> bool:
    """
    Validate that the role is a valid student or professor role
    
    Args:
        role: Role to validate
        
    Returns:
        True if valid, False otherwise
    """
    return role in ['student', 'professor']

def extract_role_from_user_id(user_id: str) -> str | None:
    """
    Extract role from user ID
    
    Args:
        user_id: User ID to extract role from
        
    Returns:
        Role ('student' or 'professor') or None if invalid format
    """
    if not user_id or not isinstance(user_id, str):
        return None
    
    if user_id.startswith('STUD-') and len(user_id) == 14:  # STUD- + 9 chars
        return 'student'
    elif user_id.startswith('INSTR-') and len(user_id) == 15:  # INSTR- + 9 chars
        return 'professor'
    
    return None

def is_valid_user_id_format(user_id: str) -> bool:
    """
    Check if user ID follows the correct format
    
    Args:
        user_id: User ID to validate
        
    Returns:
        True if valid format, False otherwise
    """
    return extract_role_from_user_id(user_id) is not None

def generate_invitation_token() -> str:
    """
    Generate a secure invitation token for cohort invitations
    
    Returns:
        URL-safe token string
    """
    return secrets.token_urlsafe(32)

def generate_email_verification_token() -> str:
    """
    Generate a secure email verification token
    
    Returns:
        URL-safe token string
    """
    return secrets.token_urlsafe(32)

def generate_simulation_instance_id() -> str:
    """
    Generate a unique ID for student simulation instances
    Format: SSI-XXXXXXXX (Student Simulation Instance)
    
    Returns:
        Unique instance ID string
    """
    return f"SSI-{secrets.token_urlsafe(8).upper()}"

def generate_unique_simulation_instance_id(db: Session) -> str:
    """
    Generate a unique simulation instance ID that doesn't exist in the database
    
    Args:
        db: Database session
        
    Returns:
        Unique instance ID
    """
    
    max_attempts = 100
    attempts = 0
    
    while attempts < max_attempts:
        instance_id = generate_simulation_instance_id()
        
        # Check if ID already exists
        existing = db.query(StudentSimulationInstance).filter(
            StudentSimulationInstance.unique_id == instance_id
        ).first()
        
        if not existing:
            return instance_id
        
        attempts += 1
    
    raise RuntimeError(f"Failed to generate unique simulation instance ID after {max_attempts} attempts")

def generate_invite_link_token() -> str:
    """
    Generate a secure token for cohort invite links (32 bytes hex)
    
    Returns:
        Hex token string (64 characters)
    """
    return secrets.token_hex(32)
