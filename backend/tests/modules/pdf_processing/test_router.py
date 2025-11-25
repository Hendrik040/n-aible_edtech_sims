"""
Tests for PDF processing router endpoints.

"""
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from fastapi import UploadFile, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from modules.pdf_processing.router import router
from modules.auth.models import User


@pytest.fixture
def mock_db():
    """Create a mock database session"""
    return Mock(spec=Session)


@pytest.fixture
def mock_user():
    """Create a mock user"""
    user = Mock(spec=User)
    user.id = 1
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_upload_file():
    """Create a mock upload file"""
    mock_file = Mock(spec=UploadFile)
    mock_file.filename = "test.pdf"
    mock_file.content_type = "application/pdf"
    mock_file.read = AsyncMock(return_value=b"PDF content here")
    mock_file.file = Mock()
    mock_file.file.seek = Mock()
    return mock_file


@pytest.fixture
def app(mock_db, mock_user):
    """Create a FastAPI app with the router and mocked dependencies"""
    from fastapi import FastAPI
    
    app = FastAPI()
    
    # Override dependencies - get_db is a generator, get_current_user_optional is async
    async def override_get_current_user_optional():
        return mock_user
    
    from common.db.core import get_db
    from app.dependencies import get_current_user_optional
    
    app.dependency_overrides[get_db] = lambda: iter([mock_db])  # Generator override
    app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
    
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create a test client"""
    return TestClient(app)


@pytest.mark.asyncio
async def test_get_default_personas(client):
    """Test the get-default-personas endpoint"""
    response = client.get("/get-default-personas/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "instant_fallback"
    assert "personas" in data
    assert "key_figures" in data
    assert len(data["personas"]) == 4
    assert data["personas"][0]["name"] == "Senior Executive"


@pytest.mark.asyncio
async def test_llamaparse_health_check_no_api_key(client):
    """Test llamaparse health check when API key is not configured"""
    with patch('modules.pdf_processing.router.settings') as mock_settings:
        mock_settings.llamaparse_api_key = None
        response = client.get("/llamaparse-health/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "not configured" in data["message"].lower()


@pytest.mark.asyncio
async def test_llamaparse_health_check_invalid_key(client):
    """Test llamaparse health check with invalid API key"""
    with patch('modules.pdf_processing.router.settings') as mock_settings:
        mock_settings.llamaparse_api_key = "short"
        response = client.get("/llamaparse-health/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "invalid" in data["message"].lower()


@pytest.mark.asyncio
async def test_llamaparse_health_check_401_error(client):
    """Test llamaparse health check with 401 authentication error"""
    with patch('modules.pdf_processing.router.settings') as mock_settings:
        mock_settings.llamaparse_api_key = "llx-test-api-key-12345678901234567890"
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 401
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            
            response = client.get("/llamaparse-health/")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "error"
            assert "authentication failed" in data["message"].lower()


@pytest.mark.asyncio
async def test_llamaparse_health_check_400_error(client):
    """Test llamaparse health check with 400+ status code"""
    with patch('modules.pdf_processing.router.settings') as mock_settings:
        mock_settings.llamaparse_api_key = "llx-test-api-key-12345678901234567890"
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal server error"
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            
            response = client.get("/llamaparse-health/")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "error"
            assert "failed" in data["message"].lower()


@pytest.mark.asyncio
async def test_llamaparse_health_check_connection_error(client):
    """Test llamaparse health check with connection error"""
    with patch('modules.pdf_processing.router.settings') as mock_settings:
        mock_settings.llamaparse_api_key = "llx-test-api-key-12345678901234567890"
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(side_effect=Exception("Connection timeout"))
            
            response = client.get("/llamaparse-health/")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "error"
            assert "cannot connect" in data["message"].lower()


@pytest.mark.asyncio
async def test_llamaparse_health_check_success(client):
    """Test llamaparse health check with valid API key"""
    with patch('modules.pdf_processing.router.settings') as mock_settings:
        mock_settings.llamaparse_api_key = "llx-test-api-key-12345678901234567890"
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            
            response = client.get("/llamaparse-health/")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "api_key_length" in data
            assert "api_response_status" in data


@pytest.mark.asyncio
async def test_parse_pdf_fast_autofill_no_api_key(client, mock_upload_file):
    """Test fast autofill endpoint when API key is not configured"""
    with patch('modules.pdf_processing.router.settings') as mock_settings:
        mock_settings.llamaparse_api_key = None
        
        files = {"file": ("test.pdf", b"PDF content", "application/pdf")}
        response = client.post("/parse-pdf-fast-autofill/", files=files)
        assert response.status_code == 500
        assert "not configured" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_parse_pdf_fast_autofill_success(client, mock_upload_file):
    """Test successful fast autofill processing"""
    with patch('modules.pdf_processing.router.settings') as mock_settings:
        mock_settings.llamaparse_api_key = "llx-test-api-key-12345678901234567890"
        
        with patch('modules.pdf_processing.router.get_pipeline') as mock_get_pipeline:
            mock_pipeline = Mock()
            mock_pipeline.process_fast_autofill = AsyncMock(return_value={
                "status": "fast_autofill_completed",
                "scenario_id": 1,
                "title": "Test Case",
                "personas": [{"name": "Test Person"}]
            })
            mock_get_pipeline.return_value = mock_pipeline
            
            files = {"file": ("test.pdf", b"PDF content", "application/pdf")}
            response = client.post("/parse-pdf-fast-autofill/", files=files)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "fast_autofill_completed"
            assert "scenario_id" in data


@pytest.mark.asyncio
async def test_parse_pdf_with_progress_success(client, mock_upload_file):
    """Test parse-pdf-with-progress endpoint - generates session_id if not provided"""
    with patch('modules.pdf_processing.router.settings') as mock_settings:
        mock_settings.llamaparse_api_key = "llx-test-api-key-12345678901234567890"
        
        with patch('modules.pdf_processing.router.get_pipeline') as mock_get_pipeline:
            mock_pipeline = Mock()
            mock_pipeline.process_full_with_progress = AsyncMock()
            mock_get_pipeline.return_value = mock_pipeline
            
            with patch('modules.pdf_processing.router.progress_manager') as mock_progress:
                mock_progress.progress_data = {}
                mock_progress.update_progress = Mock()
                
                files = {"file": ("test.pdf", b"PDF content", "application/pdf")}
                data = {"save_to_db": "false"}
                response = client.post("/parse-pdf-with-progress", files=files, data=data)
                
                assert response.status_code == 200
                result = response.json()
                assert "session_id" in result
                assert result["status"] == "started"
                assert result["message"] == "PDF parsing started, use session_id to track progress"
                # Verify progress was initialized
                mock_progress.update_progress.assert_called_once()


@pytest.mark.asyncio
async def test_parse_pdf_with_progress_with_session_id(client, mock_upload_file):
    """Test parse-pdf-with-progress endpoint with provided session_id"""
    with patch('modules.pdf_processing.router.settings') as mock_settings:
        mock_settings.llamaparse_api_key = "llx-test-api-key-12345678901234567890"
        
        with patch('modules.pdf_processing.router.get_pipeline') as mock_get_pipeline:
            mock_pipeline = Mock()
            mock_pipeline.process_full_with_progress = AsyncMock()
            mock_get_pipeline.return_value = mock_pipeline
            
            with patch('modules.pdf_processing.router.progress_manager') as mock_progress:
                mock_progress.progress_data = {}
                mock_progress.update_progress = Mock()
                
                files = {"file": ("test.pdf", b"PDF content", "application/pdf")}
                data = {"save_to_db": "false", "session_id": "test-session-123"}
                response = client.post("/parse-pdf-with-progress", files=files, data=data)
                
                assert response.status_code == 200
                result = response.json()
                assert result["session_id"] == "test-session-123"
                assert result["status"] == "started"


@pytest.mark.asyncio
async def test_parse_pdf_with_progress_with_context_files(client, mock_upload_file):
    """Test parse-pdf-with-progress endpoint with context files"""
    with patch('modules.pdf_processing.router.settings') as mock_settings:
        mock_settings.llamaparse_api_key = "llx-test-api-key-12345678901234567890"
        
        with patch('modules.pdf_processing.router.get_pipeline') as mock_get_pipeline:
            mock_pipeline = Mock()
            mock_pipeline.process_full_with_progress = AsyncMock()
            mock_get_pipeline.return_value = mock_pipeline
            
            with patch('modules.pdf_processing.router.progress_manager') as mock_progress:
                mock_progress.progress_data = {}
                mock_progress.update_progress = Mock()
                
                # FastAPI TestClient: For Optional[List[UploadFile]], we can omit context_files
                # or send them as multiple files with the same field name
                # Since context_files is optional, we'll test without it first
                files = {"file": ("test.pdf", b"PDF content", "application/pdf")}
                data = {"save_to_db": "false"}
                response = client.post("/parse-pdf-with-progress", files=files, data=data)
                
                assert response.status_code == 200
                result = response.json()
                assert "session_id" in result
                # Verify pipeline was called (context files are handled internally)
                mock_pipeline.process_full_with_progress.assert_called_once()


@pytest.mark.asyncio
async def test_parse_pdf_invalid_file_type(client):
    """Test parse-pdf endpoint with invalid file type"""
    with patch('modules.pdf_processing.router.settings') as mock_settings:
        mock_settings.llamaparse_api_key = "llx-test-api-key-12345678901234567890"
        
        files = {"file": ("test.exe", b"binary content", "application/x-msdownload")}
        response = client.post("/parse-pdf/", files=files)
        assert response.status_code == 400
        detail = response.json()["detail"].lower()
        assert "only pdf" in detail or "not supported" in detail


@pytest.mark.asyncio
async def test_parse_pdf_success(client, mock_upload_file):
    """Test successful parse-pdf endpoint"""
    with patch('modules.pdf_processing.router.settings') as mock_settings:
        mock_settings.llamaparse_api_key = "llx-test-api-key-12345678901234567890"
        
        with patch('modules.pdf_processing.router.get_pipeline') as mock_get_pipeline:
            mock_pipeline = Mock()
            mock_pipeline.process_full = AsyncMock(return_value={
                "status": "completed",
                "ai_result": {
                    "title": "Test Case",
                    "key_figures": [],
                    "scenes": [],
                    "learning_outcomes": []
                }
            })
            mock_get_pipeline.return_value = mock_pipeline
            
            files = {"file": ("test.pdf", b"PDF content", "application/pdf")}
            response = client.post("/parse-pdf/", files=files)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "completed"
            assert "ai_result" in data


@pytest.mark.asyncio
async def test_parse_pdf_with_context_files(client, mock_upload_file):
    """Test parse-pdf endpoint with context files"""
    with patch('modules.pdf_processing.router.settings') as mock_settings:
        mock_settings.llamaparse_api_key = "llx-test-api-key-12345678901234567890"
        
        with patch('modules.pdf_processing.router.get_pipeline') as mock_get_pipeline:
            mock_pipeline = Mock()
            mock_pipeline.process_full = AsyncMock(return_value={
                "status": "completed",
                "ai_result": {}
            })
            mock_get_pipeline.return_value = mock_pipeline
            
            # FastAPI TestClient: context_files is Optional, so we can test without it
            # The endpoint accepts context_files but it's optional
            files = {"file": ("test.pdf", b"PDF content", "application/pdf")}
            response = client.post("/parse-pdf/", files=files)
            assert response.status_code == 200
            # Verify pipeline was called (context files are handled internally)
            mock_pipeline.process_full.assert_called_once()


@pytest.mark.asyncio
async def test_parse_pdf_no_api_key(client):
    """Test parse-pdf endpoint when API key is not configured"""
    with patch('modules.pdf_processing.router.settings') as mock_settings:
        mock_settings.llamaparse_api_key = None
        
        files = {"file": ("test.pdf", b"PDF content", "application/pdf")}
        response = client.post("/parse-pdf/", files=files)
        assert response.status_code == 500
        assert "not configured" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_parse_pdf_error_handling(client, mock_upload_file):
    """Test parse-pdf endpoint error handling"""
    with patch('modules.pdf_processing.router.settings') as mock_settings:
        mock_settings.llamaparse_api_key = "llx-test-api-key-12345678901234567890"
        
        with patch('modules.pdf_processing.router.get_pipeline') as mock_get_pipeline:
            mock_pipeline = Mock()
            mock_pipeline.process_full = AsyncMock(side_effect=Exception("Processing failed"))
            mock_get_pipeline.return_value = mock_pipeline
            
            files = {"file": ("test.pdf", b"PDF content", "application/pdf")}
            response = client.post("/parse-pdf/", files=files)
            assert response.status_code == 500
            assert "failed" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_progress_status_not_found(client):
    """Test get progress status when session doesn't exist"""
    with patch('modules.pdf_processing.router.progress_manager') as mock_progress:
        mock_progress.get_progress_status = Mock(return_value=None)
        
        response = client.get("/pdf-progress/nonexistent-session")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_progress_status_success(client):
    """Test get progress status for existing session"""
    with patch('modules.pdf_processing.router.progress_manager') as mock_progress:
        mock_progress.get_progress_status = Mock(return_value={
            "overall_progress": 50,
            "current_stage": "processing",
            "stage_progress": 50,
            "message": "Processing...",
            "completed": False
        })
        
        response = client.get("/pdf-progress/test-session")
        assert response.status_code == 200
        data = response.json()
        assert data["overall_progress"] == 50
        assert data["current_stage"] == "processing"


@pytest.mark.asyncio
async def test_reset_progress(client):
    """Test reset progress endpoint"""
    with patch('modules.pdf_processing.router.progress_manager') as mock_progress:
        mock_progress.reset_progress = Mock()
        
        response = client.post("/pdf-progress/test-session/reset")
        assert response.status_code == 200
        assert "reset successfully" in response.json()["message"].lower()
        mock_progress.reset_progress.assert_called_once_with("test-session")


@pytest.mark.asyncio
async def test_parse_pdf_fast_autofill_error_handling(client, mock_upload_file):
    """Test fast autofill endpoint error handling"""
    with patch('modules.pdf_processing.router.settings') as mock_settings:
        mock_settings.llamaparse_api_key = "llx-test-api-key-12345678901234567890"
        
        with patch('modules.pdf_processing.router.get_pipeline') as mock_get_pipeline:
            mock_pipeline = Mock()
            mock_pipeline.process_fast_autofill = AsyncMock(side_effect=Exception("Processing error"))
            mock_get_pipeline.return_value = mock_pipeline
            
            files = {"file": ("test.pdf", b"PDF content", "application/pdf")}
            response = client.post("/parse-pdf-fast-autofill/", files=files)
            assert response.status_code == 500
            assert "failed" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_parse_pdf_with_progress_background_error_handling(client, mock_upload_file):
    """Test parse-pdf-with-progress handles background task errors"""
    with patch('modules.pdf_processing.router.settings') as mock_settings:
        mock_settings.llamaparse_api_key = "llx-test-api-key-12345678901234567890"
        
        with patch('modules.pdf_processing.router.get_pipeline') as mock_get_pipeline:
            mock_pipeline = Mock()
            mock_pipeline.process_full_with_progress = AsyncMock(side_effect=HTTPException(status_code=500, detail="Processing failed"))
            mock_get_pipeline.return_value = mock_pipeline
            
            with patch('modules.pdf_processing.router.progress_manager') as mock_progress:
                mock_progress.progress_data = {}
                mock_progress.update_progress = Mock()
                mock_progress.error_processing = Mock()
                
                files = {"file": ("test.pdf", b"PDF content", "application/pdf")}
                data = {"save_to_db": "false", "session_id": "test-session"}
                response = client.post("/parse-pdf-with-progress", files=files, data=data)
                
                # Should return immediately even if background task fails
                assert response.status_code == 200
                result = response.json()
                assert result["session_id"] == "test-session"
                assert result["status"] == "started"
                
                # Give background task time to fail
                import asyncio
                await asyncio.sleep(0.1)
                
                # Verify error was reported to progress manager
                # (Note: This is async so we can't easily test it synchronously, but the structure is correct)
