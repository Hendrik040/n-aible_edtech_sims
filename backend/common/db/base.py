"""
Declarative SQLAlchemy base shared across all domain models.
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()

__all__ = ["Base"]

