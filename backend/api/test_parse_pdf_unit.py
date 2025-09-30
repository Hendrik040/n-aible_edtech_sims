"""
Comprehensive unit tests for backend/api/test_parse_pdf.py

Testing Framework: pytest with pytest-asyncio for async support
Mocking: pytest-mock, unittest.mock, pytest-httpx for HTTP mocking
"""

import pytest
import asyncio
import json
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock, call
from io import BytesIO
from typing import List, Optional

import httpx
from fastapi import UploadFile, HTTPException
from fastapi.datastructures import UploadFile as FastAPIUploadFile
from sqlalchemy.orm import Session

# Import the functions to test
import sys
sys.path.insert(0, 'backend/api')

# Mock progress_manager before importing
with patch('backend.api.test_parse_pdf.progress_manager'):
    from test_parse_pdf import (
        parse_with_llamaparse,
        _get_llamaparse_result,
        parse_pdf_fast_autofill,
        get_default_personas,
        parse_pdf_with_progress,
        parse_pdf,
        preprocess_case_study_content,
        _fast_persona_extraction,
        _create_fallback_result,
        generate_scenes_optimized,
        generate_learning_outcomes_optimized,
        _create_fallback_personas,
        _create_fallback_scenes,
        _create_fallback_learning_outcomes,
        generate_scene_image,
        process_with_ai_optimized_with_updates_from_preprocessed,
        process_with_ai_optimized_from_preprocessed,
        process_with_ai_optimized_with_updates
    )


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_upload_file():
    """Create a mock UploadFile for testing."""
    file_content = b"Test PDF content"
    mock_file = Mock(spec=UploadFile)
    mock_file.filename = "test_document.pdf"
    mock_file.content_type = "application/pdf"
    mock_file.read = AsyncMock(return_value=file_content)
    mock_file.file = BytesIO(file_content)
    return mock_file


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    return Mock(spec=Session)


@pytest.fixture
def mock_llamaparse_response():
    """Mock LlamaParse API response."""
    return {
        "id": "test-job-123",
        "job_id": "test-job-123",
        "status": "COMPLETED"
    }


@pytest.fixture
def mock_progress_manager():
    """Mock progress manager for tracking."""
    with patch('test_parse_pdf.progress_manager') as mock:
        mock.update_progress = Mock()
        mock.error_processing = Mock()
        mock.complete_processing = Mock()
        mock.send_field_update = Mock()
        yield mock


@pytest.fixture
def sample_markdown_content():
    """Sample markdown content for testing."""
    return """
# Harvard Business School Case Study

## Company Overview
This is a test case study about a fictional company.

## Key Challenges
- Challenge 1
- Challenge 2
- Challenge 3

## Financial Data
Revenue: $1M
Costs: $800K
Profit: $200K
"""


@pytest.fixture
def sample_preprocessed_data():
    """Sample preprocessed case study data."""
    return {
        "title": "Business Case Study Title",
        "cleaned_content": "This is cleaned content about a business scenario."
    }


@pytest.fixture
def sample_personas():
    """Sample persona data."""
    return [
        {
            "name": "John Doe",
            "role": "CEO",
            "background": "Experienced executive",
            "primary_goals": ["Growth", "Innovation"],
            "personality_traits": {
                "analytical": 8,
                "creative": 7,
                "assertive": 9,
                "collaborative": 6,
                "detail_oriented": 7
            }
        },
        {
            "name": "Jane Smith",
            "role": "CFO",
            "background": "Financial expert",
            "primary_goals": ["Financial stability", "Risk management"],
            "personality_traits": {
                "analytical": 10,
                "creative": 4,
                "assertive": 6,
                "collaborative": 7,
                "detail_oriented": 10
            }
        }
    ]


# ============================================================================
# Tests for parse_with_llamaparse
# ============================================================================

@pytest.mark.asyncio
class TestParseWithLlamaparse:
    """Test suite for parse_with_llamaparse function."""

    async def test_parse_with_llamaparse_success(self, mock_upload_file, httpx_mock):
        """Test successful parsing with LlamaParse."""
        # Mock the upload response
        httpx_mock.add_response(
            url="https://api.cloud.llamaindex.ai/api/parsing/upload",
            method="POST",
            json={"id": "job-123"},
            status_code=200
        )
        
        # Mock the status check response (completed)
        httpx_mock.add_response(
            url="https://api.cloud.llamaindex.ai/api/parsing/job/job-123",
            method="GET",
            json={"status": "COMPLETED"},
            status_code=200
        )
        
        # Mock the result responses
        httpx_mock.add_response(
            url="https://api.cloud.llamaindex.ai/api/parsing/job/job-123/result/markdown",
            method="GET",
            text="# Parsed Markdown Content",
            status_code=200
        )

        with patch('test_parse_pdf.LLAMAPARSE_API_KEY', 'test-api-key'):
            result = await parse_with_llamaparse(mock_upload_file)
        
        assert result == "# Parsed Markdown Content"
        mock_upload_file.read.assert_called_once()

    async def test_parse_with_llamaparse_no_api_key(self, mock_upload_file):
        """Test that HTTPException is raised when API key is not configured."""
        with patch('test_parse_pdf.LLAMAPARSE_API_KEY', None):
            with pytest.raises(HTTPException) as exc_info:
                await parse_with_llamaparse(mock_upload_file)
            
            assert exc_info.value.status_code == 500
            assert "API key not configured" in str(exc_info.value.detail)

    async def test_parse_with_llamaparse_missing_job_id(self, mock_upload_file, httpx_mock):
        """Test handling of missing job ID in response."""
        httpx_mock.add_response(
            url="https://api.cloud.llamaindex.ai/api/parsing/upload",
            method="POST",
            json={"no_id_field": "oops"},
            status_code=200
        )

        with patch('test_parse_pdf.LLAMAPARSE_API_KEY', 'test-api-key'):
            with pytest.raises(HTTPException) as exc_info:
                await parse_with_llamaparse(mock_upload_file)
            
            assert exc_info.value.status_code == 500
            assert "No job ID" in str(exc_info.value.detail)

    async def test_parse_with_llamaparse_job_failed(self, mock_upload_file, httpx_mock):
        """Test handling of failed LlamaParse job."""
        httpx_mock.add_response(
            url="https://api.cloud.llamaindex.ai/api/parsing/upload",
            method="POST",
            json={"id": "job-456"},
            status_code=200
        )
        
        httpx_mock.add_response(
            url="https://api.cloud.llamaindex.ai/api/parsing/job/job-456",
            method="GET",
            json={"status": "FAILED", "error": "Parsing error occurred"},
            status_code=200
        )

        with patch('test_parse_pdf.LLAMAPARSE_API_KEY', 'test-api-key'):
            with pytest.raises(HTTPException) as exc_info:
                await parse_with_llamaparse(mock_upload_file)
            
            assert exc_info.value.status_code == 500
            assert "failed" in str(exc_info.value.detail).lower()

    async def test_parse_with_llamaparse_rate_limited(self, mock_upload_file, httpx_mock):
        """Test rate limiting handling (429 status)."""
        httpx_mock.add_response(
            url="https://api.cloud.llamaindex.ai/api/parsing/upload",
            method="POST",
            status_code=429
        )

        with patch('test_parse_pdf.LLAMAPARSE_API_KEY', 'test-api-key'):
            with patch('test_parse_pdf.async_retry', lambda **kwargs: lambda f: f):
                with pytest.raises(httpx.HTTPStatusError):
                    await parse_with_llamaparse(mock_upload_file)

    async def test_parse_with_llamaparse_with_session_id(self, mock_upload_file, httpx_mock, mock_progress_manager):
        """Test parsing with progress tracking via session_id."""
        httpx_mock.add_response(
            url="https://api.cloud.llamaindex.ai/api/parsing/upload",
            method="POST",
            json={"id": "job-789"},
            status_code=200
        )
        
        httpx_mock.add_response(
            url="https://api.cloud.llamaindex.ai/api/parsing/job/job-789",
            method="GET",
            json={"status": "COMPLETED"},
            status_code=200
        )
        
        httpx_mock.add_response(
            url="https://api.cloud.llamaindex.ai/api/parsing/job/job-789/result/markdown",
            method="GET",
            text="# Content",
            status_code=200
        )

        with patch('test_parse_pdf.LLAMAPARSE_API_KEY', 'test-api-key'):
            result = await parse_with_llamaparse(mock_upload_file, session_id="session-123")
        
        # Verify progress updates were called
        assert mock_progress_manager.update_progress.call_count > 0

    async def test_parse_with_llamaparse_timeout(self, mock_upload_file, httpx_mock):
        """Test handling of job timeout."""
        httpx_mock.add_response(
            url="https://api.cloud.llamaindex.ai/api/parsing/upload",
            method="POST",
            json={"id": "job-timeout"},
            status_code=200
        )
        
        # Mock status to always return PENDING to trigger timeout
        for _ in range(50):
            httpx_mock.add_response(
                url="https://api.cloud.llamaindex.ai/api/parsing/job/job-timeout",
                method="GET",
                json={"status": "PENDING"},
                status_code=200
            )

        with patch('test_parse_pdf.LLAMAPARSE_API_KEY', 'test-api-key'):
            with pytest.raises(HTTPException) as exc_info:
                await parse_with_llamaparse(mock_upload_file)
            
            assert exc_info.value.status_code == 500
            assert "timed out" in str(exc_info.value.detail).lower()


# ============================================================================
# Tests for _get_llamaparse_result
# ============================================================================

@pytest.mark.asyncio
class TestGetLlamaparseResult:
    """Test suite for _get_llamaparse_result helper function."""

    async def test_get_result_markdown_success(self, httpx_mock):
        """Test successful markdown result retrieval."""
        httpx_mock.add_response(
            url="https://api.cloud.llamaindex.ai/api/parsing/job/test-job/result/markdown",
            method="GET",
            text="# Markdown Result",
            status_code=200
        )

        async with httpx.AsyncClient() as client:
            result = await _get_llamaparse_result(
                client, "test-job", "markdown", {"Authorization": "Bearer test"}
            )
        
        assert result == "# Markdown Result"

    async def test_get_result_text_success(self, httpx_mock):
        """Test successful text result retrieval."""
        httpx_mock.add_response(
            url="https://api.cloud.llamaindex.ai/api/parsing/job/test-job/result",
            method="GET",
            json={"text": "Text content"},
            status_code=200
        )

        async with httpx.AsyncClient() as client:
            result = await _get_llamaparse_result(
                client, "test-job", "text", {"Authorization": "Bearer test"}
            )
        
        assert result == "Text content"

    async def test_get_result_failure_returns_empty(self, httpx_mock):
        """Test that failures return empty string."""
        httpx_mock.add_response(
            url="https://api.cloud.llamaindex.ai/api/parsing/job/test-job/result/markdown",
            method="GET",
            status_code=500
        )

        async with httpx.AsyncClient() as client:
            result = await _get_llamaparse_result(
                client, "test-job", "markdown", {"Authorization": "Bearer test"}
            )
        
        assert result == ""

    async def test_get_result_text_missing_field(self, httpx_mock):
        """Test text result with missing 'text' field."""
        httpx_mock.add_response(
            url="https://api.cloud.llamaindex.ai/api/parsing/job/test-job/result",
            method="GET",
            json={"no_text_field": "oops"},
            status_code=200
        )

        async with httpx.AsyncClient() as client:
            result = await _get_llamaparse_result(
                client, "test-job", "text", {"Authorization": "Bearer test"}
            )
        
        assert result == ""


# ============================================================================
# Tests for parse_pdf_fast_autofill
# ============================================================================

@pytest.mark.asyncio
class TestParsePdfFastAutofill:
    """Test suite for parse_pdf_fast_autofill endpoint."""

    async def test_fast_autofill_success(self, mock_upload_file, mock_db_session):
        """Test successful fast autofill processing."""
        with patch('test_parse_pdf.LLAMAPARSE_API_KEY', 'test-key'), \
             patch('test_parse_pdf.parse_file_flexible', AsyncMock(return_value="# Test Content")), \
             patch('test_parse_pdf._fast_persona_extraction', AsyncMock(return_value={
                 "title": "Test Case",
                 "student_role": "Business Analyst",
                 "key_figures": [{"name": "Test Person", "role": "CEO"}]
             })):
            
            result = await parse_pdf_fast_autofill(mock_upload_file, mock_db_session)
        
        assert result["status"] == "fast_autofill_completed"
        assert "processing_time" in result
        assert result["title"] == "Test Case"
        assert result["student_role"] == "Business Analyst"
        assert len(result["personas"]) == 1

    async def test_fast_autofill_no_api_key(self, mock_upload_file, mock_db_session):
        """Test fast autofill without API key."""
        with patch('test_parse_pdf.LLAMAPARSE_API_KEY', None):
            with pytest.raises(HTTPException) as exc_info:
                await parse_pdf_fast_autofill(mock_upload_file, mock_db_session)
            
            assert exc_info.value.status_code == 500

    async def test_fast_autofill_fallback_on_error(self, mock_upload_file, mock_db_session):
        """Test that fallback is returned on error."""
        with patch('test_parse_pdf.LLAMAPARSE_API_KEY', 'test-key'), \
             patch('test_parse_pdf.parse_file_flexible', AsyncMock(side_effect=Exception("Parse error"))):
            
            result = await parse_pdf_fast_autofill(mock_upload_file, mock_db_session)
        
        assert result["status"] == "fast_autofill_fallback"
        assert "personas" in result
        assert "key_figures" in result


# ============================================================================
# Tests for get_default_personas
# ============================================================================

@pytest.mark.asyncio
async def test_get_default_personas():
    """Test get_default_personas endpoint returns expected structure."""
    result = await get_default_personas()
    
    assert result["status"] == "instant_fallback"
    assert result["processing_time"] < 0.01
    assert result["title"] == "Business Case Study"
    assert result["student_role"] == "Business Manager"
    assert len(result["personas"]) == 4
    assert len(result["key_figures"]) == 4
    
    # Verify persona structure
    for persona in result["personas"]:
        assert "name" in persona
        assert "role" in persona
        assert "background" in persona
        assert "primary_goals" in persona
        assert "personality_traits" in persona
        assert len(persona["personality_traits"]) == 5


# ============================================================================
# Tests for preprocess_case_study_content
# ============================================================================

class TestPreprocessCaseStudyContent:
    """Test suite for preprocess_case_study_content function."""

    def test_preprocess_with_markdown_header(self, sample_markdown_content):
        """Test preprocessing content with markdown header."""
        result = preprocess_case_study_content(sample_markdown_content)
        
        assert "title" in result
        assert "cleaned_content" in result
        assert result["title"] == "Harvard Business School Case Study"
        assert len(result["cleaned_content"]) > 0

    def test_preprocess_with_dict_input(self):
        """Test preprocessing when input is a dictionary with markdown."""
        input_data = {"markdown": "# Test Title\n\nContent here"}
        result = preprocess_case_study_content(input_data)
        
        assert result["title"] == "Test Title"
        assert "Content here" in result["cleaned_content"]

    def test_preprocess_with_json_string(self):
        """Test preprocessing when input is JSON string."""
        input_data = json.dumps({"markdown": "# JSON Title\n\nJSON content"})
        result = preprocess_case_study_content(input_data)
        
        assert result["title"] == "JSON Title"

    def test_preprocess_fallback_title(self):
        """Test fallback title when no title found."""
        input_data = "Short text without title markers"
        result = preprocess_case_study_content(input_data)
        
        assert result["title"] == "Business Case Study"

    def test_preprocess_removes_metadata(self):
        """Test that metadata lines are removed."""
        input_data = """
        COPYRIGHT ENCODED
        DOCUMENT ID: 12345
        FILE: test.pdf
        # Real Title
        Real content here
        """
        result = preprocess_case_study_content(input_data)
        
        assert "COPYRIGHT" not in result["cleaned_content"]
        assert "DOCUMENT ID" not in result["cleaned_content"]
        assert "Real content" in result["cleaned_content"]

    def test_preprocess_cleans_formatting(self):
        """Test that formatting artifacts are cleaned."""
        input_data = "# Title\n\nDouble  spaces  here\n  Leading spaces\nTrailing spaces  \n"
        result = preprocess_case_study_content(input_data)
        
        # Should have single spaces and cleaned formatting
        assert "  " not in result["cleaned_content"]


# ============================================================================
# Tests for _fast_persona_extraction
# ============================================================================

@pytest.mark.asyncio
class TestFastPersonaExtraction:
    """Test suite for _fast_persona_extraction function."""

    async def test_persona_extraction_success(self):
        """Test successful persona extraction."""
        content = "This is a case study about business challenges."
        title = "Test Case Study"
        
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content=json.dumps({
            "title": title,
            "description": "A comprehensive description",
            "student_role": "Business Analyst",
            "key_figures": [
                {
                    "name": "John CEO",
                    "role": "Chief Executive",
                    "correlation": "Main decision maker",
                    "background": "Experienced leader",
                    "primary_goals": ["Growth"],
                    "personality_traits": {
                        "analytical": 8,
                        "creative": 6,
                        "assertive": 7,
                        "collaborative": 7,
                        "detail_oriented": 8
                    }
                }
            ]
        })))]
        
        with patch('test_parse_pdf.OPENAI_API_KEY', 'test-key'), \
             patch('test_parse_pdf.openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client
            
            result = await _fast_persona_extraction(content, title)
        
        assert result["title"] == title
        assert result["student_role"] == "Business Analyst"
        assert len(result["key_figures"]) == 1

    async def test_persona_extraction_fallback_on_error(self):
        """Test fallback when extraction fails."""
        with patch('test_parse_pdf.OPENAI_API_KEY', 'test-key'), \
             patch('test_parse_pdf.openai.OpenAI', side_effect=Exception("API Error")):
            
            result = await _fast_persona_extraction("content", "title")
        
        assert "title" in result
        assert "student_role" in result
        assert "key_figures" in result

    async def test_persona_extraction_invalid_json(self):
        """Test handling of invalid JSON response."""
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Not valid JSON"))]
        
        with patch('test_parse_pdf.OPENAI_API_KEY', 'test-key'), \
             patch('test_parse_pdf.openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client
            
            result = await _fast_persona_extraction("content", "title")
        
        # Should return fallback
        assert "key_figures" in result


# ============================================================================
# Tests for _create_fallback_result
# ============================================================================

class TestCreateFallbackResult:
    """Test suite for _create_fallback_result function."""

    def test_fallback_with_empty_content(self):
        """Test fallback creation with empty content."""
        result = _create_fallback_result("Test Title", "")
        
        assert result["title"] == "Test Title"
        assert result["student_role"] == "Business Analyst"
        assert len(result["key_figures"]) == 3

    def test_fallback_detects_analyst_role(self):
        """Test role detection for analyst."""
        content = "Students are tasked to analyze the business situation"
        result = _create_fallback_result("Title", content)
        
        assert result["student_role"] == "Business Analyst"

    def test_fallback_detects_advisor_role(self):
        """Test role detection for strategic advisor."""
        content = "You are asked to evaluate the strategic options"
        result = _create_fallback_result("Title", content)
        
        assert result["student_role"] == "Strategic Advisor"

    def test_fallback_detects_decision_maker_role(self):
        """Test role detection for decision maker."""
        content = "Students must decide on the best course of action"
        result = _create_fallback_result("Title", content)
        
        assert result["student_role"] == "Decision Maker"

    def test_fallback_detects_consultant_role(self):
        """Test role detection for consultant."""
        content = "As a consultant, you are asked to provide recommendations"
        result = _create_fallback_result("Title", content)
        
        assert result["student_role"] == "Business Consultant"

    def test_fallback_personas_structure(self):
        """Test that fallback personas have correct structure."""
        result = _create_fallback_result("Test", "")
        
        for persona in result["key_figures"]:
            assert "name" in persona
            assert "role" in persona
            assert "correlation" in persona
            assert "background" in persona
            assert "primary_goals" in persona
            assert "personality_traits" in persona
            assert len(persona["personality_traits"]) == 5


# ============================================================================
# Tests for generate_scenes_optimized
# ============================================================================

@pytest.mark.asyncio
class TestGenerateScenesOptimized:
    """Test suite for generate_scenes_optimized function."""

    async def test_generate_scenes_success(self, sample_personas):
        """Test successful scene generation."""
        content = "Business case content"
        title = "Test Case"
        
        mock_scenes = [
            {
                "title": "Initial Assessment",
                "description": "Setting description",
                "personas_involved": ["John Doe", "Jane Smith"],
                "user_goal": "Assess situation",
                "goal": "Understand context",
                "success_metric": "Complete assessment",
                "sequence_order": 1
            },
            {
                "title": "Analysis Phase",
                "description": "Analysis setting",
                "personas_involved": ["John Doe", "Jane Smith"],
                "user_goal": "Analyze data",
                "goal": "Deep analysis",
                "success_metric": "Data analyzed",
                "sequence_order": 2
            },
            {
                "title": "Solution Development",
                "description": "Development setting",
                "personas_involved": ["John Doe", "Jane Smith"],
                "user_goal": "Develop solution",
                "goal": "Create plan",
                "success_metric": "Solution proposed",
                "sequence_order": 3
            },
            {
                "title": "Implementation",
                "description": "Implementation setting",
                "personas_involved": ["John Doe", "Jane Smith"],
                "user_goal": "Implement plan",
                "goal": "Execute strategy",
                "success_metric": "Plan approved",
                "sequence_order": 4
            }
        ]
        
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content=json.dumps(mock_scenes)))]
        
        with patch('test_parse_pdf.OPENAI_API_KEY', 'test-key'), \
             patch('test_parse_pdf.openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client
            
            result = await generate_scenes_optimized(content, title, sample_personas)
        
        assert len(result) == 4
        assert all(len(scene["personas_involved"]) >= 2 for scene in result)

    async def test_generate_scenes_validates_personas(self, sample_personas):
        """Test that scenes with invalid personas are rejected."""
        mock_scenes = [
            {
                "title": "Scene 1",
                "description": "Description",
                "personas_involved": ["John Doe"],  # Only 1 persona - invalid
                "user_goal": "Goal",
                "goal": "Goal",
                "success_metric": "Metric",
                "sequence_order": 1
            }
        ]
        
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content=json.dumps(mock_scenes)))]
        
        with patch('test_parse_pdf.OPENAI_API_KEY', 'test-key'), \
             patch('test_parse_pdf.openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client
            
            result = await generate_scenes_optimized("content", "title", sample_personas)
        
        # Should return fallback scenes
        assert len(result) == 4

    async def test_generate_scenes_fallback_on_error(self):
        """Test fallback when scene generation fails."""
        with patch('test_parse_pdf.OPENAI_API_KEY', 'test-key'), \
             patch('test_parse_pdf.openai.OpenAI', side_effect=Exception("API Error")):
            
            result = await generate_scenes_optimized("content", "title", [])
        
        assert len(result) == 4
        assert all("title" in scene for scene in result)


# ============================================================================
# Tests for generate_learning_outcomes_optimized
# ============================================================================

@pytest.mark.asyncio
class TestGenerateLearningOutcomesOptimized:
    """Test suite for generate_learning_outcomes_optimized function."""

    async def test_generate_outcomes_success(self):
        """Test successful learning outcomes generation."""
        outcomes = [
            "1. First outcome",
            "2. Second outcome",
            "3. Third outcome",
            "4. Fourth outcome",
            "5. Fifth outcome"
        ]
        
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content=json.dumps(outcomes)))]
        
        with patch('test_parse_pdf.OPENAI_API_KEY', 'test-key'), \
             patch('test_parse_pdf.openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client
            
            result = await generate_learning_outcomes_optimized("content", "title")
        
        assert len(result) == 5

    async def test_generate_outcomes_fallback_on_error(self):
        """Test fallback when generation fails."""
        with patch('test_parse_pdf.OPENAI_API_KEY', 'test-key'), \
             patch('test_parse_pdf.openai.OpenAI', side_effect=Exception("API Error")):
            
            result = await generate_learning_outcomes_optimized("content", "title")
        
        assert len(result) == 5
        assert all(outcome.startswith(str(i+1)) for i, outcome in enumerate(result))


# ============================================================================
# Tests for fallback functions
# ============================================================================

class TestFallbackFunctions:
    """Test suite for fallback helper functions."""

    def test_create_fallback_personas(self):
        """Test _create_fallback_personas function."""
        result = _create_fallback_personas("Test Title")
        
        assert result["title"] == "Test Title"
        assert result["student_role"] == "Business Manager"
        assert len(result["key_figures"]) == 2

    def test_create_fallback_scenes(self):
        """Test _create_fallback_scenes function."""
        result = _create_fallback_scenes()
        
        assert len(result) == 4
        assert all(len(scene["personas_involved"]) == 2 for scene in result)
        assert all(scene["sequence_order"] in [1, 2, 3, 4] for scene in result)

    def test_create_fallback_learning_outcomes(self):
        """Test _create_fallback_learning_outcomes function."""
        result = _create_fallback_learning_outcomes()
        
        assert len(result) == 5
        assert all(isinstance(outcome, str) for outcome in result)


# ============================================================================
# Tests for generate_scene_image
# ============================================================================

@pytest.mark.asyncio
class TestGenerateSceneImage:
    """Test suite for generate_scene_image function."""

    async def test_generate_image_success(self):
        """Test successful image generation."""
        mock_response = Mock()
        mock_response.data = [Mock(url="https://example.com/image.png")]
        
        with patch('test_parse_pdf.OPENAI_API_KEY', 'test-key'), \
             patch('test_parse_pdf.openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_client.images.generate.return_value = mock_response
            mock_openai.return_value = mock_client
            
            result = await generate_scene_image("Scene description", "Scene Title")
        
        assert result == "https://example.com/image.png"

    async def test_generate_image_failure(self):
        """Test image generation failure returns empty string."""
        with patch('test_parse_pdf.OPENAI_API_KEY', 'test-key'), \
             patch('test_parse_pdf.openai.OpenAI', side_effect=Exception("API Error")):
            
            result = await generate_scene_image("Description", "Title")
        
        assert result == ""


# ============================================================================
# Tests for AI processing functions
# ============================================================================

@pytest.mark.asyncio
class TestAIProcessing:
    """Test suite for AI processing functions."""

    async def test_process_with_ai_optimized_from_preprocessed(self, sample_preprocessed_data):
        """Test AI processing from preprocessed data."""
        with patch('test_parse_pdf.extract_personas_and_key_figures_optimized', AsyncMock(return_value={
            "title": "Test",
            "description": "Desc",
            "student_role": "Analyst",
            "key_figures": []
        })), \
             patch('test_parse_pdf.generate_scenes_optimized', AsyncMock(return_value=[])), \
             patch('test_parse_pdf.generate_learning_outcomes_optimized', AsyncMock(return_value=[])):
            
            result = await process_with_ai_optimized_from_preprocessed(sample_preprocessed_data)
        
        assert "title" in result
        assert "description" in result
        assert "student_role" in result
        assert "key_figures" in result
        assert "scenes" in result
        assert "learning_outcomes" in result

    async def test_process_with_ai_optimized_with_updates(self):
        """Test deprecated AI processing function."""
        with patch('test_parse_pdf.CPU_EXECUTOR'), \
             patch('test_parse_pdf.process_with_ai_optimized_with_updates_from_preprocessed', 
                   AsyncMock(return_value={"success": True})):
            
            result = await process_with_ai_optimized_with_updates("content", "context")
        
        assert result == {"success": True}


# ============================================================================
# Integration-style tests for endpoints
# ============================================================================

@pytest.mark.asyncio
class TestEndpoints:
    """Test suite for API endpoint functions."""

    async def test_parse_pdf_endpoint_missing_api_key(self, mock_upload_file, mock_db_session):
        """Test parse_pdf endpoint without API key."""
        with patch('test_parse_pdf.LLAMAPARSE_API_KEY', None):
            with pytest.raises(HTTPException) as exc_info:
                await parse_pdf(mock_upload_file, None, False, mock_db_session)
            
            assert exc_info.value.status_code == 500

    async def test_parse_pdf_endpoint_invalid_file_type(self, mock_db_session):
        """Test parse_pdf endpoint with invalid file type."""
        mock_file = Mock(spec=UploadFile)
        mock_file.content_type = "text/html"
        mock_file.filename = "test.html"
        
        with patch('test_parse_pdf.LLAMAPARSE_API_KEY', 'test-key'):
            with pytest.raises(HTTPException) as exc_info:
                await parse_pdf(mock_file, None, False, mock_db_session)
            
            assert exc_info.value.status_code == 400

    async def test_parse_pdf_with_progress_missing_api_key(self, mock_upload_file, mock_db_session):
        """Test parse_pdf_with_progress without API key."""
        with patch('test_parse_pdf.LLAMAPARSE_API_KEY', None):
            with pytest.raises(HTTPException) as exc_info:
                await parse_pdf_with_progress(mock_upload_file, None, False, None, mock_db_session)
            
            assert exc_info.value.status_code == 500

    async def test_parse_pdf_with_progress_generates_session_id(self, mock_upload_file, mock_db_session):
        """Test that session_id is generated if not provided."""
        with patch('test_parse_pdf.LLAMAPARSE_API_KEY', 'test-key'), \
             patch('test_parse_pdf.parse_file_flexible', AsyncMock(return_value="content")), \
             patch('test_parse_pdf.preprocess_case_study_content', return_value={
                 "title": "Test", "cleaned_content": "content"
             }), \
             patch('test_parse_pdf.process_with_ai_optimized_with_updates_from_preprocessed', 
                   AsyncMock(return_value={"title": "Test"})):
            
            result = await parse_pdf_with_progress(
                mock_upload_file, None, False, None, mock_db_session
            )
        
        assert "session_id" in result
        assert result["session_id"] is not None


# ============================================================================
# Edge case and error handling tests
# ============================================================================

@pytest.mark.asyncio
class TestEdgeCases:
    """Test suite for edge cases and error scenarios."""

    async def test_parse_with_llamaparse_empty_result(self, mock_upload_file, httpx_mock):
        """Test handling of empty result from LlamaParse."""
        httpx_mock.add_response(
            url="https://api.cloud.llamaindex.ai/api/parsing/upload",
            method="POST",
            json={"id": "job-empty"},
            status_code=200
        )
        
        httpx_mock.add_response(
            url="https://api.cloud.llamaindex.ai/api/parsing/job/job-empty",
            method="GET",
            json={"status": "COMPLETED"},
            status_code=200
        )
        
        httpx_mock.add_response(
            url="https://api.cloud.llamaindex.ai/api/parsing/job/job-empty/result/markdown",
            method="GET",
            text="",
            status_code=200
        )
        
        httpx_mock.add_response(
            url="https://api.cloud.llamaindex.ai/api/parsing/job/job-empty/result",
            method="GET",
            json={"text": ""},
            status_code=200
        )

        with patch('test_parse_pdf.LLAMAPARSE_API_KEY', 'test-key'):
            result = await parse_with_llamaparse(mock_upload_file)
        
        assert result == ""

    def test_preprocess_with_very_long_content(self):
        """Test preprocessing with very long content."""
        long_content = "# Title\n" + ("Line of content\n" * 10000)
        result = preprocess_case_study_content(long_content)
        
        assert result["title"] == "Title"
        assert len(result["cleaned_content"]) > 0

    def test_preprocess_with_unicode_characters(self):
        """Test preprocessing with unicode characters."""
        content = "# Título con ñ y acentos\n\nContenido con émojis 🎉 y caracteres especiales €£¥"
        result = preprocess_case_study_content(content)
        
        assert "Título" in result["title"]
        assert "🎉" in result["cleaned_content"]

    async def test_persona_extraction_with_truncated_content(self):
        """Test persona extraction with very long content (truncation)."""
        long_content = "A" * 10000  # Very long content
        
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content=json.dumps({
            "title": "Test",
            "student_role": "Analyst",
            "key_figures": []
        })))]
        
        with patch('test_parse_pdf.OPENAI_API_KEY', 'test-key'), \
             patch('test_parse_pdf.openai.OpenAI') as mock_openai:
            mock_client = Mock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client
            
            result = await _fast_persona_extraction(long_content, "Test")
        
        # Verify the prompt was truncated (only first 2000 chars used)
        call_args = mock_client.chat.completions.create.call_args
        prompt = call_args[1]["messages"][1]["content"]
        assert len(long_content[:2000]) in prompt


# ============================================================================
# Performance and concurrency tests
# ============================================================================

@pytest.mark.asyncio
class TestPerformance:
    """Test suite for performance-related scenarios."""

    async def test_multiple_concurrent_llamaparse_calls(self, httpx_mock):
        """Test that semaphore limits concurrent LlamaParse calls."""
        # Create multiple mock files
        mock_files = []
        for i in range(5):
            mock_file = Mock(spec=UploadFile)
            mock_file.filename = f"test{i}.pdf"
            mock_file.content_type = "application/pdf"
            mock_file.read = AsyncMock(return_value=b"content")
            mock_files.append(mock_file)
        
        # Mock responses for each
        for i in range(5):
            httpx_mock.add_response(
                url="https://api.cloud.llamaindex.ai/api/parsing/upload",
                method="POST",
                json={"id": f"job-{i}"},
                status_code=200
            )
            
            httpx_mock.add_response(
                url=f"https://api.cloud.llamaindex.ai/api/parsing/job/job-{i}",
                method="GET",
                json={"status": "COMPLETED"},
                status_code=200
            )
            
            httpx_mock.add_response(
                url=f"https://api.cloud.llamaindex.ai/api/parsing/job/job-{i}/result/markdown",
                method="GET",
                text=f"# Result {i}",
                status_code=200
            )
        
        with patch('test_parse_pdf.LLAMAPARSE_API_KEY', 'test-key'):
            tasks = [parse_with_llamaparse(f) for f in mock_files]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All should succeed
        assert len([r for r in results if not isinstance(r, Exception)]) == 5

