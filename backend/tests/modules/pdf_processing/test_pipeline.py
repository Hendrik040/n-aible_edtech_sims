"""
Tests for PDF processing pipeline.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from sqlalchemy.orm import Session

from modules.pdf_processing.pipeline import PDFProcessingPipeline
from database.models import User


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
    mock_file = Mock()
    mock_file.filename = "test.pdf"
    mock_file.content_type = "application/pdf"
    mock_file.read = AsyncMock(return_value=b"PDF content")
    return mock_file


@pytest.fixture
def pipeline(mock_db, mock_user):
    """Create a pipeline instance"""
    with patch('modules.pdf_processing.pipeline.get_repository'):
        with patch('modules.pdf_processing.pipeline.parser_service'):
            with patch('modules.pdf_processing.pipeline.ai_extraction_service'):
                return PDFProcessingPipeline(mock_db, mock_user)


@pytest.mark.asyncio
async def test_process_fast_autofill_success(pipeline, mock_upload_file):
    """Test successful fast autofill processing"""
    # Mock repository
    mock_scenario = Mock()
    mock_scenario.id = 1
    mock_scenario.status = "creating"
    pipeline.repository.create_scenario = Mock(return_value=mock_scenario)
    pipeline.repository.save_autofill_data = Mock(return_value=True)
    
    # Mock parser
    pipeline.parser.parse_file_flexible = AsyncMock(return_value="Parsed content")
    
    # Mock AI service
    pipeline.ai_service.preprocess_content = Mock(return_value={
        "title": "Test Case",
        "cleaned_content": "Cleaned content"
    })
    pipeline.ai_service.extract_personas_fast = AsyncMock(return_value={
        "title": "Test Case",
        "description": "Test description",
        "student_role": "Business Analyst",
        "key_figures": [{"name": "Test Person", "role": "CEO"}]
    })
    
    # Mock image generation
    with patch('modules.pdf_processing.pipeline.generate_personas_with_avatars', new=AsyncMock(return_value=[{"name": "Test Person"}])):
        result = await pipeline.process_fast_autofill(mock_upload_file)
        
        assert result["status"] == "fast_autofill_completed"
        assert result["scenario_id"] == 1
        assert "personas" in result


@pytest.mark.asyncio
async def test_process_full_success(pipeline, mock_upload_file):
    """Test successful full processing"""
    # Mock parser
    pipeline.parser.parse_file_flexible = AsyncMock(return_value="Parsed content")
    
    # Mock AI service
    pipeline.ai_service.preprocess_content = Mock(return_value={
        "title": "Test Case",
        "cleaned_content": "Cleaned content"
    })
    
    personas_result = {
        "title": "Test Case",
        "description": "Test description",
        "student_role": "Business Analyst",
        "key_figures": [{"name": "Test Person", "role": "CEO"}]
    }
    
    pipeline.ai_service.extract_personas_and_key_figures = AsyncMock(return_value=personas_result)
    pipeline.ai_service.generate_scenes = AsyncMock(return_value=[{"title": "Scene 1"}])
    pipeline.ai_service.generate_learning_outcomes = AsyncMock(return_value=["Outcome 1"])
    
    result = await pipeline.process_full(mock_upload_file)
    
    assert result["status"] == "completed"
    assert "ai_result" in result
    assert result["ai_result"]["title"] == "Test Case"


@pytest.mark.asyncio
async def test_process_fast_autofill_error_handling(pipeline, mock_upload_file):
    """Test error handling in fast autofill"""
    # Mock repository to create scenario
    mock_scenario = Mock()
    mock_scenario.id = 1
    pipeline.repository.create_scenario = Mock(return_value=mock_scenario)
    pipeline.repository.update_scenario_status_to_draft = Mock(return_value=True)
    
    # Mock parser to raise an error
    pipeline.parser.parse_file_flexible = AsyncMock(side_effect=Exception("Parsing failed"))
    
    with pytest.raises(Exception) as exc_info:
        await pipeline.process_fast_autofill(mock_upload_file)
    
    assert "Parsing failed" in str(exc_info.value)
    # Verify scenario status was updated
    pipeline.repository.update_scenario_status_to_draft.assert_called_once_with(1)
