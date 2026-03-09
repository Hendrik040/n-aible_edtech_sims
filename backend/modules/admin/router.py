"""Admin module router — Super admin impersonation functionality."""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user
from common.db.core import get_db
from common.db.models import User
from common.security.tokens import create_access_token, decode_token
from modules.auth.service import auth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def require_super_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require super_admin role for access."""
    if current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )
    return current_user


@router.get("/professors")
async def list_professors(
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Return all professor accounts (super_admin only)."""
    professors = (
        db.query(User)
        .filter(User.role == "professor")
        .order_by(User.full_name)
        .all()
    )
    return [
        {
            "id": p.id,
            "full_name": p.full_name,
            "email": p.email,
            "username": p.username,
            "avatar_url": p.avatar_url,
        }
        for p in professors
    ]


@router.post("/impersonate/{user_id}")
async def impersonate_professor(
    user_id: int,
    response: Response,
    current_user: User = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """
    Begin impersonating a professor account.

    Sets a short-lived professor cookie and returns a restore token the
    frontend can store in sessionStorage.  The restore token is a signed JWT
    that the /restore endpoint can later verify to re-issue the admin cookie.
    """
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.role not in ("professor", "admin"):
        raise HTTPException(
            status_code=400, detail="Can only impersonate professor accounts"
        )

    # Signed restore token — contains the admin's user ID, valid 2 hours
    restore_token = create_access_token(
        subject=str(current_user.id),
        expires_delta=timedelta(hours=2),
    )

    # Short-lived professor session cookie (1 hour)
    prof_token = create_access_token(
        subject=str(target.id),
        expires_delta=timedelta(hours=1),
    )
    auth_service.set_auth_cookie(response, prof_token)

    logger.info(
        "Super admin %s is now impersonating %s", current_user.email, target.email
    )
    return {
        "restore_token": restore_token,
        "impersonated_user": {
            "id": target.id,
            "full_name": target.full_name,
            "email": target.email,
        },
    }


@router.post("/restore")
async def restore_admin_session(
    body: dict,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Restore the super_admin session using a restore token.

    The frontend passes the restore token it stored in sessionStorage.
    This endpoint validates the token, confirms the referenced user is still
    a super_admin, and issues a fresh admin cookie.
    """
    restore_token = body.get("restore_token")
    if not restore_token:
        raise HTTPException(status_code=400, detail="Missing restore_token")

    try:
        payload = decode_token(restore_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired restore token")

    admin_id_str = payload.get("sub")
    if not admin_id_str:
        raise HTTPException(status_code=401, detail="Invalid restore token payload")

    admin_user = db.query(User).filter(User.id == int(admin_id_str)).first()
    if not admin_user or admin_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    admin_token = create_access_token(subject=str(admin_user.id))
    auth_service.set_auth_cookie(response, admin_token)

    logger.info("Super admin session restored for %s", admin_user.email)
    return {"success": True}
