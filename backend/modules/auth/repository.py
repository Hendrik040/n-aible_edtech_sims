"""Data access helpers for authentication domain."""

from sqlalchemy.orm import Session

from modules.auth import models


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_email(self, email: str) -> models.User | None:
        return self.db.query(models.User).filter(models.User.email == email).first()

    def create(self, email: str, password_hash: str, full_name: str | None = None) -> models.User:
        user = models.User(email=email, password_hash=password_hash, full_name=full_name)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user


__all__ = ["UserRepository"]
