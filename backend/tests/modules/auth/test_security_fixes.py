"""Regression tests for the security audit fixes (2026-06-15).

These cover the auth/account-takeover findings and the config guard. They are
written to pass whether or not Redis is available: without Redis the rate
limiter and reset-token store fail safely (limiter fails open; reset tokens
cannot be created, so the reset flow simply cannot change a password).
"""
import uuid

import pytest
from httpx import AsyncClient

from common.config import Settings


def _new_user(role: str = "student") -> dict:
    uid = str(uuid.uuid4())[:8]
    return {
        "email": f"sec_{uid}@example.com",
        "password": "OriginalPass123!",
        "full_name": "Sec Test",
        "username": f"sec_{uid}",
        "role": role,
    }


# --- #517: SECRET_KEY production guard --------------------------------------

def test_production_rejects_default_secret():
    with pytest.raises(Exception):
        Settings(environment="production", secret_key="super-secret-key")


def test_production_rejects_empty_secret():
    with pytest.raises(Exception):
        Settings(environment="production", secret_key="")


def test_production_accepts_strong_secret():
    s = Settings(environment="production", secret_key="a-strong-unique-random-value")
    assert s.secret_key == "a-strong-unique-random-value"


def test_development_allows_default_secret():
    # Local/dev must remain frictionless.
    s = Settings(environment="development", secret_key="super-secret-key")
    assert s.secret_key == "super-secret-key"


# --- #516: password reset can no longer take over accounts ------------------

@pytest.mark.asyncio
async def test_forgot_password_does_not_change_password(async_client: AsyncClient):
    user = _new_user()
    assert (await async_client.post("/api/auth/users/register", json=user)).status_code == 200

    # Request a reset. Response must be generic and must NOT report a change.
    resp = await async_client.post(
        "/api/auth/users/forgot-password", json={"email": user["email"]}
    )
    assert resp.status_code == 200
    assert "updated" not in resp.json()["message"].lower()

    # The original password must still work (nothing was changed).
    login = await async_client.post(
        "/api/auth/users/login",
        json={"email": user["email"], "password": user["password"]},
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_forgot_password_ignores_injected_new_password(async_client: AsyncClient):
    """Sending the OLD tokenless payload must not set the attacker's password."""
    user = _new_user()
    assert (await async_client.post("/api/auth/users/register", json=user)).status_code == 200

    attacker_pw = "AttackerOwned123!"
    await async_client.post(
        "/api/auth/users/forgot-password",
        json={"email": user["email"], "confirm_email": user["email"], "new_password": attacker_pw},
    )

    # Attacker's chosen password must be rejected at login.
    bad = await async_client.post(
        "/api/auth/users/login",
        json={"email": user["email"], "password": attacker_pw},
    )
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_reset_password_rejects_invalid_token(async_client: AsyncClient):
    resp = await async_client.post(
        "/api/auth/users/reset-password",
        json={"token": "definitely-not-a-real-token", "new_password": "BrandNewPass123"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_reset_password_enforces_min_length(async_client: AsyncClient):
    resp = await async_client.post(
        "/api/auth/users/reset-password",
        json={"token": "whatever", "new_password": "short"},
    )
    assert resp.status_code == 422  # schema validation rejects < 8 chars
