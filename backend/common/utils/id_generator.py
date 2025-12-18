"""
ID generation utilities
"""
import uuid
import secrets
from sqlalchemy.orm import Session
from common.db.models import User, Simulation

def generate_unique_user_id(db: Session, role: str) -> str:
    """
    Generate a unique user ID based on role.
    Format: ROLE-UUID-8chars (e.g. STU-12345678)
    """
    prefix = role[:3].upper() if role else "USR"
    while True:
        # Generate a candidate ID
        random_part = str(uuid.uuid4())[:8].upper()
        new_id = f"{prefix}-{random_part}"
        
        # Check for collision
        # We use the 'user_id' field (String) not 'id' (Integer)
        existing = db.query(User).filter(User.user_id == new_id).first()
        
        if not existing:
            return new_id


def generate_simulation_id(db: Session) -> str:
    """
    Generate a unique simulation ID.
    Format: SC-TOKEN (e.g. SC-ABC123XY)
    """
    while True:
        # Generate a candidate ID (matching format used in pdf_processing)
        random_part = secrets.token_urlsafe(8).upper()
        unique_id = f"SC-{random_part}"
        
        # Check for collision
        existing = db.query(Simulation).filter(Simulation.unique_id == unique_id).first()
        
        if not existing:
            return unique_id
