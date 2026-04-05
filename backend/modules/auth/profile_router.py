"""
User profile router - Update profile and change password endpoints.

These endpoints are called by the frontend ProfilePage component via the
generic API proxy, which forwards paths as-is. The frontend calls:
  PUT  /users/me
  POST /users/change-password

This router uses prefix="/users" and is registered directly on the app
(not through the /api/auth wiring used by the auth router).
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.dependencies import get_current_user
from common.db.core import get_db
from common.db.models import User
from common.db.schemas import UserResponse
from modules.auth.schemas import ProfileUpdate, PasswordChange
from modules.auth.service import auth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["User Profile"])


@router.put("/me", response_model=UserResponse)
async def update_profile(
    profile_data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the authenticated user's profile fields."""
    # Check username uniqueness if changed
    if profile_data.username is not None and profile_data.username != current_user.username:
        existing = (
            db.query(User)
            .filter(
                func.lower(User.username) == profile_data.username.strip().lower(),
                User.id != current_user.id,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username is already taken",
            )

    # Apply only the fields that were provided
    update_fields = profile_data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        if isinstance(value, str):
            value = value.strip()
            if field in ("full_name", "username") and not value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{field} cannot be empty",
                )
        setattr(current_user, field, value)

    current_user.updated_at = datetime.now(timezone.utc)
    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    return current_user


@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verify current password and update to a new password."""
    if not current_user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account uses Google sign-in. Password change is not available.",
        )

    if not await auth_service.verify_password_async(
        password_data.current_password, current_user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    if len(password_data.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters",
        )

    current_user.password_hash = await auth_service.get_password_hash_async(
        password_data.new_password
    )
    current_user.updated_at = datetime.now(timezone.utc)
    db.add(current_user)
    db.commit()

    return {"message": "Password updated successfully"}
