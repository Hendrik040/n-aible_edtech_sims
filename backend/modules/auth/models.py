"""SQLAlchemy models for authentication."""

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, func
from sqlalchemy.sql.sqltypes import TIMESTAMP

from common.db.base import Base


class User(Base):
    __tablename__ = "users"

    # Core fields
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(15), unique=True, nullable=True, index=True)  # STUD-XXXXX, INSTR-XXXXX, ADMIN-XXXXX
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=True)
    username = Column(String(255), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=True)  # Nullable for future OAuth
    
    # Profile fields
    bio = Column(Text, nullable=True)
    avatar_url = Column(String(500), nullable=True)
from sqlalchemy import Boolean, Column, DateTime, Enum, Float, Integer, String, Text, func
from sqlalchemy.sql.sqltypes import TIMESTAMP

# ... other code ...

    role = Column(Enum("student", "professor", "admin", name="user_role"), default="student", index=True, nullable=False)  # student, professor, admin
    
    # Account status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


__all__ = ["User"]

