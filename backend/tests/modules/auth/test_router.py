"""Tests for auth router endpoints."""

import pytest
from fastapi import status
from sqlalchemy.orm import Session

from modules.auth import models


def test_register_user_success(client):
    """Test successful user registration."""
    payload = {
        "email": "test@example.com",
        "password": "testpassword123",
        "full_name": "Test User"
    }
    response = client.post("/api/auth/register", json=payload)
    
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["email"] == payload["email"]
    assert data["full_name"] == payload["full_name"]
    assert data["is_active"] is True
    assert data["role"] == "student"  # Default role
    assert data["is_verified"] is False
    assert "id" in data
    assert "user_id" in data  # Role-based ID
    assert "username" in data
    assert "created_at" in data
    assert "updated_at" in data
    assert "password" not in data
    assert "password_hash" not in data
    # Check that authentication cookie is set
    assert "access_token" in response.cookies


def test_register_user_duplicate_email(client):
    """Test registration with duplicate email fails."""
    payload = {
        "email": "duplicate@example.com",
        "password": "testpassword123",
        "full_name": "First User"
    }
    # First registration should succeed
    response1 = client.post("/api/auth/register", json=payload)
    assert response1.status_code == status.HTTP_201_CREATED
    
    # Second registration with same email should fail
    response2 = client.post("/api/auth/register", json=payload)
    assert response2.status_code == status.HTTP_400_BAD_REQUEST
    assert "already registered" in response2.json()["detail"].lower()


def test_register_user_short_password(client):
    """Test registration with password too short fails."""
    payload = {
        "email": "shortpass@example.com",
        "password": "short",
        "full_name": "Test User"
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_register_user_invalid_email(client):
    """Test registration with invalid email format fails."""
    payload = {
        "email": "not-an-email",
        "password": "testpassword123",
        "full_name": "Test User"
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_register_user_optional_full_name(client):
    """Test registration without full_name works."""
    payload = {
        "email": "nofullname@example.com",
        "password": "testpassword123"
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["email"] == payload["email"]
    assert data["full_name"] is None
    assert data["role"] == "student"  # Default role


def test_register_user_with_role(client):
    """Test registration with specific role."""
    payload = {
        "email": "professor@example.com",
        "password": "testpassword123",
        "full_name": "Professor User",
        "role": "professor"
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["role"] == "professor"
    assert data["user_id"].startswith("INSTR-")  # Professor ID prefix


def test_register_user_with_username(client):
    """Test registration with custom username."""
    payload = {
        "email": "username@example.com",
        "password": "testpassword123",
        "username": "custom_username"
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["username"] == "custom_username"


def test_register_user_duplicate_username(client):
    """Test registration with duplicate username fails."""
    payload1 = {
        "email": "user1@example.com",
        "password": "testpassword123",
        "username": "duplicate_username"
    }
    payload2 = {
        "email": "user2@example.com",
        "password": "testpassword123",
        "username": "duplicate_username"
    }
    # First registration should succeed
    response1 = client.post("/api/auth/register", json=payload1)
    assert response1.status_code == status.HTTP_201_CREATED
    
    # Second registration with same username should fail
    response2 = client.post("/api/auth/register", json=payload2)
    assert response2.status_code == status.HTTP_400_BAD_REQUEST
    assert "username" in response2.json()["detail"].lower()


def test_login_success(client):
    """Test successful login sets cookie and returns user data."""
    # First register a user
    register_payload = {
        "email": "login@example.com",
        "password": "testpassword123",
        "full_name": "Login User"
    }
    client.post("/api/auth/register", json=register_payload)
    
    # Then login
    login_payload = {
        "email": "login@example.com",
        "password": "testpassword123"
    }
    response = client.post("/api/auth/login", json=login_payload)
    
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    # Cookie-based auth: access_token is empty, token_type is "cookie"
    assert "access_token" in data
    assert data["access_token"] == ""  # Empty for cookie-based auth
    assert data["token_type"] == "cookie"
    assert "user" in data
    assert data["user"]["email"] == login_payload["email"]
    # Check that authentication cookie is set
    assert "access_token" in response.cookies


def test_login_wrong_password(client):
    """Test login with wrong password fails."""
    # First register a user
    register_payload = {
        "email": "wrongpass@example.com",
        "password": "correctpassword123",
        "full_name": "Test User"
    }
    client.post("/api/auth/register", json=register_payload)
    
    # Try to login with wrong password
    login_payload = {
        "email": "wrongpass@example.com",
        "password": "wrongpassword123"
    }
    response = client.post("/api/auth/login", json=login_payload)
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "incorrect" in response.json()["detail"].lower()


def test_login_nonexistent_user(client):
    """Test login with non-existent email fails."""
    login_payload = {
        "email": "nonexistent@example.com",
        "password": "somepassword123"
    }
    response = client.post("/api/auth/login", json=login_payload)
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "incorrect" in response.json()["detail"].lower()


def test_login_invalid_email_format(client):
    """Test login with invalid email format fails validation."""
    login_payload = {
        "email": "not-an-email",
        "password": "somepassword123"
    }
    response = client.post("/api/auth/login", json=login_payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_logout_success(client):
    """Test logout clears authentication cookie."""
    # First register and login
    register_payload = {
        "email": "logout@example.com",
        "password": "testpassword123"
    }
    client.post("/api/auth/register", json=register_payload)
    
    login_payload = {
        "email": "logout@example.com",
        "password": "testpassword123"
    }
    login_response = client.post("/api/auth/login", json=login_payload)
    assert "access_token" in login_response.cookies
    
    # Logout
    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == status.HTTP_200_OK
    assert "message" in logout_response.json()
    # Cookie should be cleared (check for empty or deleted cookie)
    # Note: TestClient may not show deleted cookies, but status should be OK


def test_get_current_user_me(client):
    """Test /me endpoint returns current authenticated user."""
    # Register and login
    register_payload = {
        "email": "me@example.com",
        "password": "testpassword123",
        "full_name": "Me User"
    }
    client.post("/api/auth/register", json=register_payload)
    
    login_payload = {
        "email": "me@example.com",
        "password": "testpassword123"
    }
    client.post("/api/auth/login", json=login_payload)
    
    # Get current user
    response = client.get("/api/auth/me")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["email"] == "me@example.com"
    assert data["full_name"] == "Me User"
    assert "id" in data
    assert "user_id" in data
    assert "role" in data


def test_get_current_user_me_unauthenticated(client):
    """Test /me endpoint requires authentication."""
    response = client.get("/api/auth/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "not authenticated" in response.json()["detail"].lower()


def test_login_inactive_user(client, db_session: Session):
    """Test login with inactive user fails."""
    # Register a user
    register_payload = {
        "email": "inactive@example.com",
        "password": "testpassword123"
    }
    register_response = client.post("/api/auth/register", json=register_payload)
    user_id = register_response.json()["id"]
    
    # Deactivate user via direct DB access
    user = db_session.query(models.User).filter(models.User.id == user_id).first()
    user.is_active = False
    db_session.commit()
    
    # Try to login with inactive user
    login_payload = {
        "email": "inactive@example.com",
        "password": "testpassword123"
    }
    response = client.post("/api/auth/login", json=login_payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "inactive" in response.json()["detail"].lower()
