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
