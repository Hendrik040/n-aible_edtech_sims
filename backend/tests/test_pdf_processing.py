"""
Unit tests for PDF processing API endpoints
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock
import io

def test_parse_pdf_with_progress(client: TestClient, auth_headers_professor):
    """Test parse PDF with progress tracking"""
    # Create a mock PDF file
    pdf_content = b"Mock PDF content"
    files = {
        "file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")
    }
    data = {
        "save_to_db": "false",
        "session_id": "test_session_123"
    }
    
    with patch('api.parse_pdf.parse_pdf_with_progress') as mock_parse:
        mock_parse.return_value = {
            "status": "success",
            "session_id": "test_session_123",
            "progress": 100
        }
        
        response = client.post("/parse-pdf-with-progress", files=files, data=data, headers=auth_headers_professor)
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "success"
        assert data["session_id"] == "test_session_123"

def test_parse_pdf_with_progress_unauthorized(client: TestClient):
    """Test parse PDF without authentication"""
    pdf_content = b"Mock PDF content"
    files = {
        "file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")
    }
    data = {
        "save_to_db": "false",
        "session_id": "test_session_123"
    }
    
    response = client.post("/parse-pdf-with-progress", files=files, data=data)
    assert response.status_code == 401

def test_parse_pdf_with_context_files(client: TestClient, auth_headers_professor):
    """Test parse PDF with context files"""
    pdf_content = b"Mock PDF content"
    context_content = b"Mock context content"
    
    files = {
        "file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf"),
        "context_files": [
            ("context1.txt", io.BytesIO(context_content), "text/plain"),
            ("context2.txt", io.BytesIO(context_content), "text/plain")
        ]
    }
    data = {
        "save_to_db": "false",
        "session_id": "test_session_456"
    }
    
    with patch('api.parse_pdf.parse_pdf_with_progress') as mock_parse:
        mock_parse.return_value = {
            "status": "success",
            "session_id": "test_session_456",
            "progress": 100
        }
        
        response = client.post("/parse-pdf-with-progress", files=files, data=data, headers=auth_headers_professor)
        assert response.status_code == 200

def test_parse_pdf_invalid_file_type(client: TestClient, auth_headers_professor):
    """Test parse PDF with invalid file type"""
    invalid_content = b"Not a PDF"
    files = {
        "file": ("test.txt", io.BytesIO(invalid_content), "text/plain")
    }
    data = {
        "save_to_db": "false",
        "session_id": "test_session_789"
    }
    
    response = client.post("/parse-pdf-with-progress", files=files, data=data, headers=auth_headers_professor)
    assert response.status_code == 400
    assert "Only PDF, TXT, MD, DOC, and DOCX files are supported" in response.json()["detail"]

def test_parse_pdf_missing_api_key(client: TestClient, auth_headers_professor):
    """Test parse PDF with missing API key"""
    pdf_content = b"Mock PDF content"
    files = {
        "file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")
    }
    data = {
        "save_to_db": "false",
        "session_id": "test_session_no_key"
    }
    
    with patch('api.parse_pdf.LLAMAPARSE_API_KEY', None):
        response = client.post("/parse-pdf-with-progress", files=files, data=data, headers=auth_headers_professor)
        assert response.status_code == 500
        assert "LlamaParse API key not configured" in response.json()["detail"]

def test_get_pdf_progress(client: TestClient, auth_headers_professor):
    """Test get PDF progress status"""
    session_id = "test_session_progress"
    
    with patch('api.pdf_progress.progress_manager') as mock_manager:
        mock_manager.progress_data = {
            session_id: {
                "status": "processing",
                "progress": 50,
                "message": "Processing PDF..."
            }
        }
        
        response = client.get(f"/pdf-progress/{session_id}", headers=auth_headers_professor)
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "processing"
        assert data["progress"] == 50

def test_get_pdf_progress_not_found(client: TestClient, auth_headers_professor):
    """Test get PDF progress for non-existent session"""
    session_id = "nonexistent_session"
    
    with patch('api.pdf_progress.progress_manager') as mock_manager:
        mock_manager.progress_data = {}
        
        response = client.get(f"/pdf-progress/{session_id}", headers=auth_headers_professor)
        assert response.status_code == 404
        assert "Session not found" in response.json()["detail"]

def test_reset_pdf_progress(client: TestClient, auth_headers_professor):
    """Test reset PDF progress"""
    session_id = "test_session_reset"
    
    with patch('api.pdf_progress.progress_manager') as mock_manager:
        mock_manager.progress_data = {
            session_id: {
                "status": "processing",
                "progress": 50
            }
        }
        
        response = client.post(f"/pdf-progress/{session_id}/reset", headers=auth_headers_professor)
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "reset"

def test_parse_pdf_main_endpoint(client: TestClient, auth_headers_professor):
    """Test main parse PDF endpoint"""
    pdf_content = b"Mock PDF content"
    files = {
        "file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")
    }
    data = {
        "save_to_db": "false"
    }
    
    with patch('api.parse_pdf.parse_pdf_with_progress') as mock_parse:
        mock_parse.return_value = {
            "status": "success",
            "result": "Parsed content"
        }
        
        response = client.post("/api/parse-pdf/", files=files, data=data, headers=auth_headers_professor)
        assert response.status_code == 200

def test_parse_pdf_with_save_to_db(client: TestClient, auth_headers_professor, db_session):
    """Test parse PDF with save to database"""
    pdf_content = b"Mock PDF content"
    files = {
        "file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")
    }
    data = {
        "save_to_db": "true",
        "session_id": "test_session_save"
    }
    
    with patch('api.parse_pdf.parse_pdf_with_progress') as mock_parse:
        mock_parse.return_value = {
            "status": "success",
            "session_id": "test_session_save",
            "saved_to_db": True
        }
        
        response = client.post("/parse-pdf-with-progress", files=files, data=data, headers=auth_headers_professor)
        assert response.status_code == 200
        
        data = response.json()
        assert data["saved_to_db"] == True

def test_parse_pdf_processing_error(client: TestClient, auth_headers_professor):
    """Test parse PDF with processing error"""
    pdf_content = b"Mock PDF content"
    files = {
        "file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")
    }
    data = {
        "save_to_db": "false",
        "session_id": "test_session_error"
    }
    
    with patch('api.parse_pdf.parse_pdf_with_progress') as mock_parse:
        mock_parse.side_effect = Exception("Processing error")
        
        response = client.post("/parse-pdf-with-progress", files=files, data=data, headers=auth_headers_professor)
        assert response.status_code == 500

def test_parse_pdf_large_file(client: TestClient, auth_headers_professor):
    """Test parse PDF with large file"""
    # Create a larger mock PDF file
    pdf_content = b"Mock PDF content" * 1000  # Simulate larger file
    files = {
        "file": ("large_test.pdf", io.BytesIO(pdf_content), "application/pdf")
    }
    data = {
        "save_to_db": "false",
        "session_id": "test_session_large"
    }
    
    with patch('api.parse_pdf.parse_pdf_with_progress') as mock_parse:
        mock_parse.return_value = {
            "status": "success",
            "session_id": "test_session_large",
            "file_size": len(pdf_content)
        }
        
        response = client.post("/parse-pdf-with-progress", files=files, data=data, headers=auth_headers_professor)
        assert response.status_code == 200

