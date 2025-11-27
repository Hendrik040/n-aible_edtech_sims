"""Data access helpers for authentication domain."""

from sqlalchemy.orm import Session

from modules.auth import models


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, user_id: int) -> models.User | None:
        """Get user by primary key ID."""
        return self.db.query(models.User).filter(models.User.id == user_id).first()

    def get_by_email(self, email: str) -> models.User | None:
        """Get user by email address."""
        return self.db.query(models.User).filter(models.User.email == email).first()

    def get_by_username(self, username: str) -> models.User | None:
        """Get user by username."""
        return self.db.query(models.User).filter(models.User.username == username).first()

    def create(
        self,
        user_id: str,
        email: str,
        password_hash: str,
        full_name: str | None = None,
        username: str | None = None,
        role: str = "student",
    ) -> models.User:
        """Create a new user with all fields."""
        user = models.User(
            user_id=user_id,
            email=email,
            password_hash=password_hash,
            full_name=full_name,
            username=username or email.split("@")[0],
            role=role,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user


__all__ = ["UserRepository"]
