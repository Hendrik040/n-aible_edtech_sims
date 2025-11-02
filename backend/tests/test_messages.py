"""
Unit tests for messaging API endpoints
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

def test_send_message(client: TestClient, auth_headers_professor, test_student):
    """Test send message to student"""
    message_data = {
        "recipient_id": test_student.id,
        "subject": "Test Message",
        "content": "This is a test message",
        "message_type": "text"
    }
    
    response = client.post("/messages/", json=message_data, headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert data["recipient_id"] == test_student.id
    assert data["subject"] == message_data["subject"]
    assert data["content"] == message_data["content"]
    assert data["sender_id"] is not None

def test_send_message_recipient_not_found(client: TestClient, auth_headers_professor):
    """Test send message to non-existent recipient"""
    message_data = {
        "recipient_id": 99999,
        "subject": "Test Message",
        "content": "This is a test message",
        "message_type": "text"
    }
    
    response = client.post("/messages/", json=message_data, headers=auth_headers_professor)
    assert response.status_code == 404
    assert "Recipient not found" in response.json()["detail"]

def test_send_message_unauthorized(client: TestClient, test_student):
    """Test send message without authentication"""
    message_data = {
        "recipient_id": test_student.id,
        "subject": "Test Message",
        "content": "This is a test message",
        "message_type": "text"
    }
    
    response = client.post("/messages/", json=message_data)
    assert response.status_code == 401

def test_send_message_with_cohort(client: TestClient, auth_headers_professor, test_student, test_cohort):
    """Test send message with cohort context"""
    message_data = {
        "recipient_id": test_student.id,
        "subject": "Cohort Message",
        "content": "This is a message about the cohort",
        "message_type": "text",
        "cohort_id": test_cohort.id
    }
    
    response = client.post("/messages/", json=message_data, headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert data["cohort_id"] == test_cohort.id

def test_send_message_cohort_not_found(client: TestClient, auth_headers_professor, test_student):
    """Test send message with non-existent cohort"""
    message_data = {
        "recipient_id": test_student.id,
        "subject": "Cohort Message",
        "content": "This is a message about the cohort",
        "message_type": "text",
        "cohort_id": 99999
    }
    
    response = client.post("/messages/", json=message_data, headers=auth_headers_professor)
    assert response.status_code == 404
    assert "Cohort not found" in response.json()["detail"]

def test_get_messages(client: TestClient, auth_headers_professor):
    """Test get messages for current user"""
    response = client.get("/messages/", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_messages_with_pagination(client: TestClient, auth_headers_professor):
    """Test get messages with pagination"""
    response = client.get("/messages/?page=1&page_size=10", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_messages_unauthorized(client: TestClient):
    """Test get messages without authentication"""
    response = client.get("/messages/")
    assert response.status_code == 401

def test_get_message_thread(client: TestClient, auth_headers_professor, test_professor, test_student, db_session: Session):
    """Test get message thread between users"""
    # First create a message
    from database.models import ProfessorStudentMessage
    message = ProfessorStudentMessage(
        sender_id=test_professor.id,
        recipient_id=test_student.id,
        subject="Test Thread",
        content="Initial message",
        message_type="text"
    )
    db_session.add(message)
    db_session.commit()
    
    response = client.get(f"/messages/thread/{test_student.id}", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert isinstance(data, list)

def test_get_message_thread_not_found(client: TestClient, auth_headers_professor):
    """Test get message thread with non-existent user"""
    response = client.get("/messages/thread/99999", headers=auth_headers_professor)
    assert response.status_code == 404

def test_reply_to_message(client: TestClient, auth_headers_student, test_professor, db_session: Session):
    """Test reply to a message"""
    # First create a message from professor to student
    from database.models import ProfessorStudentMessage
    original_message = ProfessorStudentMessage(
        sender_id=test_professor.id,
        recipient_id=1,  # Assuming student has ID 1
        subject="Original Message",
        content="Original content",
        message_type="text"
    )
    db_session.add(original_message)
    db_session.commit()
    
    reply_data = {
        "original_message_id": original_message.id,
        "content": "This is a reply",
        "message_type": "text"
    }
    
    response = client.post("/messages/reply", json=reply_data, headers=auth_headers_student)
    assert response.status_code == 200
    
    data = response.json()
    assert data["content"] == reply_data["content"]
    assert data["original_message_id"] == original_message.id

def test_reply_to_message_not_found(client: TestClient, auth_headers_student):
    """Test reply to non-existent message"""
    reply_data = {
        "original_message_id": 99999,
        "content": "This is a reply",
        "message_type": "text"
    }
    
    response = client.post("/messages/reply", json=reply_data, headers=auth_headers_student)
    assert response.status_code == 404
    assert "Original message not found" in response.json()["detail"]

def test_mark_message_as_read(client: TestClient, auth_headers_professor, db_session: Session):
    """Test mark message as read"""
    # Create a message
    from database.models import ProfessorStudentMessage
    message = ProfessorStudentMessage(
        sender_id=1,
        recipient_id=1,
        subject="Test Message",
        content="Test content",
        message_type="text",
        is_read=False
    )
    db_session.add(message)
    db_session.commit()
    
    response = client.put(f"/messages/{message.id}/read", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert data["is_read"] == True

def test_mark_message_as_read_not_found(client: TestClient, auth_headers_professor):
    """Test mark non-existent message as read"""
    response = client.put("/messages/99999/read", headers=auth_headers_professor)
    assert response.status_code == 404
    assert "Message not found" in response.json()["detail"]

def test_delete_message(client: TestClient, auth_headers_professor, db_session: Session):
    """Test delete message"""
    # Create a message
    from database.models import ProfessorStudentMessage
    message = ProfessorStudentMessage(
        sender_id=1,
        recipient_id=1,
        subject="Test Message",
        content="Test content",
        message_type="text"
    )
    db_session.add(message)
    db_session.commit()
    
    response = client.delete(f"/messages/{message.id}", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert "deleted successfully" in data["message"]

def test_delete_message_not_found(client: TestClient, auth_headers_professor):
    """Test delete non-existent message"""
    response = client.delete("/messages/99999", headers=auth_headers_professor)
    assert response.status_code == 404
    assert "Message not found" in response.json()["detail"]

def test_get_unread_message_count(client: TestClient, auth_headers_professor):
    """Test get unread message count"""
    response = client.get("/messages/unread-count", headers=auth_headers_professor)
    assert response.status_code == 200
    
    data = response.json()
    assert "unread_count" in data
    assert isinstance(data["unread_count"], int)

