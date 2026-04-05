"""
Tests for user profile endpoints: PUT /users/me and POST /users/change-password
"""
import pytest
import uuid
from httpx import AsyncClient


async def _register_and_login(async_client: AsyncClient, role: str = "student") -> dict:
    """Helper: register a fresh user, login, and return (cookies, user_data)."""
    uid = str(uuid.uuid4())[:8]
    user_data = {
        "email": f"profile_{uid}@example.com",
        "password": "Password123!",
        "full_name": f"Profile User {uid}",
        "username": f"profile_{uid}",
        "role": role,
    }
    reg = await async_client.post("/api/auth/users/register", json=user_data)
    assert reg.status_code == 200

    login = await async_client.post(
        "/api/auth/users/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    assert login.status_code == 200
    return {"cookies": login.cookies, "user": user_data}


# ---- PUT /users/me ----


@pytest.mark.asyncio
async def test_update_profile_full_name(async_client: AsyncClient):
    """Updating full_name should persist and be returned."""
    ctx = await _register_and_login(async_client)
    resp = await async_client.put(
        "/users/me",
        json={"full_name": "New Name"},
        cookies=ctx["cookies"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["full_name"] == "New Name"


@pytest.mark.asyncio
async def test_update_profile_multiple_fields(async_client: AsyncClient):
    """Updating several profile fields at once should work."""
    ctx = await _register_and_login(async_client)
    payload = {
        "full_name": "Updated Name",
        "bio": "Hello world",
        "profile_public": False,
        "allow_contact": False,
    }
    resp = await async_client.put("/users/me", json=payload, cookies=ctx["cookies"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["full_name"] == "Updated Name"
    assert body["bio"] == "Hello world"
    assert body["profile_public"] is False
    assert body["allow_contact"] is False


@pytest.mark.asyncio
async def test_update_profile_username_uniqueness(async_client: AsyncClient):
    """Changing username to one already taken should return 409."""
    ctx1 = await _register_and_login(async_client, role="student")
    ctx2 = await _register_and_login(async_client, role="professor")

    # Try to set user2's username to user1's username
    resp = await async_client.put(
        "/users/me",
        json={"username": ctx1["user"]["username"]},
        cookies=ctx2["cookies"],
    )
    assert resp.status_code == 409
    assert "taken" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_profile_unauthenticated(async_client: AsyncClient):
    """PUT /users/me without auth should return 401."""
    resp = await async_client.put("/users/me", json={"full_name": "Hacker"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_profile_strips_whitespace(async_client: AsyncClient):
    """String fields should be trimmed of leading/trailing whitespace."""
    ctx = await _register_and_login(async_client)
    resp = await async_client.put(
        "/users/me",
        json={"full_name": "  Padded Name  ", "bio": "  bio text  "},
        cookies=ctx["cookies"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["full_name"] == "Padded Name"
    assert body["bio"] == "bio text"


# ---- POST /users/change-password ----


@pytest.mark.asyncio
async def test_change_password_success(async_client: AsyncClient):
    """Changing password with correct current password should succeed."""
    ctx = await _register_and_login(async_client)
    resp = await async_client.post(
        "/users/change-password",
        json={
            "current_password": ctx["user"]["password"],
            "new_password": "NewPassword456!",
        },
        cookies=ctx["cookies"],
    )
    assert resp.status_code == 200
    assert "success" in resp.json()["message"].lower()

    # Verify new password works for login
    login = await async_client.post(
        "/api/auth/users/login",
        json={"email": ctx["user"]["email"], "password": "NewPassword456!"},
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_change_password_wrong_current(async_client: AsyncClient):
    """Providing an incorrect current password should return 401."""
    ctx = await _register_and_login(async_client)
    resp = await async_client.post(
        "/users/change-password",
        json={
            "current_password": "WrongPassword!",
            "new_password": "NewPassword456!",
        },
        cookies=ctx["cookies"],
    )
    assert resp.status_code == 401
    assert "incorrect" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_change_password_too_short(async_client: AsyncClient):
    """New password shorter than 6 chars should return 400."""
    ctx = await _register_and_login(async_client)
    resp = await async_client.post(
        "/users/change-password",
        json={
            "current_password": ctx["user"]["password"],
            "new_password": "short",
        },
        cookies=ctx["cookies"],
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_change_password_unauthenticated(async_client: AsyncClient):
    """POST /users/change-password without auth should return 401."""
    resp = await async_client.post(
        "/users/change-password",
        json={"current_password": "x", "new_password": "y12345"},
    )
    assert resp.status_code == 401
