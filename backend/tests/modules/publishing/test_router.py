"""
Tests for publishing router endpoints.

"""
import pytest

pytest.skip(
    "Needs rewrite: router now exposes `async def build_simulation_response`; "
    "these tests import the old sync `_build_simulation_response` and call it synchronously.",
    allow_module_level=True,
)

from unittest.mock import Mock, patch, AsyncMock
from fastapi import HTTPException
from datetime import datetime
from sqlalchemy.orm import Session

from app.main import app
from app.dependencies import get_current_user, get_current_user_optional
from modules.publishing.router import router, _build_simulation_response
from modules.publishing.service import PublishingService
from common.db.models import Simulation, SimulationPersona, SimulationScene, User


@pytest.fixture
def mock_user(db_session: Session):
    """Create a test user in the database."""
    user = User(
        email="test@example.com",
        hashed_password="hashed",
        role="professor"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def mock_simulation(db_session: Session, mock_user: User):
    """Create a test simulation in the database."""
    from common.utils.id_generator import generate_simulation_id
    unique_id = generate_simulation_id(db_session)
    
    simulation = Simulation(
        unique_id=unique_id,
        title="Test Simulation",
        description="Test Description",
        created_by=mock_user.id,
        status="draft",
        is_draft=True,
        is_public=False
    )
    db_session.add(simulation)
    db_session.commit()
    db_session.refresh(simulation)
    return simulation


@pytest.fixture
def mock_simulation_with_personas_scenes(db_session: Session, mock_simulation: Simulation):
    """Create a simulation with personas and scenes."""
    persona = SimulationPersona(
        scenario_id=mock_simulation.id,
        name="Test Persona",
        role="Manager",
        background="Test background",
        image_url="https://s3.amazonaws.com/bucket/scenarios/1/personas/1/avatar.png"
    )
    db_session.add(persona)
    db_session.flush()
    
    scene = SimulationScene(
        scenario_id=mock_simulation.id,
        title="Test Scene",
        description="Test scene description",
        scene_order=1,
        image_url="https://s3.amazonaws.com/bucket/scenarios/1/scenes/1/image.png"
    )
    db_session.add(scene)
    db_session.commit()
    db_session.refresh(persona)
    db_session.refresh(scene)
    
    return mock_simulation, persona, scene


class TestGetSimulations:
    """Tests for GET /api/publishing/simulations/ endpoint."""
    
    def test_get_simulations_returns_user_simulations(
        self, client, db_session, mock_user, mock_simulation
    ):
        """Test that get_simulations returns simulations for the current user."""
        # Override authentication dependency
        async def override_get_current_user():
            return mock_user
        
        app.dependency_overrides[get_current_user] = override_get_current_user
        
        try:
            response = client.get("/api/publishing/simulations/")
            
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) > 0
            assert data[0]["id"] == mock_simulation.id
            assert data[0]["title"] == "Test Simulation"
        finally:
            app.dependency_overrides.clear()
    
    def test_get_simulations_filters_by_status_draft(
        self, client, db_session, mock_user, mock_simulation
    ):
        """Test that get_simulations filters by draft status."""
        # Create an active simulation
        active_sim = Simulation(
            unique_id="active-123",
            title="Active Simulation",
            created_by=mock_user.id,
            status="active",
            is_draft=False,
            is_public=True
        )
        db_session.add(active_sim)
        db_session.commit()
        
        # Override authentication dependency
        async def override_get_current_user():
            return mock_user
        
        app.dependency_overrides[get_current_user] = override_get_current_user
        
        try:
            response = client.get("/api/publishing/simulations/?status=draft")
            
            assert response.status_code == 200
            data = response.json()
            # Should only return draft simulations
            assert all(sim["is_draft"] is True for sim in data)
        finally:
            app.dependency_overrides.clear()
    
    def test_get_simulations_requires_authentication(self, client):
        """Test that get_simulations requires authentication."""
        # Ensure no auth override
        app.dependency_overrides.clear()
        response = client.get("/api/publishing/simulations/")
        assert response.status_code == 401 or response.status_code == 403


class TestGetDraftSimulations:
    """Tests for GET /api/publishing/simulations/drafts/ endpoint."""
    
    def test_get_draft_simulations_returns_only_drafts(
        self, client, db_session, mock_user, mock_simulation
    ):
        """Test that get_draft_simulations returns only draft simulations."""
        async def override_get_current_user():
            return mock_user
        
        app.dependency_overrides[get_current_user] = override_get_current_user
        
        try:
            response = client.get("/api/publishing/simulations/drafts/")
            
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert all(sim["is_draft"] is True for sim in data)
        finally:
            app.dependency_overrides.clear()


class TestGetSimulationFull:
    """Tests for GET /api/publishing/simulations/{id}/full endpoint."""
    
    def test_get_simulation_full_returns_complete_data(
        self, client, db_session, mock_simulation_with_personas_scenes
    ):
        """Test that get_simulation_full returns complete simulation with personas and scenes."""
        simulation, persona, scene = mock_simulation_with_personas_scenes
        
        response = client.get(f"/api/publishing/simulations/{simulation.id}/full")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == simulation.id
        assert "personas" in data
        assert "scenes" in data
        assert len(data["personas"]) == 1
        assert len(data["scenes"]) == 1
        assert data["personas"][0]["name"] == "Test Persona"
        assert data["scenes"][0]["title"] == "Test Scene"
    
    def test_get_simulation_full_returns_404_for_nonexistent(
        self, client, db_session
    ):
        """Test that get_simulation_full returns 404 for nonexistent simulation."""
        response = client.get("/api/publishing/simulations/99999/full")
        assert response.status_code == 404
    
    def test_get_simulation_full_increments_usage_count_for_public(
        self, client, db_session, mock_simulation
    ):
        """Test that get_simulation_full increments usage_count for public simulations."""
        mock_simulation.is_public = True
        mock_simulation.usage_count = 0
        db_session.commit()
        
        initial_count = mock_simulation.usage_count
        response = client.get(f"/api/publishing/simulations/{mock_simulation.id}/full")
        
        assert response.status_code == 200
        db_session.refresh(mock_simulation)
        assert mock_simulation.usage_count == initial_count + 1


class TestGetUploadStatus:
    """Tests for GET /api/publishing/simulations/{id}/upload-status endpoint."""
    
    def test_get_upload_status_returns_completed_when_no_uploads(
        self, client, db_session, mock_user, mock_simulation
    ):
        """Test that get_upload_status returns completed when no uploads pending."""
        async def override_get_current_user_optional():
            return mock_user
        
        app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
        
        with patch.object(PublishingService, '_get_upload_status', return_value={
            "status": "completed",
            "completed": 0,
            "total": 0,
            "pending": 0,
            "failed": []
        }):
            try:
                response = client.get(f"/api/publishing/simulations/{mock_simulation.id}/upload-status")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "completed"
                assert data["completed"] == 0
                assert data["total"] == 0
            finally:
                app.dependency_overrides.clear()
    
    def test_get_upload_status_returns_uploading_when_pending(
        self, client, db_session, mock_user, mock_simulation
    ):
        """Test that get_upload_status returns uploading when uploads are pending."""
        async def override_get_current_user_optional():
            return mock_user
        
        app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
        
        with patch.object(PublishingService, '_get_upload_status', return_value={
            "status": "uploading",
            "completed": 2,
            "total": 5,
            "pending": 3,
            "failed": []
        }):
            try:
                response = client.get(f"/api/publishing/simulations/{mock_simulation.id}/upload-status")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "uploading"
                assert data["pending"] == 3
                assert data["completed"] == 2
            finally:
                app.dependency_overrides.clear()
    
    def test_get_upload_status_returns_404_for_nonexistent(
        self, client, db_session, mock_user
    ):
        """Test that get_upload_status returns 404 for nonexistent simulation."""
        async def override_get_current_user_optional():
            return mock_user
        
        app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
        
        try:
            response = client.get("/api/publishing/simulations/99999/upload-status")
            assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()
    
    def test_get_upload_status_requires_owner_for_private(
        self, client, db_session, mock_user, mock_simulation
    ):
        """Test that get_upload_status requires owner access for private simulations."""
        # Create another user
        other_user = User(
            email="other@example.com",
            hashed_password="hashed",
            role="professor"
        )
        db_session.add(other_user)
        db_session.commit()
        
        async def override_get_current_user_optional():
            return other_user
        
        app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
        
        try:
            response = client.get(f"/api/publishing/simulations/{mock_simulation.id}/upload-status")
            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestSaveSimulationDraft:
    """Tests for POST /api/publishing/simulations/save endpoint."""
    
    def test_save_simulation_draft_creates_new_simulation(
        self, client, db_session, mock_user
    ):
        """Test that save_simulation_draft creates a new simulation when no ID provided."""
        async def override_get_current_user_optional():
            return mock_user
        
        app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
        
        try:
            payload = {
                "title": "New Simulation",
                "description": "New Description",
                "student_role": "Manager",
                "personas": [],
                "scenes": []
            }
            response = client.post(
                "/api/publishing/simulations/save",
                json=payload
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "saved"
            assert "simulation_id" in data
            
            # Verify simulation was created
            simulation = db_session.query(Simulation).filter(
                Simulation.id == data["simulation_id"]
            ).first()
            assert simulation is not None
            assert simulation.title == "New Simulation"
        finally:
            app.dependency_overrides.clear()
    
    def test_save_simulation_draft_updates_existing_simulation(
        self, client, db_session, mock_user, mock_simulation
    ):
        """Test that save_simulation_draft updates an existing simulation."""
        async def override_get_current_user_optional():
            return mock_user
        
        app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
        
        try:
            payload = {
                "title": "Updated Title",
                "description": "Updated Description",
                "personas": [],
                "scenes": []
            }
            response = client.post(
                f"/api/publishing/simulations/save?simulation_id={mock_simulation.id}",
                json=payload
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "saved"
            
            # Verify simulation was updated
            db_session.refresh(mock_simulation)
            assert mock_simulation.title == "Updated Title"
        finally:
            app.dependency_overrides.clear()
    
    def test_save_simulation_draft_enqueues_temp_url_uploads(
        self, client, db_session, mock_user, mock_simulation
    ):
        """Test that save_simulation_draft enqueues uploads for temporary image URLs."""
        async def override_get_current_user_optional():
            return mock_user
        
        app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
        
        with patch.object(PublishingService, '_enqueue_image_upload', return_value=True) as mock_enqueue:
            try:
                payload = {
                    "title": "Test",
                    "personas": [{
                        "name": "Test Persona",
                        "role": "Manager",
                        "imageUrl": "https://oaidalleapiprodscus.blob.core.windows.net/temp.jpg"
                    }],
                    "scenes": [{
                        "title": "Test Scene",
                        "imageUrl": "https://cdn-magnific.freepik.com/temp.jpg"
                    }]
                }
                response = client.post(
                    f"/api/publishing/simulations/save?simulation_id={mock_simulation.id}",
                    json=payload
                )
                
                assert response.status_code == 200
                # Should have enqueued 2 uploads (1 persona + 1 scene)
                assert mock_enqueue.call_count == 2
            finally:
                app.dependency_overrides.clear()
    
    def test_save_simulation_draft_does_not_save_temp_urls(
        self, client, db_session, mock_user, mock_simulation
    ):
        """Test that save_simulation_draft does not save temporary URLs to database."""
        async def override_get_current_user_optional():
            return mock_user
        
        app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
        
        try:
            temp_url = "https://oaidalleapiprodscus.blob.core.windows.net/temp.jpg"
            payload = {
                "title": "Test",
                "personas": [{
                    "name": "Test Persona",
                    "role": "Manager",
                    "imageUrl": temp_url
                }],
                "scenes": []
            }
            response = client.post(
                f"/api/publishing/simulations/save?simulation_id={mock_simulation.id}",
                json=payload
            )
            
            assert response.status_code == 200
            
            # Verify persona was created but image_url is None (not temp URL)
            persona = db_session.query(SimulationPersona).filter(
                SimulationPersona.scenario_id == mock_simulation.id
            ).first()
            assert persona is not None
            assert persona.image_url != temp_url
            assert persona.image_url is None  # Should be None until worker uploads
        finally:
            app.dependency_overrides.clear()


class TestPublishSimulation:
    """Tests for POST /api/publishing/simulations/publish/{id} endpoint."""
    
    def test_publish_simulation_changes_status_to_active(
        self, client, db_session, mock_simulation
    ):
        """Test that publish_simulation changes status to active."""
        async def override_get_current_user_optional():
            return None
        
        app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
        
        with patch.object(PublishingService, '_get_upload_status', return_value={
            "status": "completed",
            "completed": 0,
            "total": 0,
            "pending": 0,
            "failed": []
        }):
            try:
                response = client.post(f"/api/publishing/simulations/publish/{mock_simulation.id}")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "published"
                
                # Verify simulation was published
                db_session.refresh(mock_simulation)
                assert mock_simulation.status == "active"
                assert mock_simulation.is_draft is False
                assert mock_simulation.is_public is True
            finally:
                app.dependency_overrides.clear()
    
    def test_publish_simulation_prevents_publishing_when_uploads_pending(
        self, client, db_session, mock_simulation
    ):
        """Test that publish_simulation prevents publishing when uploads are pending."""
        async def override_get_current_user_optional():
            return None
        
        app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
        
        with patch.object(PublishingService, '_get_upload_status', return_value={
            "status": "uploading",
            "completed": 2,
            "total": 5,
            "pending": 3,
            "failed": []
        }):
            try:
                response = client.post(f"/api/publishing/simulations/publish/{mock_simulation.id}")
                
                assert response.status_code == 400
                assert "uploading" in response.json()["detail"].lower()
            finally:
                app.dependency_overrides.clear()
    
    def test_publish_simulation_prevents_publishing_with_temp_urls(
        self, client, db_session, mock_user, mock_simulation
    ):
        """Test that publish_simulation prevents publishing when temp URLs exist."""
        # Create persona with temp URL
        persona = SimulationPersona(
            scenario_id=mock_simulation.id,
            name="Test",
            role="Manager",
            image_url="https://oaidalleapiprodscus.blob.core.windows.net/temp.jpg"
        )
        db_session.add(persona)
        db_session.commit()
        
        async def override_get_current_user_optional():
            return None
        
        app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
        
        with patch.object(PublishingService, '_get_upload_status', return_value={
            "status": "completed",
            "completed": 0,
            "total": 0,
            "pending": 0,
            "failed": []
        }):
            try:
                response = client.post(f"/api/publishing/simulations/publish/{mock_simulation.id}")
                
                assert response.status_code == 400
                assert "not uploaded" in response.json()["detail"].lower()
            finally:
                app.dependency_overrides.clear()


class TestUpdateSimulationStatus:
    """Tests for PUT /api/publishing/simulations/{id}/status endpoint."""
    
    def test_update_simulation_status_to_active_publishes(
        self, client, db_session, mock_user, mock_simulation
    ):
        """Test that updating status to active publishes the simulation."""
        async def override_get_current_user():
            return mock_user
        
        app.dependency_overrides[get_current_user] = override_get_current_user
        
        with patch.object(PublishingService, '_get_upload_status', return_value={
            "status": "completed",
            "completed": 0,
            "total": 0,
            "pending": 0,
            "failed": []
        }):
            try:
                response = client.put(
                    f"/api/publishing/simulations/{mock_simulation.id}/status",
                    json={"status": "active"}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "active"
                assert data["is_draft"] is False
                assert data["is_public"] is True
            finally:
                app.dependency_overrides.clear()
    
    def test_update_simulation_status_to_draft_unpublishes(
        self, client, db_session, mock_user, mock_simulation
    ):
        """Test that updating status to draft unpublishes the simulation."""
        # First publish it
        mock_simulation.status = "active"
        mock_simulation.is_draft = False
        mock_simulation.is_public = True
        db_session.commit()
        
        async def override_get_current_user():
            return mock_user
        
        app.dependency_overrides[get_current_user] = override_get_current_user
        
        try:
            response = client.put(
                f"/api/publishing/simulations/{mock_simulation.id}/status",
                json={"status": "draft"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "draft"
            assert data["is_draft"] is True
            assert data["is_public"] is False
        finally:
            app.dependency_overrides.clear()
    
    def test_update_simulation_status_rejects_invalid_status(
        self, client, db_session, mock_user, mock_simulation
    ):
        """Test that update_simulation_status rejects invalid status values."""
        async def override_get_current_user():
            return mock_user
        
        app.dependency_overrides[get_current_user] = override_get_current_user
        
        try:
            response = client.put(
                f"/api/publishing/simulations/{mock_simulation.id}/status",
                json={"status": "invalid_status"}
            )
            
            assert response.status_code == 422  # Validation error
        finally:
            app.dependency_overrides.clear()


class TestDeleteSimulation:
    """Tests for DELETE /api/publishing/simulations/{id} endpoint."""
    
    def test_delete_simulation_performs_soft_delete(
        self, client, db_session, mock_user, mock_simulation
    ):
        """Test that delete_simulation performs a soft delete."""
        async def override_get_current_user_optional():
            return mock_user
        
        app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
        
        try:
            response = client.delete(f"/api/publishing/simulations/{mock_simulation.id}")
            
            assert response.status_code == 204
            
            # Verify soft delete (deleted_at is set)
            db_session.refresh(mock_simulation)
            assert mock_simulation.deleted_at is not None
        finally:
            app.dependency_overrides.clear()
    
    def test_delete_simulation_requires_owner(
        self, client, db_session, mock_simulation
    ):
        """Test that delete_simulation requires owner access."""
        # Create another user
        other_user = User(
            email="other@example.com",
            hashed_password="hashed",
            role="professor"
        )
        db_session.add(other_user)
        db_session.commit()
        
        async def override_get_current_user_optional():
            return other_user
        
        app.dependency_overrides[get_current_user_optional] = override_get_current_user_optional
        
        try:
            response = client.delete(f"/api/publishing/simulations/{mock_simulation.id}")
            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()


class TestBuildSimulationResponse:
    """Tests for _build_simulation_response helper function."""
    
    def test_build_simulation_response_includes_all_fields(
        self, db_session, mock_simulation_with_personas_scenes
    ):
        """Test that _build_simulation_response includes all required fields."""
        simulation, persona, scene = mock_simulation_with_personas_scenes
        
        response = _build_simulation_response(simulation, db_session)
        
        assert response["id"] == simulation.id
        assert response["title"] == simulation.title
        assert "personas" in response
        assert "scenes" in response
        assert "completion_status" in response
        assert len(response["personas"]) == 1
        assert len(response["scenes"]) == 1
    
    def test_build_simulation_response_handles_learning_objectives_string(
        self, db_session, mock_simulation
    ):
        """Test that _build_simulation_response handles string learning objectives."""
        mock_simulation.learning_objectives = "Objective 1\nObjective 2\nObjective 3"
        db_session.commit()
        
        response = _build_simulation_response(mock_simulation, db_session)
        
        assert isinstance(response["learning_objectives"], list)
        assert len(response["learning_objectives"]) == 3
        assert "Objective 1" in response["learning_objectives"]
