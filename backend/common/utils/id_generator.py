"""
ID generation utilities
"""
import uuid
from sqlalchemy.orm import Session
from common.db.models import User

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
