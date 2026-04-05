"""
Tests for email case normalization across auth endpoints.
Covers: schema validators, login, registration, check-email, and OAuth lookups.
"""
import pytest
import uuid
from httpx import AsyncClient


# --- Schema-level normalization tests ---

def test_user_login_schema_normalizes_email():
    """UserLogin schema should strip and lowercase the email."""
    from modules.auth.schemas import UserLogin
    login = UserLogin(email="  Alice@Example.COM  ", password="secret")
    assert login.email == "alice@example.com"


def test_user_register_schema_normalizes_email():
    """UserRegister schema should strip and lowercase the email."""
    from modules.auth.schemas import UserRegister
    reg = UserRegister(
        email="  Bob@Example.COM  ",
        full_name="Bob",
        username="bob",
        password="secret123",
        role="student",
    )
    assert reg.email == "bob@example.com"


# --- Login endpoint case-insensitivity ---

@pytest.mark.asyncio
async def test_login_case_insensitive(async_client: AsyncClient):
    """User should be able to login with different email casing."""
    uid = str(uuid.uuid4())[:8]
    email = f"casetest_{uid}@example.com"

    # Register with lowercase email
    reg = await async_client.post(
        "/api/auth/users/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Case Test",
            "username": f"casetest_{uid}",
            "role": "student",
        },
    )
    assert reg.status_code == 200

    # Login with uppercase variant
    login = await async_client.post(
        "/api/auth/users/login",
        json={"email": email.upper(), "password": "Password123!"},
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_login_mixed_case(async_client: AsyncClient):
    """Login with mixed-case email should succeed."""
    uid = str(uuid.uuid4())[:8]
    email = f"mixedcase_{uid}@example.com"

    await async_client.post(
        "/api/auth/users/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Mixed Case",
            "username": f"mixedcase_{uid}",
            "role": "student",
        },
    )

    # Login with MiXeD case
    mixed = f"MiXeDcAsE_{uid}@ExAmPlE.cOm"
    login = await async_client.post(
        "/api/auth/users/login",
        json={"email": mixed, "password": "Password123!"},
    )
    assert login.status_code == 200


# --- Registration duplicate prevention ---

@pytest.mark.asyncio
async def test_register_duplicate_case_insensitive(async_client: AsyncClient):
    """Registering with a case-variant of an existing email should fail."""
    uid = str(uuid.uuid4())[:8]
    email = f"dupetest_{uid}@example.com"

    reg1 = await async_client.post(
        "/api/auth/users/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Dupe Test",
            "username": f"dupetest_{uid}",
            "role": "student",
        },
    )
    assert reg1.status_code == 200

    # Try registering with uppercase variant
    reg2 = await async_client.post(
        "/api/auth/users/register",
        json={
            "email": email.upper(),
            "password": "Password123!",
            "full_name": "Dupe Test 2",
            "username": f"dupetest2_{uid}",
            "role": "student",
        },
    )
    assert reg2.status_code == 400
    assert "email already registered" in reg2.json()["detail"].lower()


# --- Check-email endpoint ---

@pytest.mark.asyncio
async def test_check_email_case_insensitive(async_client: AsyncClient):
    """check-email should find existing users regardless of casing."""
    uid = str(uuid.uuid4())[:8]
    email = f"checktest_{uid}@example.com"

    await async_client.post(
        "/api/auth/users/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Check Test",
            "username": f"checktest_{uid}",
            "role": "student",
        },
    )

    # Check with uppercase
    resp = await async_client.post(
        "/api/auth/users/check-email",
        json={"email": email.upper()},
    )
    assert resp.status_code == 200
    assert resp.json()["exists"] is True


@pytest.mark.asyncio
async def test_check_email_with_whitespace(async_client: AsyncClient):
    """check-email should trim whitespace before checking."""
    uid = str(uuid.uuid4())[:8]
    email = f"wstest_{uid}@example.com"

    await async_client.post(
        "/api/auth/users/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "WS Test",
            "username": f"wstest_{uid}",
            "role": "student",
        },
    )

    resp = await async_client.post(
        "/api/auth/users/check-email",
        json={"email": f"  {email}  "},
    )
    assert resp.status_code == 200
    assert resp.json()["exists"] is True


# --- Forgot password case-insensitivity (already implemented, regression test) ---

@pytest.mark.asyncio
async def test_forgot_password_case_insensitive(async_client: AsyncClient):
    """Forgot-password should work with case-variant email."""
    uid = str(uuid.uuid4())[:8]
    email = f"forgottest_{uid}@example.com"

    await async_client.post(
        "/api/auth/users/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Forgot Test",
            "username": f"forgottest_{uid}",
            "role": "student",
        },
    )

    resp = await async_client.post(
        "/api/auth/users/forgot-password",
        json={
            "email": email.upper(),
            "confirm_email": email.upper(),
            "new_password": "NewPassword456!",
        },
    )
    assert resp.status_code == 200
