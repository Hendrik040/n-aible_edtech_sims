"""
ID generation utilities
"""
import uuid
import secrets
from sqlalchemy.orm import Session
from common.db.models import User, Simulation, CohortInvitation, CohortInvite

_MAX_RETRIES = 100


def generate_unique_user_id(db: Session, role: str) -> str:
    """
    Generate a unique user ID based on role.
    Format: ROLE-UUID-8chars (e.g. STU-12345678)
    """
    prefix = role[:3].upper() if role else "USR"
    for _ in range(_MAX_RETRIES):
        random_part = str(uuid.uuid4())[:8].upper()
        new_id = f"{prefix}-{random_part}"
        if not db.query(User).filter(User.user_id == new_id).first():
            return new_id
    raise ValueError(f"Could not generate unique user ID after {_MAX_RETRIES} attempts")


def generate_simulation_id(db: Session) -> str:
    """
    Generate a unique simulation ID.
    Format: SC-TOKEN (e.g. SC-ABC123XY)
    """
    for _ in range(_MAX_RETRIES):
        random_part = secrets.token_urlsafe(8).upper()
        unique_id = f"SC-{random_part}"
        if not db.query(Simulation).filter(Simulation.unique_id == unique_id).first():
            return unique_id
    raise ValueError(f"Could not generate unique simulation ID after {_MAX_RETRIES} attempts")


def generate_invite_token(db: Session) -> str:
    """
    Generate a unique single-use invite token for CohortInvitation.
    Format: INV-TOKEN (e.g. INV-Xk3mP9aQ)
    """
    for _ in range(_MAX_RETRIES):
        token = f"INV-{secrets.token_urlsafe(12)}"
        if not db.query(CohortInvitation).filter(CohortInvitation.invitation_token == token).first():
            return token
    raise ValueError(f"Could not generate unique invite token after {_MAX_RETRIES} attempts")


def generate_invite_link_token(db: Session) -> str:
    """
    Generate a unique reusable invite link token for CohortInvite.
    Format: LNK-TOKEN (e.g. LNK-aB3xYz8k)
    """
    for _ in range(_MAX_RETRIES):
        token = f"LNK-{secrets.token_urlsafe(12)}"
        if not db.query(CohortInvite).filter(CohortInvite.token == token).first():
            return token
    raise ValueError(f"Could not generate unique invite link token after {_MAX_RETRIES} attempts")
