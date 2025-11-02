"""
Unit tests for simulation API endpoints
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock

def test_linear_simulation_chat(client: TestClient, auth_headers_student, test_scenario, mock_openai):
    """Test linear simulation chat"""
    chat_data = {
        "user_progress_id": 1,
        "message": "Hello, I want to start the simulation",
        "scene_id": 1
    }
    
    response = client.post("/simulation/linear-chat", json=chat_data, headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert "response" in data
    assert "scene_id" in data
    assert "user_progress_id" in data

def test_linear_simulation_chat_unauthorized(client: TestClient, test_scenario):
    """Test linear simulation chat without authentication"""
    chat_data = {
        "user_progress_id": 1,
        "message": "Hello, I want to start the simulation",
        "scene_id": 1
    }
    
    response = client.post("/simulation/linear-chat", json=chat_data)
    assert response.status_code == 401

def test_linear_simulation_chat_invalid_progress_id(client: TestClient, auth_headers_student):
    """Test linear simulation chat with invalid progress ID"""
    chat_data = {
        "user_progress_id": 99999,
        "message": "Hello, I want to start the simulation",
        "scene_id": 1
    }
    
    response = client.post("/simulation/linear-chat", json=chat_data, headers=auth_headers_student)
    assert response.status_code == 404
    assert "User progress not found" in response.json()["detail"]

def test_get_user_responses(client: TestClient, auth_headers_student):
    """Test get user responses"""
    response = client.get("/simulation/user-responses?user_progress_id=1", headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_user_responses_unauthorized(client: TestClient):
    """Test get user responses without authentication"""
    response = client.get("/simulation/user-responses?user_progress_id=1")
    assert response.status_code == 401

def test_get_user_responses_with_scene_filter(client: TestClient, auth_headers_student):
    """Test get user responses with scene filter"""
    response = client.get("/simulation/user-responses?user_progress_id=1&scene_id=1", headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_simulation_progress(client: TestClient, auth_headers_student):
    """Test get simulation progress"""
    response = client.get("/simulation/progress?user_progress_id=1", headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert "progress" in data
    assert "current_scene" in data
    assert "total_scenes" in data

def test_get_simulation_progress_unauthorized(client: TestClient):
    """Test get simulation progress without authentication"""
    response = client.get("/simulation/progress?user_progress_id=1")
    assert response.status_code == 401

def test_start_simulation(client: TestClient, auth_headers_student, test_scenario):
    """Test start simulation"""
    start_data = {
        "scenario_id": test_scenario.id,
        "cohort_id": None
    }
    
    response = client.post("/simulation/start", json=start_data, headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert "user_progress_id" in data
    assert "scenario_id" in data
    assert "current_scene" in data

def test_start_simulation_unauthorized(client: TestClient, test_scenario):
    """Test start simulation without authentication"""
    start_data = {
        "scenario_id": test_scenario.id,
        "cohort_id": None
    }
    
    response = client.post("/simulation/start", json=start_data)
    assert response.status_code == 401

def test_start_simulation_scenario_not_found(client: TestClient, auth_headers_student):
    """Test start simulation with non-existent scenario"""
    start_data = {
        "scenario_id": 99999,
        "cohort_id": None
    }
    
    response = client.post("/simulation/start", json=start_data, headers=auth_headers_student)
    assert response.status_code == 404
    assert "Scenario not found" in response.json()["detail"]

def test_pause_simulation(client: TestClient, auth_headers_student):
    """Test pause simulation"""
    pause_data = {
        "user_progress_id": 1
    }
    
    response = client.post("/simulation/pause", json=pause_data, headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert "status" in data
    assert data["status"] == "paused"

def test_resume_simulation(client: TestClient, auth_headers_student):
    """Test resume simulation"""
    resume_data = {
        "user_progress_id": 1
    }
    
    response = client.post("/simulation/resume", json=resume_data, headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert "status" in data
    assert data["status"] == "active"

def test_end_simulation(client: TestClient, auth_headers_student):
    """Test end simulation"""
    end_data = {
        "user_progress_id": 1,
        "completion_status": "completed"
    }
    
    response = client.post("/simulation/end", json=end_data, headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert "status" in data
    assert data["status"] == "completed"

def test_get_simulation_history(client: TestClient, auth_headers_student):
    """Test get simulation history"""
    response = client.get("/simulation/history", headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_simulation_history_unauthorized(client: TestClient):
    """Test get simulation history without authentication"""
    response = client.get("/simulation/history")
    assert response.status_code == 401

def test_get_simulation_analytics(client: TestClient, auth_headers_professor):
    """Test get simulation analytics (professor only)"""
    response = client.get("/simulation/analytics", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert "total_simulations" in data
    assert "completion_rate" in data

def test_get_simulation_analytics_unauthorized(client: TestClient, auth_headers_student):
    """Test get simulation analytics as student"""
    response = client.get("/simulation/analytics", headers=auth_headers_student)
    assert response.status_code == 403

def test_get_scenario_personas(client: TestClient, auth_headers_student, test_scenario):
    """Test get scenario personas"""
    response = client.get(f"/simulation/scenarios/{test_scenario.id}/personas", headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_scenario_scenes(client: TestClient, auth_headers_student, test_scenario):
    """Test get scenario scenes"""
    response = client.get(f"/simulation/scenarios/{test_scenario.id}/scenes", headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_save_simulation_state(client: TestClient, auth_headers_student):
    """Test save simulation state"""
    state_data = {
        "user_progress_id": 1,
        "scene_id": 1,
        "state_data": {"key": "value"}
    }
    
    response = client.post("/simulation/save-state", json=state_data, headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert "status" in data
    assert data["status"] == "saved"

def test_load_simulation_state(client: TestClient, auth_headers_student):
    """Test load simulation state"""
    response = client.get("/simulation/load-state?user_progress_id=1", headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert "state_data" in data

