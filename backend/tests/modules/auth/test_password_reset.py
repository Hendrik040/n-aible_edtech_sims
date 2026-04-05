"""Tests for the email-verified password reset flow.

Covers the two-step flow:
  POST /api/auth/users/request-reset   → issues a token + sends email
  POST /api/auth/users/reset-password  → validates token and updates password

These tests monkey-patch ``send_password_reset_email`` so no real SMTP call
is made and the generated token can be captured from the database.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from common.db.models import PasswordResetToken, User
from modules.auth.router import PASSWORD_RESET_GENERIC_MESSAGE


GENERIC = PASSWORD_RESET_GENERIC_MESSAGE


async def _register_user(async_client: AsyncClient, *, email: str, password: str = "Password123!") -> None:
    uid = str(uuid.uuid4())[:8]
    resp = await async_client.post(
        "/api/auth/users/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Reset Test",
            "username": f"reset_{uid}",
            "role": "student",
        },
    )
    assert resp.status_code == 200, resp.text


def _latest_token_for(db_session: Session, email: str) -> PasswordResetToken:
    user = db_session.query(User).filter(User.email == email).first()
    assert user is not None, f"user {email!r} should exist"
    token = (
        db_session.query(PasswordResetToken)
        .filter(PasswordResetToken.user_id == user.id)
        .order_by(PasswordResetToken.id.desc())
        .first()
    )
    assert token is not None, "expected a password reset token to have been created"
    return token


@pytest.fixture
def stub_send_email(monkeypatch):
    """Prevent real SMTP calls and capture invocations."""
    calls: list[tuple[str, str]] = []

    async def _fake(email: str, reset_link: str) -> bool:
        calls.append((email, reset_link))
        return True

    # Patch the symbol imported into the router module (that's what the
    # endpoint calls).
    import modules.auth.router as auth_router_module

    monkeypatch.setattr(auth_router_module, "send_password_reset_email", _fake)
    return calls


# --------------------------------------------------------------------------
# /request-reset
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_reset_returns_generic_message_for_unknown_email(
    async_client: AsyncClient, stub_send_email, db_session: Session
):
    resp = await async_client.post(
        "/api/auth/users/request-reset",
        json={"email": "nobody-" + uuid.uuid4().hex[:6] + "@example.com"},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == GENERIC
    # No email dispatched, no token created.
    assert stub_send_email == []
    assert db_session.query(PasswordResetToken).count() == 0


@pytest.mark.asyncio
async def test_request_reset_happy_path_creates_token_and_sends_email(
    async_client: AsyncClient, stub_send_email, db_session: Session
):
    email = f"happy_{uuid.uuid4().hex[:8]}@example.com"
    await _register_user(async_client, email=email)

    resp = await async_client.post(
        "/api/auth/users/request-reset", json={"email": email}
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == GENERIC

    # A token was created with a future expiry and no used_at.
    token = _latest_token_for(db_session, email)
    assert token.used_at is None
    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    assert expires_at > datetime.now(timezone.utc)

    # Exactly one email dispatched with a reset link that contains the token.
    assert len(stub_send_email) == 1
    sent_email, reset_link = stub_send_email[0]
    assert sent_email == email
    assert token.token in reset_link
    assert "/reset-password?token=" in reset_link


@pytest.mark.asyncio
async def test_request_reset_is_case_insensitive_on_email(
    async_client: AsyncClient, stub_send_email, db_session: Session
):
    email = f"caseins_{uuid.uuid4().hex[:8]}@example.com"
    await _register_user(async_client, email=email)

    resp = await async_client.post(
        "/api/auth/users/request-reset", json={"email": email.upper()}
    )
    assert resp.status_code == 200
    assert len(stub_send_email) == 1


@pytest.mark.asyncio
async def test_request_reset_invalidates_previous_unused_tokens(
    async_client: AsyncClient, stub_send_email, db_session: Session
):
    email = f"invalidate_{uuid.uuid4().hex[:8]}@example.com"
    await _register_user(async_client, email=email)

    await async_client.post("/api/auth/users/request-reset", json={"email": email})
    first_token = _latest_token_for(db_session, email).token

    await async_client.post("/api/auth/users/request-reset", json={"email": email})

    # Only the newest token should remain for this user.
    user = db_session.query(User).filter(User.email == email).first()
    remaining = (
        db_session.query(PasswordResetToken)
        .filter(PasswordResetToken.user_id == user.id)
        .all()
    )
    assert len(remaining) == 1
    assert remaining[0].token != first_token


# --------------------------------------------------------------------------
# /reset-password
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_password_happy_path_updates_password_and_marks_token_used(
    async_client: AsyncClient, stub_send_email, db_session: Session
):
    email = f"reset_{uuid.uuid4().hex[:8]}@example.com"
    old_password = "OldPassword123!"
    new_password = "NewPassword456!"
    await _register_user(async_client, email=email, password=old_password)

    await async_client.post("/api/auth/users/request-reset", json={"email": email})
    token = _latest_token_for(db_session, email).token

    resp = await async_client.post(
        "/api/auth/users/reset-password",
        json={"token": token, "new_password": new_password},
    )
    assert resp.status_code == 200, resp.text

    # Old password no longer works.
    bad = await async_client.post(
        "/api/auth/users/login", json={"email": email, "password": old_password}
    )
    assert bad.status_code == 401

    # New password works.
    ok = await async_client.post(
        "/api/auth/users/login", json={"email": email, "password": new_password}
    )
    assert ok.status_code == 200

    # Token is now marked used.
    db_session.expire_all()
    used_token = (
        db_session.query(PasswordResetToken)
        .filter(PasswordResetToken.token == token)
        .first()
    )
    assert used_token is not None
    assert used_token.used_at is not None


@pytest.mark.asyncio
async def test_reset_password_rejects_unknown_token(async_client: AsyncClient):
    resp = await async_client.post(
        "/api/auth/users/reset-password",
        json={"token": "this-token-does-not-exist", "new_password": "whatever123"},
    )
    assert resp.status_code == 400
    assert "invalid" in resp.json()["detail"].lower() or "expired" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reset_password_rejects_reused_token(
    async_client: AsyncClient, stub_send_email, db_session: Session
):
    email = f"reuse_{uuid.uuid4().hex[:8]}@example.com"
    await _register_user(async_client, email=email)
    await async_client.post("/api/auth/users/request-reset", json={"email": email})
    token = _latest_token_for(db_session, email).token

    first = await async_client.post(
        "/api/auth/users/reset-password",
        json={"token": token, "new_password": "FirstReset123!"},
    )
    assert first.status_code == 200

    second = await async_client.post(
        "/api/auth/users/reset-password",
        json={"token": token, "new_password": "SecondReset123!"},
    )
    assert second.status_code == 400
    assert "already" in second.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reset_password_rejects_expired_token(
    async_client: AsyncClient, stub_send_email, db_session: Session
):
    email = f"expired_{uuid.uuid4().hex[:8]}@example.com"
    await _register_user(async_client, email=email)
    await async_client.post("/api/auth/users/request-reset", json={"email": email})

    token_row = _latest_token_for(db_session, email)
    # Force the token into the past.
    token_row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db_session.add(token_row)
    db_session.commit()
    token_value = token_row.token

    resp = await async_client.post(
        "/api/auth/users/reset-password",
        json={"token": token_value, "new_password": "LatePassword123!"},
    )
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reset_password_rejects_short_password(
    async_client: AsyncClient, stub_send_email, db_session: Session
):
    email = f"short_{uuid.uuid4().hex[:8]}@example.com"
    await _register_user(async_client, email=email)
    await async_client.post("/api/auth/users/request-reset", json={"email": email})
    token = _latest_token_for(db_session, email).token

    resp = await async_client.post(
        "/api/auth/users/reset-password",
        json={"token": token, "new_password": "abc"},
    )
    # FastAPI returns 422 for pydantic validation errors.
    assert resp.status_code == 422


# --------------------------------------------------------------------------
# Regression: old insecure endpoint must be gone.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_old_forgot_password_endpoint_is_removed(async_client: AsyncClient):
    resp = await async_client.post(
        "/api/auth/users/forgot-password",
        json={
            "email": "whoever@example.com",
            "confirm_email": "whoever@example.com",
            "new_password": "hackhack123",
        },
    )
    # The old direct-reset endpoint must no longer exist.
    assert resp.status_code in (404, 405)
