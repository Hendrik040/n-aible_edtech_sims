"""
Tests for PDF parser service with mocked LlamaParse.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi import UploadFile, HTTPException

from modules.pdf_processing.parser_service import ParserService


@pytest.fixture
def parser_service():
    """Create a parser service instance"""
    with patch('modules.pdf_processing.parser_service.LLAMAPARSE_API_KEY', 'llx-test-api-key-1234567890'):
        service = ParserService()
        return service


@pytest.fixture
def mock_upload_file():
    """Create a mock upload file"""
    mock_file = Mock(spec=UploadFile)
    mock_file.filename = "test.pdf"
    mock_file.content_type = "application/pdf"
    mock_file.read = AsyncMock(return_value=b"PDF content here")
    # Add file attribute with seek method
    mock_file.file = Mock()
    mock_file.file.seek = Mock()
    return mock_file


@pytest.mark.asyncio
async def test_validate_config_success(parser_service):
    """Test successful configuration validation"""
    is_valid, message = parser_service.validate_config()
    assert is_valid is True
    assert "properly configured" in message


@pytest.mark.asyncio
async def test_validate_config_no_api_key():
    """Test configuration validation with no API key"""
    with patch('modules.pdf_processing.parser_service.LLAMAPARSE_API_KEY', None):
        service = ParserService()
        is_valid, message = service.validate_config()
        assert is_valid is False
        assert "not configured" in message


@pytest.mark.asyncio
async def test_parse_pdf_contents_success(parser_service):
    """Test successful PDF parsing"""
    file_contents = b"PDF content here"
    filename = "test.pdf"
    content_type = "application/pdf"
    
    mock_document = Mock()
    mock_document.text = "Parsed PDF text"
    
    with patch.object(parser_service, 'get_parser') as mock_get_parser:
        mock_parser = Mock()
        mock_parser.aload_data = AsyncMock(return_value=[mock_document])
        mock_get_parser.return_value = mock_parser
        
        result = await parser_service.parse_pdf_contents(
            file_contents, 
            filename, 
            content_type
        )
        
        assert result == "Parsed PDF text"
        mock_parser.aload_data.assert_called_once()


@pytest.mark.asyncio
async def test_parse_pdf_contents_empty_file(parser_service):
    """Test parsing empty PDF file"""
    file_contents = b""
    filename = "test.pdf"
    content_type = "application/pdf"
    
    with pytest.raises(HTTPException) as exc_info:
        await parser_service.parse_pdf_contents(file_contents, filename, content_type)
    
    assert exc_info.value.status_code == 400
    assert "empty" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_parse_text_file(parser_service):
    """Test parsing text file"""
    file_contents = b"Text file content"
    filename = "test.txt"
    
    result = await parser_service.parse_text_file(file_contents, filename)
    
    assert "Text file content" in result
    assert filename in result


@pytest.mark.asyncio
async def test_parse_file_flexible_pdf(parser_service, mock_upload_file):
    """Test flexible file parsing with PDF"""
    with patch.object(parser_service, 'parse_pdf_contents', new=AsyncMock(return_value="Parsed PDF")):
        result = await parser_service.parse_file_flexible(mock_upload_file)
        
        assert result == "Parsed PDF"


@pytest.mark.asyncio
async def test_parse_file_flexible_text(parser_service):
    """Test flexible file parsing with text file"""
    mock_file = Mock(spec=UploadFile)
    mock_file.filename = "test.txt"
    mock_file.content_type = "text/plain"
    mock_file.read = AsyncMock(return_value=b"Text content")
    mock_file.file = Mock()
    mock_file.file.seek = Mock()
    
    with patch.object(parser_service, 'parse_text_file', new=AsyncMock(return_value="Parsed text")):
        result = await parser_service.parse_file_flexible(mock_file)
        
        assert result == "Parsed text"
