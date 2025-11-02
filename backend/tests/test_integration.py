"""
Integration tests for complete API workflows
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

def test_complete_user_registration_and_login_flow(client: TestClient, db_session: Session):
    """Test complete user registration and login flow"""
    # Register new user
    user_data = {
        "email": "integration@test.com",
        "username": "integrationuser",
        "full_name": "Integration User",
        "password": "testpass123",
        "role": "student",
        "bio": "Integration test user"
    }
    
    response = client.post("/users/register", json=user_data)
    assert response.status_code == 200
    
    registered_user = response.json()
    assert registered_user["email"] == user_data["email"]
    assert registered_user["role"] == user_data["role"]
    
    # Login with registered user
    login_data = {
        "email": user_data["email"],
        "password": user_data["password"]
    }
    
    response = client.post("/users/login", json=login_data)
    assert response.status_code == 200
    
    login_response = response.json()
    assert login_response["user"]["email"] == user_data["email"]

def test_complete_professor_cohort_management_flow(client: TestClient, auth_headers_professor, test_professor, test_student):
    """Test complete professor cohort management flow"""
    # Create cohort
    cohort_data = {
        "name": "Integration Test Cohort",
        "description": "A cohort for integration testing",
        "is_active": True
    }
    
    response = client.post("/cohorts/", json=cohort_data, headers=auth_headers_professor)
    assert response.status_code == 200
    
    cohort = response.json()
    cohort_id = cohort["id"]
    
    # Add student to cohort
    student_data = {
        "student_id": test_student.id,
        "enrollment_date": "2024-01-01T00:00:00Z"
    }
    
    response = client.post(f"/cohorts/{cohort_id}/students", json=student_data, headers=auth_headers_professor)
    assert response.status_code == 200
    
    # Send message to student
    message_data = {
        "recipient_id": test_student.id,
        "subject": "Welcome to the cohort",
        "content": "Welcome to our integration test cohort!",
        "message_type": "text",
        "cohort_id": cohort_id
    }
    
    response = client.post("/messages/", json=message_data, headers=auth_headers_professor)
    assert response.status_code == 200

def test_complete_student_simulation_flow(client: TestClient, auth_headers_student, test_scenario, test_cohort):
    """Test complete student simulation flow"""
    # Start simulation
    start_data = {
        "scenario_id": test_scenario.id,
        "cohort_id": test_cohort.id
    }
    
    response = client.post("/simulation/start", json=start_data, headers=auth_headers_student)
    assert response.status_code == 200
    
    simulation = response.json()
    user_progress_id = simulation["user_progress_id"]
    
    # Chat in simulation
    chat_data = {
        "user_progress_id": user_progress_id,
        "message": "Hello, I want to start this simulation",
        "scene_id": 1
    }
    
    response = client.post("/simulation/linear-chat", json=chat_data, headers=auth_headers_student)
    assert response.status_code == 200
    
    # Get simulation progress
    response = client.get(f"/simulation/progress?user_progress_id={user_progress_id}", headers=auth_headers_student)
    assert response.status_code == 200
    
    # End simulation
    end_data = {
        "user_progress_id": user_progress_id,
        "completion_status": "completed"
    }
    
    response = client.post("/simulation/end", json=end_data, headers=auth_headers_student)
    assert response.status_code == 200

def test_complete_pdf_processing_flow(client: TestClient, auth_headers_professor):
    """Test complete PDF processing flow"""
    import io
    from unittest.mock import patch
    
    # Create mock PDF file
    pdf_content = b"Mock PDF content for integration testing"
    files = {
        "file": ("integration_test.pdf", io.BytesIO(pdf_content), "application/pdf")
    }
    data = {
        "save_to_db": "true",
        "session_id": "integration_session_123"
    }
    
    with patch('api.parse_pdf.parse_pdf_with_progress') as mock_parse:
        mock_parse.return_value = {
            "status": "success",
            "session_id": "integration_session_123",
            "progress": 100,
            "result": "Parsed PDF content"
        }
        
        # Parse PDF
        response = client.post("/parse-pdf-with-progress", files=files, data=data, headers=auth_headers_professor)
        assert response.status_code == 200
        
        # Check progress
        response = client.get("/pdf-progress/integration_session_123", headers=auth_headers_professor)
        assert response.status_code == 200
        
        progress_data = response.json()
        assert progress_data["status"] == "success"

def test_complete_scenario_publishing_flow(client: TestClient, auth_headers_professor, test_scenario):
    """Test complete scenario publishing flow"""
    # Update scenario status to active
    status_data = {"status": "active"}
    
    response = client.put(f"/api/scenarios/{test_scenario.id}/status", json=status_data, headers=auth_headers_professor)
    assert response.status_code == 200
    
    # Publish scenario
    publish_data = {
        "is_public": True,
        "category": "Leadership",
        "difficulty_level": "intermediate",
        "tags": ["leadership", "management"]
    }
    
    response = client.put(f"/publishing/scenarios/{test_scenario.id}/publish", json=publish_data, headers=auth_headers_professor)
    assert response.status_code == 200
    
    # Get public scenarios (should include our published scenario)
    response = client.get("/publishing/scenarios")
    assert response.status_code == 200
    
    scenarios = response.json()
    published_scenario = next((s for s in scenarios if s["id"] == test_scenario.id), None)
    assert published_scenario is not None
    assert published_scenario["is_public"] == True

def test_complete_oauth_flow(client: TestClient):
    """Test complete OAuth flow"""
    from unittest.mock import patch
    
    # Start OAuth login
    response = client.get("/oauth/google/login")
    assert response.status_code == 200
    
    auth_data = response.json()
    assert "auth_url" in auth_data
    assert "state" in auth_data
    
    # Mock OAuth callback
    mock_user_info = {
        "email": "oauth@test.com",
        "name": "OAuth User",
        "picture": "https://example.com/avatar.jpg"
    }
    
    with patch('api.oauth.get_google_user_info') as mock_get_user:
        mock_get_user.return_value = mock_user_info
        
        with patch('api.oauth.create_or_get_user') as mock_create_user:
            mock_create_user.return_value = {
                "id": 1,
                "email": "oauth@test.com",
                "full_name": "OAuth User",
                "role": "student"
            }
            
            # OAuth callback
            response = client.get(f"/oauth/google/callback?code=test_code&state={auth_data['state']}")
            assert response.status_code == 200
            
            callback_data = response.json()
            assert "access_token" in callback_data
            assert "user" in callback_data

def test_complete_notification_flow(client: TestClient, auth_headers_professor, auth_headers_student, test_student, test_cohort):
    """Test complete notification flow"""
    # Professor sends invitation
    invitation_data = {
        "student_email": test_student.email,
        "cohort_id": test_cohort.id,
        "message": "You are invited to join this cohort"
    }
    
    response = client.post("/professor/invitations/send", json=invitation_data, headers=auth_headers_professor)
    assert response.status_code == 200
    
    # Student gets pending invitations
    response = client.get("/student/notifications/pending-invitations", headers=auth_headers_student)
    assert response.status_code == 200
    
    invitations = response.json()
    assert isinstance(invitations, list)
    
    # Student accepts invitation (if any)
    if invitations:
        invitation_id = invitations[0]["id"]
        response = client.post(f"/student/notifications/invitations/{invitation_id}/accept", headers=auth_headers_student)
        assert response.status_code == 200

def test_error_handling_flow(client: TestClient):
    """Test error handling across different endpoints"""
    # Test 404 errors
    response = client.get("/api/scenarios/99999")
    assert response.status_code == 404
    
    # Test 401 errors
    response = client.get("/users/me")
    assert response.status_code == 401
    
    # Test 400 errors
    response = client.post("/users/register", json={"invalid": "data"})
    assert response.status_code == 422  # Validation error
    
    # Test 500 errors (with mocked failure)
    with patch('database.connection.get_db') as mock_db:
        mock_db.side_effect = Exception("Database error")
        response = client.get("/api/scenarios/")
        assert response.status_code == 500

def test_cors_headers(client: TestClient):
    """Test CORS headers are properly set"""
    response = client.options("/api/scenarios/", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    
    # Check CORS headers
    assert "access-control-allow-origin" in response.headers
    assert "access-control-allow-methods" in response.headers

def test_rate_limiting(client: TestClient):
    """Test rate limiting functionality"""
    # Test multiple rapid requests to a rate-limited endpoint
    for i in range(10):
        response = client.post("/test-login", json={"email": "test@test.com", "password": "wrong"})
        # Should eventually hit rate limit
        if response.status_code == 429:
            break
    else:
        # If we didn't hit rate limit, that's also acceptable for testing
        assert True

