"""
Notification model for in-app notifications.
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String, Text, ForeignKey, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from common.db.base import Base

if TYPE_CHECKING:
    from common.db.models.auth.user import User


class Notification(Base):
    """In-app notifications for users."""
    __tablename__ = "notifications"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="notifications")
    
    __table_args__ = (
        Index("idx_notifications_user_read", "user_id", "is_read"),
        Index("idx_notifications_user_created", "user_id", "created_at"),
    )

