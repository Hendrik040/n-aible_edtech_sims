"""
Unit tests for cohorts API endpoints
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

def test_get_cohorts(client: TestClient, auth_headers_professor, test_cohort):
    """Test get cohorts for professor"""
    response = client.get("/cohorts/", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    
    # Check if our test cohort is in the response
    cohort_found = any(cohort["id"] == test_cohort.id for cohort in data)
    assert cohort_found

def test_get_cohorts_unauthorized(client: TestClient):
    """Test get cohorts without authentication"""
    response = client.get("/cohorts/")
    assert response.status_code == 401

def test_create_cohort(client: TestClient, auth_headers_professor, test_professor):
    """Test create new cohort"""
    cohort_data = {
        "name": "New Test Cohort",
        "description": "A new test cohort",
        "is_active": True
    }
    
    response = client.post("/cohorts/", json=cohort_data, headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert data["name"] == cohort_data["name"]
    assert data["description"] == cohort_data["description"]
    assert data["professor_id"] == test_professor.id
    assert "cohort_id" in data

def test_create_cohort_unauthorized(client: TestClient, auth_headers_student):
    """Test create cohort as student"""
    cohort_data = {
        "name": "Student Cohort",
        "description": "A cohort by student",
        "is_active": True
    }
    
    response = client.post("/cohorts/", json=cohort_data, headers=auth_headers_student)
    assert response.status_code == 403

def test_get_cohort_by_id(client: TestClient, auth_headers_professor, test_cohort):
    """Test get specific cohort by ID"""
    response = client.get(f"/cohorts/{test_cohort.id}", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert data["id"] == test_cohort.id
    assert data["name"] == test_cohort.name
    assert data["cohort_id"] == test_cohort.cohort_id

def test_get_cohort_by_id_not_found(client: TestClient, auth_headers_professor):
    """Test get non-existent cohort"""
    response = client.get("/cohorts/99999", headers=auth_headers_professor)
    assert response.status_code == 404
    assert "Cohort not found" in response.json()["detail"]

def test_update_cohort(client: TestClient, auth_headers_professor, test_cohort):
    """Test update cohort"""
    update_data = {
        "name": "Updated Cohort Name",
        "description": "Updated description",
        "is_active": False
    }
    
    response = client.put(f"/cohorts/{test_cohort.id}", json=update_data, headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert data["name"] == update_data["name"]
    assert data["description"] == update_data["description"]
    assert data["is_active"] == update_data["is_active"]

def test_update_cohort_unauthorized(client: TestClient, auth_headers_student, test_cohort):
    """Test update cohort by different user"""
    update_data = {
        "name": "Unauthorized Update",
        "description": "This should fail"
    }
    
    response = client.put(f"/cohorts/{test_cohort.id}", json=update_data, headers=auth_headers_student)
    assert response.status_code == 403

def test_delete_cohort(client: TestClient, auth_headers_professor, test_cohort):
    """Test delete cohort"""
    response = client.delete(f"/cohorts/{test_cohort.id}", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert "deleted successfully" in data["message"]

def test_delete_cohort_unauthorized(client: TestClient, auth_headers_student, test_cohort):
    """Test delete cohort by different user"""
    response = client.delete(f"/cohorts/{test_cohort.id}", headers=auth_headers_student)
    assert response.status_code == 403

def test_add_student_to_cohort(client: TestClient, auth_headers_professor, test_cohort, test_student):
    """Test add student to cohort"""
    student_data = {
        "student_id": test_student.id,
        "enrollment_date": "2024-01-01T00:00:00Z"
    }
    
    response = client.post(f"/cohorts/{test_cohort.id}/students", json=student_data, headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert data["student_id"] == test_student.id
    assert data["cohort_id"] == test_cohort.id

def test_add_student_to_cohort_not_found(client: TestClient, auth_headers_professor):
    """Test add student to non-existent cohort"""
    student_data = {
        "student_id": 1,
        "enrollment_date": "2024-01-01T00:00:00Z"
    }
    
    response = client.post("/cohorts/99999/students", json=student_data, headers=auth_headers_professor)
    assert response.status_code == 404

def test_get_cohort_students(client: TestClient, auth_headers_professor, test_cohort):
    """Test get students in cohort"""
    response = client.get(f"/cohorts/{test_cohort.id}/students", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_remove_student_from_cohort(client: TestClient, auth_headers_professor, test_cohort, test_student, db_session: Session):
    """Test remove student from cohort"""
    # First add student to cohort
    from database.models import CohortStudent
    cohort_student = CohortStudent(
        cohort_id=test_cohort.id,
        student_id=test_student.id
    )
    db_session.add(cohort_student)
    db_session.commit()
    
    response = client.delete(f"/cohorts/{test_cohort.id}/students/{test_student.id}", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert "removed successfully" in data["message"]

def test_assign_simulation_to_cohort(client: TestClient, auth_headers_professor, test_cohort, test_scenario):
    """Test assign simulation to cohort"""
    simulation_data = {
        "scenario_id": test_scenario.id,
        "due_date": "2024-12-31T23:59:59Z",
        "instructions": "Complete this simulation"
    }
    
    response = client.post(f"/cohorts/{test_cohort.id}/simulations", json=simulation_data, headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert data["scenario_id"] == test_scenario.id
    assert data["cohort_id"] == test_cohort.id

def test_get_cohort_simulations(client: TestClient, auth_headers_professor, test_cohort):
    """Test get simulations assigned to cohort"""
    response = client.get(f"/cohorts/{test_cohort.id}/simulations", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_cohort_by_code(client: TestClient, test_cohort):
    """Test get cohort by join code"""
    response = client.get(f"/cohorts/join/{test_cohort.cohort_id}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["cohort_id"] == test_cohort.cohort_id
    assert data["name"] == test_cohort.name

def test_get_cohort_by_code_not_found(client: TestClient):
    """Test get cohort by invalid join code"""
    response = client.get("/cohorts/join/INVALID_CODE")
    assert response.status_code == 404
    assert "Cohort not found" in response.json()["detail"]

