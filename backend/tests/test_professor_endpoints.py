"""
Unit tests for professor-specific API endpoints
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

def test_send_message_to_student(client: TestClient, auth_headers_professor, test_student):
    """Test professor send message to student"""
    message_data = {
        "recipient_id": test_student.id,
        "subject": "Professor Message",
        "content": "This is a message from professor",
        "message_type": "text"
    }
    
    response = client.post("/professor/messages/send", json=message_data, headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert data["recipient_id"] == test_student.id
    assert data["subject"] == message_data["subject"]
    assert data["content"] == message_data["content"]

def test_send_message_to_student_unauthorized(client: TestClient, auth_headers_student, test_student):
    """Test student trying to send message as professor"""
    message_data = {
        "recipient_id": test_student.id,
        "subject": "Student Message",
        "content": "This should fail",
        "message_type": "text"
    }
    
    response = client.post("/professor/messages/send", json=message_data, headers=auth_headers_student)
    assert response.status_code == 403

def test_get_professor_notifications(client: TestClient, auth_headers_professor):
    """Test get professor notifications"""
    response = client.get("/professor/notifications/", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_professor_notifications_with_filters(client: TestClient, auth_headers_professor):
    """Test get professor notifications with filters"""
    response = client.get("/professor/notifications/?unread_only=true&limit=10", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_professor_notifications_unauthorized(client: TestClient, auth_headers_student):
    """Test get professor notifications as student"""
    response = client.get("/professor/notifications/", headers=auth_headers_student)
    assert response.status_code == 403

def test_get_unread_notification_count(client: TestClient, auth_headers_professor):
    """Test get unread notification count"""
    response = client.get("/professor/notifications/unread-count", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert "unread_count" in data
    assert isinstance(data["unread_count"], int)

def test_mark_notification_as_read(client: TestClient, auth_headers_professor, db_session: Session):
    """Test mark notification as read"""
    # Create a test notification
    from database.models import Notification
    notification = Notification(
        user_id=1,  # Assuming professor has ID 1
        title="Test Notification",
        message="Test notification message",
        notification_type="message",
        is_read=False
    )
    db_session.add(notification)
    db_session.commit()
    
    response = client.put(f"/professor/notifications/{notification.id}/read", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert data["is_read"] == True

def test_mark_notification_as_read_not_found(client: TestClient, auth_headers_professor):
    """Test mark non-existent notification as read"""
    response = client.put("/professor/notifications/99999/read", headers=auth_headers_professor)
    assert response.status_code == 404
    assert "Notification not found" in response.json()["detail"]

def test_send_invitation_to_student(client: TestClient, auth_headers_professor, test_student, test_cohort):
    """Test send invitation to student"""
    invitation_data = {
        "student_email": test_student.email,
        "cohort_id": test_cohort.id,
        "message": "You are invited to join this cohort"
    }
    
    response = client.post("/professor/invitations/send", json=invitation_data, headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert data["student_email"] == test_student.email
    assert data["cohort_id"] == test_cohort.id

def test_send_invitation_to_student_unauthorized(client: TestClient, auth_headers_student, test_student, test_cohort):
    """Test send invitation as student"""
    invitation_data = {
        "student_email": test_student.email,
        "cohort_id": test_cohort.id,
        "message": "This should fail"
    }
    
    response = client.post("/professor/invitations/send", json=invitation_data, headers=auth_headers_student)
    assert response.status_code == 403

def test_send_invitation_invalid_email(client: TestClient, auth_headers_professor, test_cohort):
    """Test send invitation with invalid email"""
    invitation_data = {
        "student_email": "invalid-email",
        "cohort_id": test_cohort.id,
        "message": "Invalid email test"
    }
    
    response = client.post("/professor/invitations/send", json=invitation_data, headers=auth_headers_professor)
    assert response.status_code == 400
    assert "Invalid email format" in response.json()["detail"]

def test_send_invitation_cohort_not_found(client: TestClient, auth_headers_professor, test_student):
    """Test send invitation to non-existent cohort"""
    invitation_data = {
        "student_email": test_student.email,
        "cohort_id": 99999,
        "message": "Cohort not found test"
    }
    
    response = client.post("/professor/invitations/send", json=invitation_data, headers=auth_headers_professor)
    assert response.status_code == 404
    assert "Cohort not found" in response.json()["detail"]

def test_get_sent_invitations(client: TestClient, auth_headers_professor):
    """Test get sent invitations"""
    response = client.get("/professor/invitations/sent", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_sent_invitations_with_filters(client: TestClient, auth_headers_professor):
    """Test get sent invitations with filters"""
    response = client.get("/professor/invitations/sent?status=pending&limit=10", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_cancel_invitation(client: TestClient, auth_headers_professor, db_session: Session):
    """Test cancel invitation"""
    # Create a test invitation
    from database.models import Invitation
    invitation = Invitation(
        professor_id=1,  # Assuming professor has ID 1
        student_email="test@example.com",
        cohort_id=1,
        status="pending"
    )
    db_session.add(invitation)
    db_session.commit()
    
    response = client.delete(f"/professor/invitations/{invitation.id}/cancel", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert "cancelled successfully" in data["message"]

def test_cancel_invitation_not_found(client: TestClient, auth_headers_professor):
    """Test cancel non-existent invitation"""
    response = client.delete("/professor/invitations/99999/cancel", headers=auth_headers_professor)
    assert response.status_code == 404
    assert "Invitation not found" in response.json()["detail"]

def test_get_professor_dashboard(client: TestClient, auth_headers_professor):
    """Test get professor dashboard data"""
    response = client.get("/professor/dashboard", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert "total_cohorts" in data
    assert "total_students" in data
    assert "active_simulations" in data

def test_get_professor_dashboard_unauthorized(client: TestClient, auth_headers_student):
    """Test get professor dashboard as student"""
    response = client.get("/professor/dashboard", headers=auth_headers_student)
    assert response.status_code == 403

def test_get_professor_analytics(client: TestClient, auth_headers_professor):
    """Test get professor analytics"""
    response = client.get("/professor/analytics", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert "cohort_performance" in data
    assert "student_engagement" in data
    assert "simulation_completion" in data

def test_get_professor_analytics_unauthorized(client: TestClient, auth_headers_student):
    """Test get professor analytics as student"""
    response = client.get("/professor/analytics", headers=auth_headers_student)
    assert response.status_code == 403

