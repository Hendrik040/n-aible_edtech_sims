"""Tests for auth router endpoints."""

import pytest
from fastapi import status


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
    assert "id" in data
    assert "created_at" in data
    assert "password" not in data
    assert "password_hash" not in data


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


def test_login_success(client):
    """Test successful login returns access token."""
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
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 0


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
