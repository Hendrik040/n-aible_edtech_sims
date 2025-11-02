"""
Unit tests for scenario management endpoints
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

def test_get_scenarios_authenticated(client: TestClient, auth_headers_professor, test_scenario):
    """Test get scenarios for authenticated user"""
    response = client.get("/api/scenarios/", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    
    # Check if our test scenario is in the response
    scenario_found = any(scenario["id"] == test_scenario.id for scenario in data)
    assert scenario_found

def test_get_scenarios_unauthenticated(client: TestClient, test_scenario):
    """Test get scenarios for unauthenticated user"""
    response = client.get("/api/scenarios/")
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)
    # Should only show public scenarios
    for scenario in data:
        assert scenario["is_public"] == True

def test_get_draft_scenarios(client: TestClient, auth_headers_professor, db_session: Session, test_professor):
    """Test get draft scenarios"""
    # Create a draft scenario
    from database.models import Scenario
    draft_scenario = Scenario(
        unique_id="DRAFT_001",
        title="Draft Scenario",
        description="A draft scenario",
        challenge="Test challenge",
        industry="Technology",
        status="draft",
        is_draft=True,
        is_public=False,
        created_by=test_professor.id
    )
    db_session.add(draft_scenario)
    db_session.commit()
    
    response = client.get("/api/scenarios/drafts/", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    
    # Check that all returned scenarios are drafts
    for scenario in data:
        assert scenario["is_draft"] == True

def test_get_draft_scenario(client: TestClient, auth_headers_professor, db_session: Session, test_professor):
    """Test get specific draft scenario"""
    # Create a draft scenario
    from database.models import Scenario
    draft_scenario = Scenario(
        unique_id="DRAFT_002",
        title="Specific Draft Scenario",
        description="A specific draft scenario",
        challenge="Test challenge",
        industry="Technology",
        status="draft",
        is_draft=True,
        is_public=False,
        created_by=test_professor.id
    )
    db_session.add(draft_scenario)
    db_session.commit()
    
    response = client.get(f"/api/scenarios/drafts/{draft_scenario.id}", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert data["id"] == draft_scenario.id
    assert data["title"] == draft_scenario.title
    assert data["is_draft"] == True

def test_get_draft_scenario_not_found(client: TestClient, auth_headers_professor):
    """Test get non-existent draft scenario"""
    response = client.get("/api/scenarios/drafts/99999", headers=auth_headers_professor)
    assert response.status_code == 404
    assert "Draft scenario not found" in response.json()["detail"]

def test_get_draft_scenario_unauthorized(client: TestClient, auth_headers_student, db_session: Session, test_professor):
    """Test get draft scenario by different user"""
    # Create a draft scenario by professor
    from database.models import Scenario
    draft_scenario = Scenario(
        unique_id="DRAFT_003",
        title="Professor's Draft",
        description="A draft scenario by professor",
        challenge="Test challenge",
        industry="Technology",
        status="draft",
        is_draft=True,
        is_public=False,
        created_by=test_professor.id
    )
    db_session.add(draft_scenario)
    db_session.commit()
    
    # Try to access as student
    response = client.get(f"/api/scenarios/drafts/{draft_scenario.id}", headers=auth_headers_student)
    assert response.status_code == 404

def test_delete_scenario_by_unique_id(client: TestClient, auth_headers_professor, test_scenario):
    """Test delete scenario by unique ID"""
    response = client.delete(f"/api/scenarios/unique/{test_scenario.unique_id}", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "success"
    assert "deleted successfully" in data["message"]

def test_delete_scenario_by_unique_id_not_found(client: TestClient, auth_headers_professor):
    """Test delete non-existent scenario by unique ID"""
    response = client.delete("/api/scenarios/unique/NONEXISTENT", headers=auth_headers_professor)
    assert response.status_code == 404
    assert "Scenario not found" in response.json()["detail"]

def test_delete_draft_scenario(client: TestClient, auth_headers_professor, db_session: Session, test_professor):
    """Test delete draft scenario"""
    # Create a draft scenario
    from database.models import Scenario
    draft_scenario = Scenario(
        unique_id="DRAFT_004",
        title="Draft to Delete",
        description="A draft scenario to delete",
        challenge="Test challenge",
        industry="Technology",
        status="draft",
        is_draft=True,
        is_public=False,
        created_by=test_professor.id
    )
    db_session.add(draft_scenario)
    db_session.commit()
    
    response = client.delete(f"/api/scenarios/drafts/{draft_scenario.id}", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert "deleted successfully" in data["message"]
    assert data["deleted_id"] == draft_scenario.id

def test_update_scenario_status(client: TestClient, auth_headers_professor, test_scenario):
    """Test update scenario status"""
    status_data = {"status": "draft"}
    
    response = client.put(f"/api/scenarios/{test_scenario.id}/status", json=status_data, headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "draft"
    assert data["is_draft"] == True
    assert data["is_public"] == False

def test_update_scenario_status_invalid(client: TestClient, auth_headers_professor, test_scenario):
    """Test update scenario status with invalid status"""
    status_data = {"status": "invalid_status"}
    
    response = client.put(f"/api/scenarios/{test_scenario.id}/status", json=status_data, headers=auth_headers_professor)
    assert response.status_code == 400
    assert "Invalid status" in response.json()["detail"]

def test_update_scenario_status_unauthorized(client: TestClient, auth_headers_student, test_scenario):
    """Test update scenario status by different user"""
    status_data = {"status": "draft"}
    
    response = client.put(f"/api/scenarios/{test_scenario.id}/status", json=status_data, headers=auth_headers_student)
    assert response.status_code == 403
    assert "Not authorized" in response.json()["detail"]

def test_get_public_scenarios(client: TestClient, test_scenario):
    """Test get public scenarios for marketplace"""
    response = client.get("/scenarios")
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)
    # Should only show public scenarios
    for scenario in data:
        assert scenario["is_public"] == True

def test_get_scenario_details(client: TestClient, test_scenario):
    """Test get scenario details"""
    response = client.get(f"/scenarios/{test_scenario.id}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["id"] == test_scenario.id
    assert data["title"] == test_scenario.title
    assert "persona_count" in data
    assert "scene_count" in data

def test_get_scenario_details_not_found(client: TestClient):
    """Test get non-existent scenario details"""
    response = client.get("/scenarios/99999")
    assert response.status_code == 404
    assert "Scenario not found" in response.json()["detail"]

