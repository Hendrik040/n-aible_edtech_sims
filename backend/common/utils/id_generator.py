"""
ID generation utilities
"""
import secrets
from sqlalchemy.orm import Session
from common.db.models import User, Simulation, Cohort

_MAX_ID_RETRIES = 50


def _generate_unique_id(prefix: str, token_length: int, exists_fn) -> str:
    """Retry-safe ID generation — raises if collision probability is pathological."""
    for _ in range(_MAX_ID_RETRIES):
        random_part = secrets.token_urlsafe(token_length).upper()[:token_length]
        candidate = f"{prefix}-{random_part}"
        if not exists_fn(candidate):
            return candidate
    raise RuntimeError(
        f"Failed to generate unique ID for prefix '{prefix}' after {_MAX_ID_RETRIES} attempts"
    )


def generate_unique_user_id(db: Session, role: str) -> str:
    """
    Generate a unique user ID based on role.
    Format: ROLE-TOKEN (e.g. STU-A1B2C3D4)
    """
    prefix = role[:3].upper() if role else "USR"
    return _generate_unique_id(
        prefix, 8,
        lambda cid: db.query(User).filter(User.user_id == cid).first()
    )


def generate_simulation_id(db: Session) -> str:
    """
    Generate a unique simulation ID.
    Format: SC-TOKEN (e.g. SC-ABC123XY)
    """
    return _generate_unique_id(
        "SC", 8,
        lambda cid: db.query(Simulation).filter(Simulation.unique_id == cid).first()
    )


def generate_cohort_id(db: Session) -> str:
    """
    Generate a unique cohort ID.
    Format: COH-TOKEN (e.g. COH-XY1234)
    """
    return _generate_unique_id(
        "COH", 6,
        lambda cid: db.query(Cohort).filter(Cohort.unique_id == cid).first()
    )
