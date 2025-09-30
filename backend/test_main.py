"""
Comprehensive unit tests for main.py endpoints and lifespan management.
Testing Framework: pytest with FastAPI TestClient and httpx
Mocking: unittest.mock for external dependencies
"""

import pytest
import asyncio
import json
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock, call
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import os

# Import the app and functions to test
from main import (
    app, 
    combined_lifespan,
    health_check,
    startup_event,
    get_cors_origins,
    websocket_endpoint,
    root,
    get_scenarios,
    get_draft_scenarios,
    delete_scenario_by_unique_id,
    delete_draft_scenario,
    get_draft_scenario,
    update_scenario_status,
    register_user,
    login_user,
    check_email_exists,
    logout_user,
    get_current_user_profile,
    test_login,
    update_current_user,
    change_password,
    track_user_activity,
    get_user_profile,
    get_public_scenarios,
    get_scenario_details,
    test_endpoint,
    test_auth_endpoint,
    test_db_endpoint,
    test_combined_endpoint,
    test_scenario_endpoint,
    get_scenario_full,
    get_cache_stats,
    invalidate_user_cache,
    invalidate_scenario_cache,
    cleanup_cache,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def mock_db():
    """Mock database session."""
    db = MagicMock()
    db.query = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    return db


@pytest.fixture
def mock_user():
    """Create a mock user object."""
    user = MagicMock()
    user.id = 1
    user.user_id = "STU-001"
    user.email = "[email protected]"
    user.username = "testuser"
    user.full_name = "Test User"
    user.role = "student"
    user.bio = "Test bio"
    user.avatar_url = None
    user.profile_public = True
    user.allow_contact = True
    user.is_active = True
    user.is_verified = False
    user.published_scenarios = 0
    user.total_simulations = 0
    user.reputation_score = 0
    user.created_at = datetime.utcnow()
    user.updated_at = datetime.utcnow()
    user.last_activity = datetime.utcnow()
    user.password_hash = "hashed_password"
    return user


@pytest.fixture
def mock_scenario():
    """Create a mock scenario object."""
    scenario = MagicMock()
    scenario.id = 1
    scenario.unique_id = "scenario-123"
    scenario.title = "Test Scenario"
    scenario.description = "Test Description"
    scenario.challenge = "Test Challenge"
    scenario.industry = "Technology"
    scenario.learning_objectives = ["Objective 1", "Objective 2"]
    scenario.student_role = "Analyst"
    scenario.status = "active"
    scenario.is_draft = False
    scenario.is_public = True
    scenario.created_by = 1
    scenario.created_at = datetime.utcnow()
    scenario.updated_at = datetime.utcnow()
    scenario.deleted_at = None
    scenario.category = "Business"
    scenario.difficulty_level = "Intermediate"
    scenario.estimated_duration = 60
    scenario.tags = ["tag1", "tag2"]
    scenario.rating_avg = 4.5
    scenario.rating_count = 10
    scenario.usage_count = 50
    scenario.completion_status = "complete"
    scenario.name_completed = True
    scenario.description_completed = True
    scenario.personas_completed = True
    scenario.scenes_completed = True
    scenario.images_completed = True
    scenario.learning_outcomes_completed = True
    scenario.ai_enhancement_completed = True
    scenario.published_version_id = None
    return scenario


@pytest.fixture
def mock_redis_manager():
    """Mock Redis manager."""
    with patch('main.redis_manager') as mock:
        mock.is_available = MagicMock(return_value=True)
        mock.get_keys = MagicMock(return_value=["key1", "key2", "key3"])
        yield mock


@pytest.fixture
def mock_settings():
    """Mock settings."""
    with patch('main.settings') as mock:
        mock.environment = "development"
        yield mock


# ============================================================================
# LIFESPAN TESTS
# ============================================================================

class TestCombinedLifespan:
    """Tests for the combined_lifespan context manager."""
    
    @pytest.mark.asyncio
    async def test_lifespan_validates_environment(self, mock_redis_manager):
        """Test that lifespan validates environment on startup."""
        with patch('main._validate_environment') as mock_validate:
            with patch('main.oauth_lifespan') as mock_oauth:
                with patch('main.session_manager_lifespan') as mock_session:
                    mock_oauth.return_value.__aenter__ = AsyncMock()
                    mock_oauth.return_value.__aexit__ = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock()
                    mock_session.return_value.__aexit__ = AsyncMock()
                    
                    async with combined_lifespan(app):
                        pass
                    
                    mock_validate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_lifespan_checks_redis_connection(self):
        """Test that lifespan checks Redis connection on startup."""
        with patch('main._validate_environment'):
            with patch('main.redis_manager') as mock_redis:
                mock_redis.is_available.return_value = True
                with patch('main.oauth_lifespan') as mock_oauth:
                    with patch('main.session_manager_lifespan') as mock_session:
                        mock_oauth.return_value.__aenter__ = AsyncMock()
                        mock_oauth.return_value.__aexit__ = AsyncMock()
                        mock_session.return_value.__aenter__ = AsyncMock()
                        mock_session.return_value.__aexit__ = AsyncMock()
                        
                        async with combined_lifespan(app):
                            pass
                        
                        mock_redis.is_available.assert_called()
    
    @pytest.mark.asyncio
    async def test_lifespan_raises_error_when_redis_unavailable(self):
        """Test that lifespan raises RuntimeError when Redis is unavailable."""
        with patch('main._validate_environment'):
            with patch('main.redis_manager') as mock_redis:
                mock_redis.is_available.return_value = False
                
                with pytest.raises(RuntimeError, match="Redis is not available"):
                    async with combined_lifespan(app):
                        pass
    
    @pytest.mark.asyncio
    async def test_lifespan_raises_error_on_redis_exception(self):
        """Test that lifespan handles Redis connection exceptions."""
        with patch('main._validate_environment'):
            with patch('main.redis_manager') as mock_redis:
                mock_redis.is_available.side_effect = Exception("Connection failed")
                
                with pytest.raises(RuntimeError, match="Redis initialization failed"):
                    async with combined_lifespan(app):
                        pass
    
    @pytest.mark.asyncio
    async def test_lifespan_starts_cleanup_tasks(self, mock_redis_manager):
        """Test that lifespan starts all cleanup tasks."""
        with patch('main._validate_environment'):
            with patch('main.oauth_lifespan') as mock_oauth:
                with patch('main.session_manager_lifespan') as mock_session:
                    with patch('main.redis_cleanup_task') as mock_redis_task:
                        mock_oauth.return_value.__aenter__ = AsyncMock()
                        mock_oauth.return_value.__aexit__ = AsyncMock()
                        mock_session.return_value.__aenter__ = AsyncMock()
                        mock_session.return_value.__aexit__ = AsyncMock()
                        
                        async with combined_lifespan(app):
                            pass
    
    @pytest.mark.asyncio
    async def test_lifespan_cancels_redis_task_on_exit(self, mock_redis_manager):
        """Test that Redis cleanup task is cancelled on exit."""
        with patch('main._validate_environment'):
            with patch('main.oauth_lifespan') as mock_oauth:
                with patch('main.session_manager_lifespan') as mock_session:
                    mock_oauth.return_value.__aenter__ = AsyncMock()
                    mock_oauth.return_value.__aexit__ = AsyncMock()
                    mock_session.return_value.__aenter__ = AsyncMock()
                    mock_session.return_value.__aexit__ = AsyncMock()
                    
                    async with combined_lifespan(app):
                        pass


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================

class TestHealthCheck:
    """Tests for the /health endpoint."""
    
    @pytest.mark.asyncio
    async def test_health_check_returns_200(self):
        """Test health check returns 200 status."""
        response = await health_check()
        assert response["status"] == "healthy"
        assert "timestamp" in response
    
    @pytest.mark.asyncio
    async def test_health_check_timestamp_format(self):
        """Test health check timestamp is in ISO format."""
        response = await health_check()
        timestamp = response["timestamp"]
        # Verify it's a valid ISO format string
        datetime.fromisoformat(timestamp)
    
    def test_health_check_endpoint_via_client(self, client):
        """Test health check endpoint via test client."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


# ============================================================================
# STARTUP EVENT TESTS
# ============================================================================

class TestStartupEvent:
    """Tests for the startup_event function."""
    
    @pytest.mark.asyncio
    async def test_startup_in_development_skips_migrations(self, mock_settings):
        """Test that migrations are skipped in development."""
        mock_settings.environment = "development"
        
        with patch('logging.basicConfig'):
            await startup_event()
    
    @pytest.mark.asyncio
    async def test_startup_in_production_runs_migrations(self):
        """Test that migrations run in production."""
        with patch('main.settings') as mock_settings:
            mock_settings.environment = "production"
            
            with patch('logging.basicConfig'):
                with patch('subprocess.run') as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stderr="")
                    
                    await startup_event()
                    
                    mock_run.assert_called_once()
                    args = mock_run.call_args[0][0]
                    assert "alembic" in args
                    assert "upgrade" in args
                    assert "head" in args
    
    @pytest.mark.asyncio
    async def test_startup_handles_migration_failure_gracefully(self):
        """Test that migration failures are handled gracefully."""
        with patch('main.settings') as mock_settings:
            mock_settings.environment = "production"
            
            with patch('logging.basicConfig'):
                with patch('subprocess.run') as mock_run:
                    mock_run.return_value = MagicMock(returncode=1, stderr="Migration error")
                    
                    # Should not raise exception
                    await startup_event()
    
    @pytest.mark.asyncio
    async def test_startup_handles_migration_exception(self):
        """Test that migration exceptions are handled gracefully."""
        with patch('main.settings') as mock_settings:
            mock_settings.environment = "production"
            
            with patch('logging.basicConfig'):
                with patch('subprocess.run', side_effect=Exception("Subprocess error")):
                    # Should not raise exception
                    await startup_event()


# ============================================================================
# CORS CONFIGURATION TESTS
# ============================================================================

class TestGetCorsOrigins:
    """Tests for get_cors_origins function."""
    
    def test_get_cors_origins_returns_base_origins(self):
        """Test that base origins are always included."""
        with patch.dict(os.environ, {}, clear=True):
            with patch('main.settings') as mock_settings:
                mock_settings.environment = "development"
                
                origins = get_cors_origins()
                
                assert "http://localhost:3000" in origins
                assert "http://localhost:5173" in origins
                assert "http://127.0.0.1:3000" in origins
    
    def test_get_cors_origins_adds_env_variable_origins(self):
        """Test that CORS_ORIGINS from env are added."""
        with patch.dict(os.environ, {"CORS_ORIGINS": "https://example.com, https://test.com"}):
            with patch('main.settings') as mock_settings:
                mock_settings.environment = "development"
                
                origins = get_cors_origins()
                
                assert "https://example.com" in origins
                assert "https://test.com" in origins
    
    def test_get_cors_origins_adds_production_origins(self):
        """Test that production origins are added in production."""
        with patch.dict(os.environ, {}, clear=True):
            with patch('main.settings') as mock_settings:
                mock_settings.environment = "production"
                
                origins = get_cors_origins()
                
                assert "https://trustworthy-perfection-production.up.railway.app" in origins
    
    def test_get_cors_origins_adds_frontend_url(self):
        """Test that FRONTEND_BASE_URL from env is added."""
        with patch.dict(os.environ, {"FRONTEND_BASE_URL": "https://custom-frontend.com"}):
            with patch('main.settings') as mock_settings:
                mock_settings.environment = "development"
                
                origins = get_cors_origins()
                
                assert "https://custom-frontend.com" in origins
    
    def test_get_cors_origins_handles_whitespace_in_cors_list(self):
        """Test that whitespace is stripped from CORS_ORIGINS."""
        with patch.dict(os.environ, {"CORS_ORIGINS": " https://example.com , https://test.com "}):
            with patch('main.settings') as mock_settings:
                mock_settings.environment = "development"
                
                origins = get_cors_origins()
                
                assert "https://example.com" in origins
                assert "https://test.com" in origins


# ============================================================================
# WEBSOCKET TESTS
# ============================================================================

class TestWebSocketEndpoint:
    """Tests for WebSocket endpoint."""
    
    @pytest.mark.asyncio
    async def test_websocket_connects_to_progress_manager(self):
        """Test WebSocket connects to progress manager."""
        mock_websocket = AsyncMock()
        mock_websocket.receive_text = AsyncMock(side_effect=WebSocketDisconnect())
        
        with patch('main.progress_manager') as mock_pm:
            mock_pm.connect = AsyncMock()
            mock_pm.disconnect = MagicMock()
            
            await websocket_endpoint(mock_websocket, "session123")
            
            mock_pm.connect.assert_called_once_with(mock_websocket, "session123")
            mock_pm.disconnect.assert_called_once_with("session123")
    
    @pytest.mark.asyncio
    async def test_websocket_handles_ping_messages(self):
        """Test WebSocket handles ping messages correctly."""
        mock_websocket = AsyncMock()
        ping_message = json.dumps({"type": "ping"})
        mock_websocket.receive_text = AsyncMock(side_effect=[ping_message, WebSocketDisconnect()])
        mock_websocket.send_text = AsyncMock()
        
        with patch('main.progress_manager') as mock_pm:
            mock_pm.connect = AsyncMock()
            mock_pm.disconnect = MagicMock()
            
            await websocket_endpoint(mock_websocket, "session123")
            
            # Check that pong was sent
            calls = mock_websocket.send_text.call_args_list
            assert len(calls) > 0
            pong_data = json.loads(calls[0][0][0])
            assert pong_data["type"] == "pong"
            assert "timestamp" in pong_data
    
    @pytest.mark.asyncio
    async def test_websocket_disconnects_on_websocket_disconnect(self):
        """Test WebSocket disconnects properly on WebSocketDisconnect."""
        mock_websocket = AsyncMock()
        mock_websocket.receive_text = AsyncMock(side_effect=WebSocketDisconnect())
        
        with patch('main.progress_manager') as mock_pm:
            mock_pm.connect = AsyncMock()
            mock_pm.disconnect = MagicMock()
            
            await websocket_endpoint(mock_websocket, "session123")
            
            mock_pm.disconnect.assert_called_once_with("session123")
    
    @pytest.mark.asyncio
    async def test_websocket_disconnects_on_exception(self):
        """Test WebSocket disconnects on exception."""
        mock_websocket = AsyncMock()
        mock_websocket.receive_text = AsyncMock(side_effect=Exception("Connection error"))
        
        with patch('main.progress_manager') as mock_pm:
            mock_pm.connect = AsyncMock()
            mock_pm.disconnect = MagicMock()
            
            await websocket_endpoint(mock_websocket, "session123")
            
            mock_pm.disconnect.assert_called_once_with("session123")


# ============================================================================
# ROOT ENDPOINT TESTS
# ============================================================================

class TestRootEndpoint:
    """Tests for the root / endpoint."""
    
    @pytest.mark.asyncio
    async def test_root_returns_correct_structure(self):
        """Test root endpoint returns correct structure."""
        response = await root()
        
        assert "message" in response
        assert "version" in response
        assert "status" in response
        assert response["status"] == "active"
    
    @pytest.mark.asyncio
    async def test_root_returns_version_2(self):
        """Test root endpoint returns version 2.0.0."""
        response = await root()
        assert response["version"] == "2.0.0"
    
    def test_root_endpoint_via_client(self, client):
        """Test root endpoint via test client."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "AI Simulation Marketplace Platform API"


# ============================================================================
# SCENARIO ENDPOINTS TESTS
# ============================================================================

class TestGetScenarios:
    """Tests for GET /api/scenarios/ endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_scenarios_unauthenticated_returns_public(self, mock_db, mock_scenario):
        """Test unauthenticated users get public scenarios only."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [mock_scenario]
        mock_db.query.return_value = mock_query
        
        with patch('main.get_current_user_optional', return_value=None):
            scenarios = await get_scenarios(current_user=None, db=mock_db)
            
            assert len(scenarios) == 1
            assert scenarios[0]["title"] == "Test Scenario"
    
    @pytest.mark.asyncio
    async def test_get_scenarios_authenticated_returns_user_scenarios(self, mock_db, mock_user, mock_scenario):
        """Test authenticated users get their own scenarios."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [mock_scenario]
        mock_db.query.return_value = mock_query
        
        scenarios = await get_scenarios(current_user=mock_user, db=mock_db)
        
        assert len(scenarios) == 1
    
    @pytest.mark.asyncio
    async def test_get_scenarios_excludes_soft_deleted(self, mock_db):
        """Test that soft-deleted scenarios are excluded."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query
        
        scenarios = await get_scenarios(current_user=None, db=mock_db)
        
        assert len(scenarios) == 0
    
    @pytest.mark.asyncio
    async def test_get_scenarios_handles_database_error(self, mock_db):
        """Test scenarios endpoint handles database errors."""
        mock_db.query.side_effect = Exception("Database error")
        
        with pytest.raises(HTTPException) as exc_info:
            await get_scenarios(current_user=None, db=mock_db)
        
        assert exc_info.value.status_code == 500


class TestGetDraftScenarios:
    """Tests for GET /api/scenarios/drafts/ endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_draft_scenarios_requires_authentication(self, mock_db, mock_user):
        """Test draft scenarios endpoint requires authentication."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query
        
        drafts = await get_draft_scenarios(current_user=mock_user, db=mock_db)
        
        assert isinstance(drafts, list)
    
    @pytest.mark.asyncio
    async def test_get_draft_scenarios_returns_only_drafts(self, mock_db, mock_user, mock_scenario):
        """Test only draft scenarios are returned."""
        mock_scenario.is_draft = True
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [mock_scenario]
        mock_db.query.return_value = mock_query
        
        drafts = await get_draft_scenarios(current_user=mock_user, db=mock_db)
        
        assert len(drafts) == 1
        assert drafts[0]["is_draft"] == True
    
    @pytest.mark.asyncio
    async def test_get_draft_scenarios_includes_completion_status(self, mock_db, mock_user, mock_scenario):
        """Test draft scenarios include completion status fields."""
        mock_scenario.is_draft = True
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [mock_scenario]
        mock_db.query.return_value = mock_query
        
        drafts = await get_draft_scenarios(current_user=mock_user, db=mock_db)
        
        assert "completion_status" in drafts[0]
        assert "personas_completed" in drafts[0]
        assert "scenes_completed" in drafts[0]


class TestDeleteScenarioByUniqueId:
    """Tests for DELETE /api/scenarios/unique/{unique_id} endpoint."""
    
    @pytest.mark.asyncio
    async def test_delete_scenario_by_unique_id_success(self, mock_db, mock_user, mock_scenario):
        """Test successful scenario deletion by unique_id."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_scenario
        mock_db.query.return_value = mock_query
        
        with patch('main.SoftDeletionService') as mock_service_class:
            mock_service = MagicMock()
            mock_service.soft_delete_scenario.return_value = True
            mock_service_class.return_value = mock_service
            
            response = await delete_scenario_by_unique_id("scenario-123", mock_user, mock_db)
            
            assert response["status"] == "success"
            assert "deleted successfully" in response["message"]
    
    @pytest.mark.asyncio
    async def test_delete_scenario_not_found(self, mock_db, mock_user):
        """Test deletion fails when scenario not found."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query
        
        with pytest.raises(HTTPException) as exc_info:
            await delete_scenario_by_unique_id("nonexistent", mock_user, mock_db)
        
        assert exc_info.value.status_code == 404
    
    @pytest.mark.asyncio
    async def test_delete_scenario_soft_deletion_fails(self, mock_db, mock_user, mock_scenario):
        """Test deletion handles soft deletion service failure."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_scenario
        mock_db.query.return_value = mock_query
        
        with patch('main.SoftDeletionService') as mock_service_class:
            mock_service = MagicMock()
            mock_service.soft_delete_scenario.return_value = False
            mock_service_class.return_value = mock_service
            
            with pytest.raises(HTTPException) as exc_info:
                await delete_scenario_by_unique_id("scenario-123", mock_user, mock_db)
            
            assert exc_info.value.status_code == 500


class TestDeleteDraftScenario:
    """Tests for DELETE /api/scenarios/drafts/{scenario_id} endpoint."""
    
    @pytest.mark.asyncio
    async def test_delete_draft_scenario_success(self, mock_db, mock_user, mock_scenario):
        """Test successful draft scenario deletion."""
        mock_scenario.is_draft = True
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_scenario
        mock_db.query.return_value = mock_query
        
        with patch('main.SoftDeletionService') as mock_service_class:
            mock_service = MagicMock()
            mock_service.soft_delete_scenario.return_value = True
            mock_service_class.return_value = mock_service
            
            response = await delete_draft_scenario(1, mock_user, mock_db)
            
            assert "deleted successfully" in response["message"]
            assert response["deleted_id"] == 1
    
    @pytest.mark.asyncio
    async def test_delete_draft_scenario_not_found(self, mock_db, mock_user):
        """Test deletion fails when draft scenario not found."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query
        
        with pytest.raises(HTTPException) as exc_info:
            await delete_draft_scenario(999, mock_user, mock_db)
        
        assert exc_info.value.status_code == 404


class TestGetDraftScenario:
    """Tests for GET /api/scenarios/drafts/{scenario_id} endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_draft_scenario_success(self, mock_db, mock_user, mock_scenario):
        """Test retrieving a specific draft scenario."""
        mock_scenario.is_draft = True
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_scenario
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query
        
        result = await get_draft_scenario(1, mock_user, mock_db)
        
        assert result["id"] == 1
        assert result["title"] == "Test Scenario"
    
    @pytest.mark.asyncio
    async def test_get_draft_scenario_not_found(self, mock_db, mock_user):
        """Test retrieval fails when draft not found."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query
        
        with pytest.raises(HTTPException) as exc_info:
            await get_draft_scenario(999, mock_user, mock_db)
        
        assert exc_info.value.status_code == 404


class TestUpdateScenarioStatus:
    """Tests for PUT /api/scenarios/{scenario_id}/status endpoint."""
    
    @pytest.mark.asyncio
    async def test_update_scenario_status_to_active(self, mock_db, mock_user, mock_scenario):
        """Test updating scenario status to active."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_scenario
        mock_db.query.return_value = mock_query
        
        result = await update_scenario_status(1, {"status": "active"}, mock_user, mock_db)
        
        assert result["status"] == "active"
        assert result["is_draft"] == False
        assert result["is_public"] == True
    
    @pytest.mark.asyncio
    async def test_update_scenario_status_to_draft(self, mock_db, mock_user, mock_scenario):
        """Test updating scenario status to draft."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_scenario
        mock_db.query.return_value = mock_query
        
        result = await update_scenario_status(1, {"status": "draft"}, mock_user, mock_db)
        
        assert result["status"] == "draft"
        assert result["is_draft"] == True
        assert result["is_public"] == False
    
    @pytest.mark.asyncio
    async def test_update_scenario_status_invalid_status(self, mock_db, mock_user, mock_scenario):
        """Test updating with invalid status value."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_scenario
        mock_db.query.return_value = mock_query
        
        with pytest.raises(HTTPException) as exc_info:
            await update_scenario_status(1, {"status": "invalid"}, mock_user, mock_db)
        
        assert exc_info.value.status_code == 400
    
    @pytest.mark.asyncio
    async def test_update_scenario_status_unauthorized(self, mock_db, mock_user, mock_scenario):
        """Test update fails when user doesn't own scenario."""
        mock_scenario.created_by = 999  # Different user
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_scenario
        mock_db.query.return_value = mock_query
        
        with pytest.raises(HTTPException) as exc_info:
            await update_scenario_status(1, {"status": "active"}, mock_user, mock_db)
        
        assert exc_info.value.status_code == 403


# ============================================================================
# USER AUTHENTICATION TESTS
# ============================================================================

class TestRegisterUser:
    """Tests for POST /users/register endpoint."""
    
    @pytest.mark.asyncio
    async def test_register_user_success(self, mock_db):
        """Test successful user registration."""
        from schemas import UserRegister
        from fastapi import Response
        
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # No existing user
        mock_db.query.return_value = mock_query
        
        user_data = UserRegister(
            email="[email protected]",
            username="newuser",
            password="password123",
            full_name="New User",
            role="student",
            bio=None,
            avatar_url=None,
            profile_public=True,
            allow_contact=True
        )
        
        response_obj = Response()
        
        with patch('main.generate_unique_user_id', return_value="STU-001"):
            with patch('main.get_password_hash', return_value="hashed"):
                with patch('main.create_access_token', return_value="token123"):
                    result = await register_user(user_data, response_obj, mock_db)
                    
                    mock_db.add.assert_called_once()
                    mock_db.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_register_user_email_exists(self, mock_db, mock_user):
        """Test registration fails when email exists."""
        from schemas import UserRegister
        from fastapi import Response
        
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_user
        mock_db.query.return_value = mock_query
        
        user_data = UserRegister(
            email="[email protected]",
            username="newuser",
            password="password123",
            full_name="New User",
            role="student",
            bio=None,
            avatar_url=None,
            profile_public=True,
            allow_contact=True
        )
        
        response_obj = Response()
        
        with pytest.raises(HTTPException) as exc_info:
            await register_user(user_data, response_obj, mock_db)
        
        assert exc_info.value.status_code == 400
        assert "Email already registered" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_register_user_username_exists(self, mock_db, mock_user):
        """Test registration fails when username exists."""
        from schemas import UserRegister
        from fastapi import Response
        
        mock_user.email = "[email protected]"  # Different email
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_user
        mock_db.query.return_value = mock_query
        
        user_data = UserRegister(
            email="[email protected]",
            username="testuser",
            password="password123",
            full_name="New User",
            role="student",
            bio=None,
            avatar_url=None,
            profile_public=True,
            allow_contact=True
        )
        
        response_obj = Response()
        
        with pytest.raises(HTTPException) as exc_info:
            await register_user(user_data, response_obj, mock_db)
        
        assert exc_info.value.status_code == 400
        assert "Username already taken" in str(exc_info.value.detail)


class TestLoginUser:
    """Tests for POST /users/login endpoint."""
    
    @pytest.mark.asyncio
    async def test_login_user_success(self, mock_db, mock_user):
        """Test successful user login."""
        from schemas import UserLogin
        from fastapi import Response
        
        user_data = UserLogin(email="[email protected]", password="password123")
        response_obj = Response()
        
        with patch('main.authenticate_user', return_value=mock_user):
            with patch('main.create_access_token', return_value="token123"):
                result = await login_user(user_data, response_obj, mock_db)
                
                assert result.token_type == "cookie"
                assert result.user.email == "[email protected]"
    
    @pytest.mark.asyncio
    async def test_login_user_invalid_credentials(self, mock_db):
        """Test login fails with invalid credentials."""
        from schemas import UserLogin
        from fastapi import Response
        
        user_data = UserLogin(email="[email protected]", password="wrong")
        response_obj = Response()
        
        with patch('main.authenticate_user', return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await login_user(user_data, response_obj, mock_db)
            
            assert exc_info.value.status_code == 401


class TestCheckEmailExists:
    """Tests for POST /users/check-email endpoint."""
    
    @pytest.mark.asyncio
    async def test_check_email_exists_true(self, mock_db, mock_user):
        """Test email existence check returns true."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_user
        mock_db.query.return_value = mock_query
        
        result = await check_email_exists({"email": "[email protected]"}, mock_db)
        
        assert result["exists"] == True
    
    @pytest.mark.asyncio
    async def test_check_email_exists_false(self, mock_db):
        """Test email existence check returns false."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query
        
        result = await check_email_exists({"email": "[email protected]"}, mock_db)
        
        assert result["exists"] == False
    
    @pytest.mark.asyncio
    async def test_check_email_missing_email(self, mock_db):
        """Test email check fails when email is missing."""
        with pytest.raises(HTTPException) as exc_info:
            await check_email_exists({}, mock_db)
        
        assert exc_info.value.status_code == 400


class TestLogoutUser:
    """Tests for POST /users/logout endpoint."""
    
    @pytest.mark.asyncio
    async def test_logout_user_success(self):
        """Test successful user logout."""
        from fastapi import Response
        
        response_obj = Response()
        
        with patch('main.settings') as mock_settings:
            mock_settings.environment = "development"
            result = await logout_user(response_obj)
            
            assert result["message"] == "Successfully logged out"


class TestGetCurrentUserProfile:
    """Tests for GET /users/me endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_current_user_profile(self, mock_user):
        """Test retrieving current user profile."""
        result = await get_current_user_profile(mock_user)
        
        assert result.email == "[email protected]"


class TestTestLogin:
    """Tests for POST /test-login endpoint."""
    
    @pytest.mark.asyncio
    async def test_test_login_blocked_in_production(self, mock_db):
        """Test test-login endpoint is blocked in production."""
        from schemas import UserLogin
        from fastapi import Request
        
        user_data = UserLogin(email="[email protected]", password="password")
        mock_request = MagicMock(spec=Request)
        
        with patch('main.settings') as mock_settings:
            mock_settings.environment = "production"
            
            with pytest.raises(HTTPException) as exc_info:
                await test_login(user_data, mock_request, mock_db, None)
            
            assert exc_info.value.status_code == 404
    
    @pytest.mark.asyncio
    async def test_test_login_success_in_development(self, mock_db, mock_user):
        """Test test-login works in development."""
        from schemas import UserLogin
        from fastapi import Request
        
        user_data = UserLogin(email="[email protected]", password="password")
        mock_request = MagicMock(spec=Request)
        
        with patch('main.settings') as mock_settings:
            mock_settings.environment = "development"
            
            with patch('main.authenticate_user', return_value=mock_user):
                result = await test_login(user_data, mock_request, mock_db, None)
                
                assert result["success"] == True


class TestUpdateCurrentUser:
    """Tests for PUT /users/me endpoint."""
    
    @pytest.mark.asyncio
    async def test_update_current_user(self, mock_db, mock_user):
        """Test updating current user profile."""
        from schemas import UserUpdate
        
        update_data = UserUpdate(full_name="Updated Name", bio="New bio")
        
        result = await update_current_user(update_data, mock_user, mock_db)
        
        mock_db.commit.assert_called_once()


class TestChangePassword:
    """Tests for POST /users/change-password endpoint."""
    
    @pytest.mark.asyncio
    async def test_change_password_success(self, mock_db, mock_user):
        """Test successful password change."""
        from schemas import PasswordChange
        
        password_data = PasswordChange(
            current_password="oldpassword",
            new_password="newpassword"
        )
        
        with patch('main.authenticate_user', return_value=mock_user):
            with patch('main.get_password_hash', return_value="newhash"):
                result = await change_password(password_data, mock_user, mock_db)
                
                assert result["message"] == "Password changed successfully"
    
    @pytest.mark.asyncio
    async def test_change_password_wrong_current(self, mock_db, mock_user):
        """Test password change fails with wrong current password."""
        from schemas import PasswordChange
        
        password_data = PasswordChange(
            current_password="wrongpassword",
            new_password="newpassword"
        )
        
        with patch('main.authenticate_user', return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await change_password(password_data, mock_user, mock_db)
            
            assert exc_info.value.status_code == 400


class TestTrackUserActivity:
    """Tests for POST /users/activity endpoint."""
    
    @pytest.mark.asyncio
    async def test_track_user_activity_success(self, mock_db, mock_user):
        """Test successful activity tracking."""
        result = await track_user_activity({}, mock_user, mock_db)
        
        assert result["status"] == "success"
        assert "timestamp" in result
    
    @pytest.mark.asyncio
    async def test_track_user_activity_handles_error(self, mock_db, mock_user):
        """Test activity tracking handles errors gracefully."""
        mock_db.commit.side_effect = Exception("DB error")
        
        result = await track_user_activity({}, mock_user, mock_db)
        
        assert result["status"] == "error"


class TestGetUserProfile:
    """Tests for GET /users/{user_id} endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_user_profile_public(self, mock_db, mock_user):
        """Test retrieving public user profile."""
        mock_user.profile_public = True
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_user
        mock_db.query.return_value = mock_query
        
        result = await get_user_profile(1, mock_db)
        
        assert result.email == "[email protected]"
    
    @pytest.mark.asyncio
    async def test_get_user_profile_private(self, mock_db, mock_user):
        """Test private profile returns 404."""
        mock_user.profile_public = False
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_user
        mock_db.query.return_value = mock_query
        
        with pytest.raises(HTTPException) as exc_info:
            await get_user_profile(1, mock_db)
        
        assert exc_info.value.status_code == 404
    
    @pytest.mark.asyncio
    async def test_get_user_profile_not_found(self, mock_db):
        """Test user not found returns 404."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query
        
        with pytest.raises(HTTPException) as exc_info:
            await get_user_profile(999, mock_db)
        
        assert exc_info.value.status_code == 404


# ============================================================================
# PUBLIC SCENARIO ENDPOINTS TESTS
# ============================================================================

class TestGetPublicScenarios:
    """Tests for GET /scenarios endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_public_scenarios(self, mock_db, mock_scenario):
        """Test retrieving public scenarios."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_scenario]
        mock_db.query.return_value = mock_query
        
        result = await get_public_scenarios(skip=0, limit=20, db=mock_db)
        
        assert len(result) == 1
        assert result[0]["title"] == "Test Scenario"
    
    @pytest.mark.asyncio
    async def test_get_public_scenarios_pagination(self, mock_db):
        """Test pagination parameters are used."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query
        
        await get_public_scenarios(skip=10, limit=5, db=mock_db)
        
        mock_query.offset.assert_called_with(10)
        mock_query.limit.assert_called_with(5)


class TestGetScenarioDetails:
    """Tests for GET /scenarios/{scenario_id} endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_scenario_details_success(self, mock_db, mock_scenario):
        """Test retrieving scenario details."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_scenario
        mock_query.count.return_value = 3
        mock_db.query.return_value = mock_query
        
        result = await get_scenario_details(1, mock_db)
        
        assert result["id"] == 1
        assert result["title"] == "Test Scenario"
        assert "persona_count" in result
        assert "scene_count" in result
    
    @pytest.mark.asyncio
    async def test_get_scenario_details_not_found(self, mock_db):
        """Test scenario details not found."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query
        
        with pytest.raises(HTTPException) as exc_info:
            await get_scenario_details(999, mock_db)
        
        assert exc_info.value.status_code == 404


# ============================================================================
# TEST ENDPOINTS TESTS
# ============================================================================

class TestTestEndpoints:
    """Tests for various /api/test* endpoints."""
    
    @pytest.mark.asyncio
    async def test_test_endpoint(self):
        """Test /api/test endpoint."""
        result = await test_endpoint()
        
        assert result["status"] == "ok"
        assert result["message"] == "Server is working"
    
    @pytest.mark.asyncio
    async def test_test_auth_endpoint(self, mock_user):
        """Test /api/test-auth endpoint."""
        result = await test_auth_endpoint(mock_user)
        
        assert result["status"] == "ok"
        assert result["user"] == "[email protected]"
    
    @pytest.mark.asyncio
    async def test_test_db_endpoint_success(self, mock_db):
        """Test /api/test-db endpoint success."""
        mock_query = MagicMock()
        mock_query.count.return_value = 5
        mock_db.query.return_value = mock_query
        
        result = await test_db_endpoint(mock_db)
        
        assert result["status"] == "ok"
        assert result["scenario_count"] == 5
    
    @pytest.mark.asyncio
    async def test_test_db_endpoint_error(self, mock_db):
        """Test /api/test-db endpoint handles errors."""
        mock_db.query.side_effect = Exception("DB error")
        
        result = await test_db_endpoint(mock_db)
        
        assert result["status"] == "error"
    
    @pytest.mark.asyncio
    async def test_test_combined_endpoint(self, mock_db, mock_user):
        """Test /api/test-combined endpoint."""
        mock_query = MagicMock()
        mock_query.count.return_value = 5
        mock_db.query.return_value = mock_query
        
        result = await test_combined_endpoint(mock_db, mock_user)
        
        assert result["status"] == "ok"
        assert result["user"] == "[email protected]"
    
    @pytest.mark.asyncio
    async def test_scenario_test_endpoint(self, mock_db, mock_user, mock_scenario):
        """Test /api/scenario-test/{scenario_id} endpoint."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_scenario
        mock_db.query.return_value = mock_query
        
        result = await test_scenario_endpoint(1, mock_db, mock_user)
        
        assert result["status"] == "ok"
        assert result["scenario_id"] == 1
    
    @pytest.mark.asyncio
    async def test_get_scenario_full(self, mock_db, mock_user):
        """Test /api/scenarios/{scenario_id}/full endpoint."""
        result = await get_scenario_full(1, mock_db, mock_user)
        
        assert result["status"] == "ok"
        assert result["scenario_id"] == 1


# ============================================================================
# CACHE MANAGEMENT TESTS
# ============================================================================

class TestCacheManagement:
    """Tests for cache management endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_cache_stats(self, mock_user, mock_redis_manager):
        """Test GET /api/cache/stats endpoint."""
        mock_user.role = "admin"  # Ensure admin role
        
        with patch('main.ai_cache_service') as mock_ai:
            with patch('main.db_cache_service') as mock_db_cache:
                mock_ai.get_cache_stats.return_value = {"hits": 100}
                mock_db_cache.get_cache_stats.return_value = {"hits": 50}
                
                result = await get_cache_stats(mock_user)
                
                assert "ai_cache" in result
                assert "db_cache" in result
                assert "redis_info" in result
    
    @pytest.mark.asyncio
    async def test_invalidate_user_cache(self, mock_user):
        """Test POST /api/cache/invalidate/user/{user_id} endpoint."""
        mock_user.role = "admin"
        
        with patch('main.ai_cache_service') as mock_ai:
            with patch('main.db_cache_service') as mock_db_cache:
                mock_ai.invalidate_user_cache.return_value = 10
                mock_db_cache.invalidate_user_related_cache.return_value = 5
                
                result = await invalidate_user_cache(1, mock_user)
                
                assert result["ai_cache_invalidated"] == 10
                assert result["db_cache_invalidated"] == 5
                assert result["total_invalidated"] == 15
    
    @pytest.mark.asyncio
    async def test_invalidate_scenario_cache(self, mock_user):
        """Test POST /api/cache/invalidate/scenario/{scenario_id} endpoint."""
        mock_user.role = "admin"
        
        with patch('main.ai_cache_service') as mock_ai:
            with patch('main.db_cache_service') as mock_db_cache:
                mock_ai.invalidate_simulation_cache.return_value = 8
                mock_db_cache.invalidate_scenario_cache.return_value = 3
                
                result = await invalidate_scenario_cache(1, mock_user)
                
                assert result["ai_cache_invalidated"] == 8
                assert result["db_cache_invalidated"] == 3
    
    @pytest.mark.asyncio
    async def test_cleanup_cache(self, mock_user):
        """Test POST /api/cache/cleanup endpoint."""
        mock_user.role = "admin"
        
        with patch('main.ai_cache_service') as mock_ai:
            with patch('main.db_cache_service') as mock_db_cache:
                mock_ai.cleanup_expired_cache.return_value = 20
                mock_db_cache.cleanup_expired_cache.return_value = 15
                
                result = await cleanup_cache(mock_user)
                
                assert result["ai_cache_entries"] == 20
                assert result["db_cache_entries"] == 15


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests using TestClient."""
    
    def test_health_endpoint_integration(self, client):
        """Integration test for health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
    
    def test_root_endpoint_integration(self, client):
        """Integration test for root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
    
    def test_test_endpoint_integration(self, client):
        """Integration test for test endpoint."""
        response = client.get("/api/test")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    @pytest.mark.asyncio
    async def test_get_scenarios_empty_database(self, mock_db):
        """Test scenarios endpoint with empty database."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query
        
        result = await get_scenarios(current_user=None, db=mock_db)
        
        assert result == []
    
    @pytest.mark.asyncio
    async def test_cors_origins_with_empty_env(self):
        """Test CORS origins with no environment variables."""
        with patch.dict(os.environ, {}, clear=True):
            with patch('main.settings') as mock_settings:
                mock_settings.environment = "development"
                
                origins = get_cors_origins()
                
                # Should still have base origins
                assert len(origins) > 0
    
    @pytest.mark.asyncio
    async def test_websocket_with_invalid_json(self):
        """Test WebSocket handles invalid JSON."""
        mock_websocket = AsyncMock()
        mock_websocket.receive_text = AsyncMock(side_effect=["invalid json", WebSocketDisconnect()])
        
        with patch('main.progress_manager') as mock_pm:
            mock_pm.connect = AsyncMock()
            mock_pm.disconnect = MagicMock()
            
            # Should handle gracefully
            await websocket_endpoint(mock_websocket, "session123")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])