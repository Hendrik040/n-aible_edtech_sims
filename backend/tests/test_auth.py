"""
Unit tests for authentication and user management endpoints
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

def test_health_check(client: TestClient):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data

def test_root_endpoint(client: TestClient):
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "AI Simulation Marketplace Platform API"
    assert data["version"] == "2.0.0"
    assert data["status"] == "active"

def test_user_registration(client: TestClient, db_session: Session):
    """Test user registration"""
    user_data = {
        "email": "newuser@test.com",
        "username": "newuser",
        "full_name": "New User",
        "password": "testpass123",
        "role": "student",
        "bio": "Test bio"
    }
    
    response = client.post("/users/register", json=user_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["email"] == user_data["email"]
    assert data["username"] == user_data["username"]
    assert data["role"] == user_data["role"]
    assert "id" in data

def test_user_registration_duplicate_email(client: TestClient, test_professor):
    """Test user registration with duplicate email"""
    user_data = {
        "email": test_professor.email,
        "username": "differentuser",
        "full_name": "Different User",
        "password": "testpass123",
        "role": "student"
    }
    
    response = client.post("/users/register", json=user_data)
    assert response.status_code == 400
    assert "Email already registered" in response.json()["detail"]

def test_user_registration_duplicate_username(client: TestClient, test_professor):
    """Test user registration with duplicate username"""
    user_data = {
        "email": "different@test.com",
        "username": test_professor.username,
        "full_name": "Different User",
        "password": "testpass123",
        "role": "student"
    }
    
    response = client.post("/users/register", json=user_data)
    assert response.status_code == 400
    assert "Username already taken" in response.json()["detail"]

def test_user_login(client: TestClient, test_professor):
    """Test user login"""
    login_data = {
        "email": test_professor.email,
        "password": "testpass123"
    }
    
    response = client.post("/users/login", json=login_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["token_type"] == "cookie"
    assert data["user"]["email"] == test_professor.email
    assert data["user"]["role"] == test_professor.role

def test_user_login_invalid_credentials(client: TestClient):
    """Test user login with invalid credentials"""
    login_data = {
        "email": "nonexistent@test.com",
        "password": "wrongpassword"
    }
    
    response = client.post("/users/login", json=login_data)
    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]

def test_check_email_exists(client: TestClient, test_professor):
    """Test email existence check"""
    # Test existing email
    response = client.post("/users/check-email", json={"email": test_professor.email})
    assert response.status_code == 200
    assert response.json()["exists"] == True
    
    # Test non-existing email
    response = client.post("/users/check-email", json={"email": "nonexistent@test.com"})
    assert response.status_code == 200
    assert response.json()["exists"] == False

def test_get_current_user_profile(client: TestClient, auth_headers_professor):
    """Test get current user profile"""
    response = client.get("/users/me", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert data["email"] == "professor@test.com"
    assert data["role"] == "professor"

def test_get_current_user_profile_unauthorized(client: TestClient):
    """Test get current user profile without authentication"""
    response = client.get("/users/me")
    assert response.status_code == 401

def test_update_user_profile(client: TestClient, auth_headers_professor):
    """Test update user profile"""
    update_data = {
        "full_name": "Updated Professor",
        "bio": "Updated bio"
    }
    
    response = client.put("/users/me", json=update_data, headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert data["full_name"] == update_data["full_name"]
    assert data["bio"] == update_data["bio"]

def test_change_password(client: TestClient, auth_headers_professor):
    """Test change password"""
    password_data = {
        "current_password": "testpass123",
        "new_password": "newpass123"
    }
    
    response = client.post("/users/change-password", json=password_data, headers=auth_headers_professor)
    assert response.status_code == 200
    assert "Password changed successfully" in response.json()["message"]

def test_change_password_wrong_current(client: TestClient, auth_headers_professor):
    """Test change password with wrong current password"""
    password_data = {
        "current_password": "wrongpassword",
        "new_password": "newpass123"
    }
    
    response = client.post("/users/change-password", json=password_data, headers=auth_headers_professor)
    assert response.status_code == 400
    assert "Current password is incorrect" in response.json()["detail"]

def test_logout(client: TestClient):
    """Test user logout"""
    response = client.post("/users/logout")
    assert response.status_code == 200
    assert "Successfully logged out" in response.json()["message"]

def test_get_user_profile_public(client: TestClient, test_professor):
    """Test get public user profile"""
    # Make profile public
    test_professor.profile_public = True
    
    response = client.get(f"/users/{test_professor.id}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["email"] == test_professor.email
    assert data["role"] == test_professor.role

def test_get_user_profile_private(client: TestClient, test_professor):
    """Test get private user profile"""
    # Make profile private
    test_professor.profile_public = False
    
    response = client.get(f"/users/{test_professor.id}")
    assert response.status_code == 404
    assert "Profile is private" in response.json()["detail"]

def test_track_user_activity(client: TestClient, auth_headers_professor):
    """Test track user activity"""
    activity_data = {"action": "test_action"}
    
    response = client.post("/users/activity", json=activity_data, headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "success"
    assert "timestamp" in data

