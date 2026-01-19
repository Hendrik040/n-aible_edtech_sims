"""
Database Connection Configuration

Re-exports from common.db.core for backwards compatibility.
"""
from common.db.core import engine, SessionLocal, get_db

__all__ = ["engine", "SessionLocal", "get_db"]

