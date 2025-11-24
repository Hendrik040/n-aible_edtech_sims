"""Password hashing helpers."""

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password."""

    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Check whether the password matches the stored hash."""

    return _pwd_context.verify(password, password_hash)


__all__ = ["hash_password", "verify_password"]
"""Password hashing helpers."""

import hashlib


def hash_password(raw_password: str) -> str:
    return hashlib.sha256(raw_password.encode("utf-8")).hexdigest()


def verify_password(raw_password: str, hashed_password: str) -> bool:
    return hash_password(raw_password) == hashed_password
