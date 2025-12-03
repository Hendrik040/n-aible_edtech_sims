"""
Tests for image generation service.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from modules.pdf_processing.image_generation_service import (
    generate_scene_image,
    generate_scenes_with_images,
    generate_personas_with_avatars,
    _generate_persona_avatar_unsafe,
    OPENAI_API_KEY,
    FREEPIK_API_KEY
)


@pytest.fixture
def mock_openai_response():
    """Create a mock OpenAI response"""
    mock_response = Mock()
    mock_data = Mock()
    mock_data.url = "https://oaidalleapiprodscus.blob.core.windows.net/test-image.jpg"
    mock_response.data = [mock_data]
    return mock_response


@pytest.fixture
def mock_settings(monkeypatch):
    """Mock settings with API keys"""
    monkeypatch.setattr('modules.pdf_processing.image_generation_service.OPENAI_API_KEY', 'test-openai-key')
    monkeypatch.setattr('modules.pdf_processing.image_generation_service.FREEPIK_API_KEY', 'test-freepik-key')


@pytest.mark.asyncio
async def test_generate_scene_image_success(mock_settings, mock_openai_response):
    """Test successful scene image generation"""
    with patch('openai.OpenAI') as mock_openai:
        mock_client = Mock()
        mock_client.images.generate = Mock(return_value=mock_openai_response)
        mock_openai.return_value = mock_client
        
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=mock_openai_response)
            
            result = await generate_scene_image(
                scene_description="A business meeting room",
                scene_title="Team Meeting",
                scenario_id=1,
                scene_id=100
            )
            
            assert result == "https://oaidalleapiprodscus.blob.core.windows.net/test-image.jpg"


@pytest.mark.asyncio
async def test_generate_scene_image_no_api_key(monkeypatch):
    """Test scene image generation fails gracefully when API key is missing"""
    monkeypatch.setattr('modules.pdf_processing.image_generation_service.OPENAI_API_KEY', None)
    
    result = await generate_scene_image(
        scene_description="A business meeting room",
        scene_title="Team Meeting"
    )
    
    assert result == ""


@pytest.mark.asyncio
async def test_generate_scene_image_openai_error(mock_settings):
    """Test scene image generation handles OpenAI errors gracefully"""
    with patch('openai.OpenAI') as mock_openai:
        mock_client = Mock()
        mock_client.images.generate = Mock(side_effect=Exception("API Error"))
        mock_openai.return_value = mock_client
        
        with patch('asyncio.get_event_loop') as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(side_effect=Exception("API Error"))
            
            result = await generate_scene_image(
                scene_description="A business meeting room",
                scene_title="Team Meeting"
            )
            
            assert result == ""


@pytest.mark.asyncio
async def test_generate_scenes_with_images(mock_settings, mock_openai_response):
    """Test generating images for multiple scenes"""
    scenes = [
        {"title": "Scene 1", "description": "First scene", "id": 1},
        {"title": "Scene 2", "description": "Second scene", "id": 2}
    ]
    
    with patch('modules.pdf_processing.image_generation_service.generate_scene_image') as mock_generate:
        mock_generate.return_value = "https://example.com/image.jpg"
        
        result = await generate_scenes_with_images(scenes, scenario_id=1)
        
        assert len(result) == 2
        assert result[0]["image_url"] == "https://example.com/image.jpg"
        assert result[1]["image_url"] == "https://example.com/image.jpg"
        assert mock_generate.call_count == 2


@pytest.mark.asyncio
async def test_generate_scenes_with_images_empty_list():
    """Test generating images for empty scene list"""
    result = await generate_scenes_with_images([])
    assert result == []


@pytest.mark.asyncio
async def test_generate_scenes_with_images_invalid_scenes():
    """Test generating images handles invalid scene data"""
    scenes = [
        {"invalid": "data"},
        {"title": "Valid Scene", "description": "Description"}
    ]
    
    with patch('modules.pdf_processing.image_generation_service.generate_scene_image') as mock_generate:
        mock_generate.return_value = "https://example.com/image.jpg"
        
        result = await generate_scenes_with_images(scenes)
        
        assert len(result) == 2
        # Invalid scene should have empty image_url
        assert result[0].get("image_url") == ""
        # Valid scene should have image URL
        assert result[1]["image_url"] == "https://example.com/image.jpg"


@pytest.mark.asyncio
async def test_generate_personas_with_avatars_empty_list():
    """Test generating avatars for empty persona list"""
    result = await generate_personas_with_avatars([])
    assert result == []


@pytest.mark.asyncio
async def test_generate_personas_with_avatars_no_api_key(monkeypatch):
    """Test persona avatar generation fails gracefully when API key is missing"""
    monkeypatch.setattr('modules.pdf_processing.image_generation_service.FREEPIK_API_KEY', None)
    
    personas = [
        {"name": "John Doe", "role": "CEO", "background": "Experienced leader"}
    ]
    
    result = await generate_personas_with_avatars(personas)
    
    assert len(result) == 1
    assert result[0].get("image_url") == ""


@pytest.mark.asyncio
async def test_generate_persona_avatar_unsafe_success(mock_settings):
    """Test successful persona avatar generation"""
    # Create a simple response class that mimics httpx.Response
    class MockResponse:
        def __init__(self, status_code, json_data, headers=None):
            self.status_code = status_code
            self._json_data = json_data
            self.headers = headers or {}
        
        def json(self):
            return self._json_data
    
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Create proper dict responses
        create_response = MockResponse(200, {
            "data": {
                "task_id": "test-task-123"
            }
        })
        
        pending_response = MockResponse(200, {
            "data": {
                "status": "PROCESSING"
            }
        })
        
        complete_response = MockResponse(200, {
            "data": {
                "status": "COMPLETED",
                "generated": ["https://cdn-magnific.freepik.com/test-avatar.jpg"]
            }
        })
        
        mock_client.post = AsyncMock(return_value=create_response)
        mock_client.get = AsyncMock(side_effect=[
            pending_response,
            complete_response
        ])
        
        # Mock asyncio.sleep to speed up the test (skip the wait time)
        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await _generate_persona_avatar_unsafe(
                persona_name="John Doe",
                persona_role="CEO",
                background="Experienced leader"
            )
        
        assert result == "https://cdn-magnific.freepik.com/test-avatar.jpg"


@pytest.mark.asyncio
async def test_generate_persona_avatar_unsafe_no_api_key(monkeypatch):
    """Test persona avatar generation fails when API key is missing"""
    monkeypatch.setattr('modules.pdf_processing.image_generation_service.FREEPIK_API_KEY', None)
    
    result = await _generate_persona_avatar_unsafe(
        persona_name="John Doe",
        persona_role="CEO"
    )
    
    assert result == ""


@pytest.mark.asyncio
async def test_generate_personas_with_avatars_success(mock_settings):
    """Test generating avatars for multiple personas"""
    personas = [
        {"name": "John Doe", "role": "CEO", "background": "Experienced leader", "id": 1},
        {"name": "Jane Smith", "role": "CFO", "background": "Financial expert", "id": 2}
    ]
    
    with patch('modules.pdf_processing.image_generation_service._generate_persona_avatar_unsafe') as mock_generate:
        mock_generate.return_value = "https://cdn-magnific.freepik.com/avatar.jpg"
        
        result = await generate_personas_with_avatars(personas)
        
        assert len(result) == 2
        assert result[0]["image_url"] == "https://cdn-magnific.freepik.com/avatar.jpg"
        assert result[1]["image_url"] == "https://cdn-magnific.freepik.com/avatar.jpg"
        assert result[0]["avatar_url"] == "https://cdn-magnific.freepik.com/avatar.jpg"  # Backwards compatibility


@pytest.mark.asyncio
async def test_generate_personas_with_avatars_invalid_personas():
    """Test generating avatars handles invalid persona data"""
    personas = [
        {"invalid": "data"},
        {"name": "John Doe", "role": "CEO"}
    ]
    
    with patch('modules.pdf_processing.image_generation_service._generate_persona_avatar_unsafe') as mock_generate:
        mock_generate.return_value = "https://cdn-magnific.freepik.com/avatar.jpg"
        
        result = await generate_personas_with_avatars(personas)
        
        assert len(result) == 2
        # Invalid persona should have empty image_url
        assert result[0].get("image_url") == ""
        # Valid persona should have image URL
        assert result[1]["image_url"] == "https://cdn-magnific.freepik.com/avatar.jpg"


@pytest.mark.asyncio
async def test_generate_personas_with_avatars_api_error(mock_settings):
    """Test generating avatars handles API errors gracefully"""
    personas = [
        {"name": "John Doe", "role": "CEO"}
    ]
    
    with patch('modules.pdf_processing.image_generation_service._generate_persona_avatar_unsafe') as mock_generate:
        mock_generate.return_value = ""  # Empty string on error
        
        result = await generate_personas_with_avatars(personas)
        
        assert len(result) == 1
        assert result[0]["image_url"] == ""

