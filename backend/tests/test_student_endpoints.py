"""
Unit tests for student-specific API endpoints
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

def test_get_pending_invitations(client: TestClient, auth_headers_student):
    """Test get pending invitations for student"""
    response = client.get("/student/notifications/pending-invitations", headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_pending_invitations_unauthorized(client: TestClient, auth_headers_professor):
    """Test get pending invitations as professor"""
    response = client.get("/student/notifications/pending-invitations", headers=auth_headers_professor)
    assert response.status_code == 403

def test_accept_invitation(client: TestClient, auth_headers_student, db_session: Session, test_cohort):
    """Test accept invitation"""
    # Create a test invitation
    from database.models import Invitation
    invitation = Invitation(
        professor_id=1,  # Assuming professor has ID 1
        student_email="student@test.com",
        cohort_id=test_cohort.id,
        status="pending"
    )
    db_session.add(invitation)
    db_session.commit()
    
    response = client.post(f"/student/notifications/invitations/{invitation.id}/accept", headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert "accepted successfully" in data["message"]

def test_accept_invitation_not_found(client: TestClient, auth_headers_student):
    """Test accept non-existent invitation"""
    response = client.post("/student/notifications/invitations/99999/accept", headers=auth_headers_student)
    assert response.status_code == 404
    assert "Invitation not found" in response.json()["detail"]

def test_decline_invitation(client: TestClient, auth_headers_student, db_session: Session, test_cohort):
    """Test decline invitation"""
    # Create a test invitation
    from database.models import Invitation
    invitation = Invitation(
        professor_id=1,  # Assuming professor has ID 1
        student_email="student@test.com",
        cohort_id=test_cohort.id,
        status="pending"
    )
    db_session.add(invitation)
    db_session.commit()
    
    response = client.post(f"/student/notifications/invitations/{invitation.id}/decline", headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert "declined successfully" in data["message"]

def test_decline_invitation_not_found(client: TestClient, auth_headers_student):
    """Test decline non-existent invitation"""
    response = client.post("/student/notifications/invitations/99999/decline", headers=auth_headers_student)
    assert response.status_code == 404
    assert "Invitation not found" in response.json()["detail"]

def test_get_student_cohorts(client: TestClient, auth_headers_student):
    """Test get student cohorts"""
    response = client.get("/student/cohorts/", headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_student_cohorts_unauthorized(client: TestClient, auth_headers_professor):
    """Test get student cohorts as professor"""
    response = client.get("/student/cohorts/", headers=auth_headers_professor)
    assert response.status_code == 403

def test_join_cohort_by_code(client: TestClient, auth_headers_student, test_cohort):
    """Test join cohort by code"""
    join_data = {
        "cohort_code": test_cohort.cohort_id
    }
    
    response = client.post("/student/cohorts/join", json=join_data, headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert data["cohort_id"] == test_cohort.cohort_id
    assert "joined successfully" in data["message"]

def test_join_cohort_by_code_invalid(client: TestClient, auth_headers_student):
    """Test join cohort with invalid code"""
    join_data = {
        "cohort_code": "INVALID_CODE"
    }
    
    response = client.post("/student/cohorts/join", json=join_data, headers=auth_headers_student)
    assert response.status_code == 404
    assert "Cohort not found" in response.json()["detail"]

def test_leave_cohort(client: TestClient, auth_headers_student, test_cohort, db_session: Session):
    """Test leave cohort"""
    # First add student to cohort
    from database.models import CohortStudent
    cohort_student = CohortStudent(
        cohort_id=test_cohort.id,
        student_id=1  # Assuming student has ID 1
    )
    db_session.add(cohort_student)
    db_session.commit()
    
    response = client.delete(f"/student/cohorts/{test_cohort.id}/leave", headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert "left successfully" in data["message"]

def test_leave_cohort_not_enrolled(client: TestClient, auth_headers_student, test_cohort):
    """Test leave cohort when not enrolled"""
    response = client.delete(f"/student/cohorts/{test_cohort.id}/leave", headers=auth_headers_student)
    assert response.status_code == 404
    assert "Not enrolled in this cohort" in response.json()["detail"]

def test_get_student_simulation_instances(client: TestClient, auth_headers_student):
    """Test get student simulation instances"""
    response = client.get("/student/simulation-instances/", headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_student_simulation_instances_unauthorized(client: TestClient, auth_headers_professor):
    """Test get student simulation instances as professor"""
    response = client.get("/student/simulation-instances/", headers=auth_headers_professor)
    assert response.status_code == 403

def test_get_simulation_instance_by_id(client: TestClient, auth_headers_student, db_session: Session):
    """Test get specific simulation instance"""
    # Create a test simulation instance
    from database.models import UserProgress
    simulation_instance = UserProgress(
        user_id=1,  # Assuming student has ID 1
        scenario_id=1,
        current_scene_id=1,
        status="active"
    )
    db_session.add(simulation_instance)
    db_session.commit()
    
    response = client.get(f"/student/simulation-instances/{simulation_instance.id}", headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert data["id"] == simulation_instance.id

def test_get_simulation_instance_by_id_not_found(client: TestClient, auth_headers_student):
    """Test get non-existent simulation instance"""
    response = client.get("/student/simulation-instances/99999", headers=auth_headers_student)
    assert response.status_code == 404
    assert "Simulation instance not found" in response.json()["detail"]

def test_get_student_dashboard(client: TestClient, auth_headers_student):
    """Test get student dashboard data"""
    response = client.get("/student/dashboard", headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert "enrolled_cohorts" in data
    assert "active_simulations" in data
    assert "completed_simulations" in data

def test_get_student_dashboard_unauthorized(client: TestClient, auth_headers_professor):
    """Test get student dashboard as professor"""
    response = client.get("/student/dashboard", headers=auth_headers_professor)
    assert response.status_code == 403

def test_get_student_progress(client: TestClient, auth_headers_student):
    """Test get student progress"""
    response = client.get("/student/progress", headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert "overall_progress" in data
    assert "cohort_progress" in data
    assert "simulation_progress" in data

def test_get_student_progress_unauthorized(client: TestClient, auth_headers_professor):
    """Test get student progress as professor"""
    response = client.get("/student/progress", headers=auth_headers_professor)
    assert response.status_code == 403

def test_get_student_achievements(client: TestClient, auth_headers_student):
    """Test get student achievements"""
    response = client.get("/student/achievements", headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_student_achievements_unauthorized(client: TestClient, auth_headers_professor):
    """Test get student achievements as professor"""
    response = client.get("/student/achievements", headers=auth_headers_professor)
    assert response.status_code == 403

def test_update_student_preferences(client: TestClient, auth_headers_student):
    """Test update student preferences"""
    preferences_data = {
        "notifications_enabled": True,
        "email_notifications": False,
        "theme": "dark"
    }
    
    response = client.put("/student/preferences", json=preferences_data, headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert data["notifications_enabled"] == True
    assert data["email_notifications"] == False
    assert data["theme"] == "dark"

def test_update_student_preferences_unauthorized(client: TestClient, auth_headers_professor):
    """Test update student preferences as professor"""
    preferences_data = {
        "notifications_enabled": True
    }
    
    response = client.put("/student/preferences", json=preferences_data, headers=auth_headers_professor)
    assert response.status_code == 403

