"""
Tests for AI extraction service with mocked OpenAI.
"""
import pytest
import json
from unittest.mock import Mock, patch, AsyncMock

from modules.pdf_processing.ai_extraction_service import AIExtractionService


@pytest.fixture
def ai_service():
    """Create an AI extraction service instance"""
    with patch('modules.pdf_processing.ai_extraction_service.OPENAI_API_KEY', 'test-api-key'):
        service = AIExtractionService()
        return service


@pytest.fixture
def mock_openai_response():
    """Create a mock OpenAI response"""
    mock_response = Mock()
    mock_choice = Mock()
    mock_message = Mock()
    mock_message.content = json.dumps({
        "title": "Test Business Case",
        "description": "A comprehensive test case study",
        "student_role": "Business Analyst",
        "key_figures": [
            {
                "name": "John Doe",
                "role": "CEO",
                "correlation": "Main character",
                "background": "Experienced executive",
                "primary_goals": ["Goal 1", "Goal 2"],
                "personality_traits": {
                    "analytical": 8,
                    "creative": 6,
                    "assertive": 7,
                    "collaborative": 7,
                    "detail_oriented": 8
                }
            }
        ]
    })
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]
    return mock_response


def test_preprocess_content_with_title(ai_service):
    """Test content preprocessing with clear title"""
    raw_content = "# Business Case Title\n\nContent here\nMore content"
    
    result = ai_service.preprocess_content(raw_content)
    
    assert result["title"] == "Business Case Title"
    assert "Content here" in result["cleaned_content"]


def test_preprocess_content_without_title(ai_service):
    """Test content preprocessing without clear title"""
    raw_content = "Some content without a clear title\nMore content here"
    
    result = ai_service.preprocess_content(raw_content)
    
    assert result["title"] is not None
    assert len(result["cleaned_content"]) > 0


@pytest.mark.asyncio
async def test_extract_personas_fast_success(ai_service, mock_openai_response):
    """Test fast persona extraction"""
    content = "Business case content here"
    title = "Test Case"
    
    with patch.object(ai_service.client.chat.completions, 'create', return_value=mock_openai_response):
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_executor = Mock()
            mock_executor.return_value = mock_openai_response
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=mock_openai_response)
            
            result = await ai_service.extract_personas_fast(content, title)
            
            assert result["title"] == "Test Business Case"
            assert result["student_role"] == "Business Analyst"
            assert len(result["key_figures"]) == 1


@pytest.mark.asyncio
async def test_extract_personas_and_key_figures_empty_content(ai_service):
    """Test persona extraction with empty content"""
    content = ""
    title = "Test Case"
    
    with pytest.raises(ValueError) as exc_info:
        await ai_service.extract_personas_and_key_figures(content, title)
    
    assert "empty" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_extract_personas_filters_student_role_from_key_figures(ai_service):
    """Ensure the student/protagonist is filtered from NPC personas."""
    content = "Business case content here"
    title = "Test Case"

    mock_response = Mock()
    mock_choice = Mock()
    mock_message = Mock()
    mock_message.content = json.dumps({
        "title": "Test Business Case",
        "description": "A comprehensive test case study",
        "student_role": "Jane Smith (CEO)",
        "key_figures": [
            {"name": "Jane Smith", "role": "CEO", "correlation": "Protagonist", "background": "Executive leader"},
            {"name": "Board Chair", "role": "Board Chair", "correlation": "Oversight", "background": "Leads board decisions"},
            {"name": "Flagged Figure", "role": "Advisor", "is_main_character": True}
        ]
    })
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]

    with patch.object(ai_service.client.chat.completions, "create", return_value=mock_response):
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=mock_response)

            result = await ai_service.extract_personas_and_key_figures(content, title)

    assert result["student_role"] == "Jane Smith (CEO)"
    assert len(result["key_figures"]) == 1
    assert result["key_figures"][0]["name"] == "Board Chair"


@pytest.mark.asyncio
async def test_generate_scenes_success(ai_service):
    """Test scene generation"""
    content = "Business case content"
    title = "Test Case"
    personas_result = {
        "key_figures": [{"name": "John Doe", "role": "CEO"}],
        "student_role": "Business Analyst"
    }
    
    mock_response = Mock()
    mock_choice = Mock()
    mock_message = Mock()
    mock_message.content = json.dumps([
        {
            "title": "Scene 1",
            "description": "First scene",
            "personas_involved": ["John Doe"],
            "user_goal": "Complete task",
            "goal": "General goal",
            "success_metric": "Success criteria",
            "sequence_order": 1
        }
    ])
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]
    
    with patch.object(ai_service.client.chat.completions, 'create', return_value=mock_response):
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=mock_response)
            
            result = await ai_service.generate_scenes(content, title, None, personas_result)
            
            assert len(result) == 1
            assert result[0]["title"] == "Scene 1"


@pytest.mark.asyncio
async def test_generate_learning_outcomes_success(ai_service):
    """Test learning outcomes generation"""
    content = "Business case content"
    title = "Test Case"
    
    mock_response = Mock()
    mock_choice = Mock()
    mock_message = Mock()
    mock_message.content = json.dumps([
        "1. First outcome",
        "2. Second outcome",
        "3. Third outcome",
        "4. Fourth outcome",
        "5. Fifth outcome"
    ])
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]
    
    with patch.object(ai_service.client.chat.completions, 'create', return_value=mock_response):
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=mock_response)
            
            result = await ai_service.generate_learning_outcomes(content, title)
            
            assert len(result) == 5
            assert "First outcome" in result[0]
