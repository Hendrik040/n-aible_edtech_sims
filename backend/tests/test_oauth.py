"""
Unit tests for OAuth API endpoints
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock

def test_google_oauth_login(client: TestClient):
    """Test Google OAuth login initiation"""
    response = client.get("/oauth/google/login")
    assert response.status_code == 200
    
    data = response.json()
    assert "auth_url" in data
    assert "state" in data

def test_google_oauth_callback_success(client: TestClient):
    """Test Google OAuth callback with successful authentication"""
    mock_user_info = {
        "email": "test@example.com",
        "name": "Test User",
        "picture": "https://example.com/avatar.jpg"
    }
    
    with patch('api.oauth.get_google_user_info') as mock_get_user:
        mock_get_user.return_value = mock_user_info
        
        with patch('api.oauth.create_or_get_user') as mock_create_user:
            mock_create_user.return_value = {
                "id": 1,
                "email": "test@example.com",
                "full_name": "Test User",
                "role": "student"
            }
            
            response = client.get("/oauth/google/callback?code=test_code&state=test_state")
            assert response.status_code == 200
            
            data = response.json()
            assert "access_token" in data
            assert "user" in data

def test_google_oauth_callback_invalid_code(client: TestClient):
    """Test Google OAuth callback with invalid code"""
    with patch('api.oauth.get_google_user_info') as mock_get_user:
        mock_get_user.side_effect = Exception("Invalid code")
        
        response = client.get("/oauth/google/callback?code=invalid_code&state=test_state")
        assert response.status_code == 400
        assert "Authentication failed" in response.json()["detail"]

def test_google_oauth_callback_missing_code(client: TestClient):
    """Test Google OAuth callback with missing code"""
    response = client.get("/oauth/google/callback?state=test_state")
    assert response.status_code == 400
    assert "Authorization code not provided" in response.json()["detail"]

def test_google_oauth_callback_missing_state(client: TestClient):
    """Test Google OAuth callback with missing state"""
    response = client.get("/oauth/google/callback?code=test_code")
    assert response.status_code == 400
    assert "State parameter not provided" in response.json()["detail"]

def test_google_oauth_callback_state_mismatch(client: TestClient):
    """Test Google OAuth callback with state mismatch"""
    with patch('api.oauth.get_google_user_info') as mock_get_user:
        mock_get_user.return_value = {
            "email": "test@example.com",
            "name": "Test User"
        }
        
        response = client.get("/oauth/google/callback?code=test_code&state=wrong_state")
        assert response.status_code == 400
        assert "State mismatch" in response.json()["detail"]

def test_google_oauth_logout(client: TestClient):
    """Test Google OAuth logout"""
    response = client.post("/oauth/google/logout")
    assert response.status_code == 200
    
    data = response.json()
    assert "message" in data
    assert "logged out" in data["message"].lower()

def test_google_oauth_user_info(client: TestClient, auth_headers_student):
    """Test get Google OAuth user info"""
    response = client.get("/oauth/google/userinfo", headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert "email" in data
    assert "name" in data

def test_google_oauth_user_info_unauthorized(client: TestClient):
    """Test get Google OAuth user info without authentication"""
    response = client.get("/oauth/google/userinfo")
    assert response.status_code == 401

def test_google_oauth_refresh_token(client: TestClient):
    """Test refresh Google OAuth token"""
    refresh_data = {
        "refresh_token": "test_refresh_token"
    }
    
    with patch('api.oauth.refresh_google_token') as mock_refresh:
        mock_refresh.return_value = {
            "access_token": "new_access_token",
            "expires_in": 3600
        }
        
        response = client.post("/oauth/google/refresh", json=refresh_data)
        assert response.status_code == 200
        
        data = response.json()
        assert "access_token" in data
        assert "expires_in" in data

def test_google_oauth_refresh_token_invalid(client: TestClient):
    """Test refresh Google OAuth token with invalid refresh token"""
    refresh_data = {
        "refresh_token": "invalid_refresh_token"
    }
    
    with patch('api.oauth.refresh_google_token') as mock_refresh:
        mock_refresh.side_effect = Exception("Invalid refresh token")
        
        response = client.post("/oauth/google/refresh", json=refresh_data)
        assert response.status_code == 400
        assert "Token refresh failed" in response.json()["detail"]

def test_google_oauth_revoke_token(client: TestClient, auth_headers_student):
    """Test revoke Google OAuth token"""
    response = client.post("/oauth/google/revoke", headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert "message" in data
    assert "revoked" in data["message"].lower()

def test_google_oauth_callback_new_user_creation(client: TestClient):
    """Test Google OAuth callback with new user creation"""
    mock_user_info = {
        "email": "newuser@example.com",
        "name": "New User",
        "picture": "https://example.com/avatar.jpg"
    }
    
    with patch('api.oauth.get_google_user_info') as mock_get_user:
        mock_get_user.return_value = mock_user_info
        
        with patch('api.oauth.create_or_get_user') as mock_create_user:
            mock_create_user.return_value = {
                "id": 2,
                "email": "newuser@example.com",
                "full_name": "New User",
                "role": "student",
                "is_new_user": True
            }
            
            response = client.get("/oauth/google/callback?code=test_code&state=test_state")
            assert response.status_code == 200
            
            data = response.json()
            assert "access_token" in data
            assert "user" in data
            assert data["user"]["is_new_user"] == True

def test_google_oauth_callback_existing_user(client: TestClient):
    """Test Google OAuth callback with existing user"""
    mock_user_info = {
        "email": "existing@example.com",
        "name": "Existing User",
        "picture": "https://example.com/avatar.jpg"
    }
    
    with patch('api.oauth.get_google_user_info') as mock_get_user:
        mock_get_user.return_value = mock_user_info
        
        with patch('api.oauth.create_or_get_user') as mock_create_user:
            mock_create_user.return_value = {
                "id": 1,
                "email": "existing@example.com",
                "full_name": "Existing User",
                "role": "student",
                "is_new_user": False
            }
            
            response = client.get("/oauth/google/callback?code=test_code&state=test_state")
            assert response.status_code == 200
            
            data = response.json()
            assert "access_token" in data
            assert "user" in data
            assert data["user"]["is_new_user"] == False

def test_google_oauth_callback_database_error(client: TestClient):
    """Test Google OAuth callback with database error"""
    mock_user_info = {
        "email": "test@example.com",
        "name": "Test User"
    }
    
    with patch('api.oauth.get_google_user_info') as mock_get_user:
        mock_get_user.return_value = mock_user_info
        
        with patch('api.oauth.create_or_get_user') as mock_create_user:
            mock_create_user.side_effect = Exception("Database error")
            
            response = client.get("/oauth/google/callback?code=test_code&state=test_state")
            assert response.status_code == 500
            assert "Internal server error" in response.json()["detail"]

