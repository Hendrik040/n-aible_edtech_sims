"""
Tests for simulation router endpoints.

Verifies that each simulation HTTP endpoint delegates to `SimulationService` and 
returns the expected DTO-shaped JSON.

Covers success and error paths for starting simulations, 
non-streaming chat, streaming chat (SSE), scene/progress reads, 
grading, and saving messages.
"""

import pytest
from typing import Any, AsyncGenerator, Dict

from fastapi import status

from app.main import app
from app.dependencies import get_current_user
from modules.simulation.schemas.dto import (
    SimulationStartResponse,
    SimulationChatResponse,
    SimulationSceneResponse,
    UserProgressResponse,
)
from common.db.models import User
from common.exceptions import NotFoundError, ForbiddenError


@pytest.fixture
def mock_student_user(db_session):
    """Create a test student user in the database (per architecture: feature tests own their fixtures)."""
    user = User(
        user_id="student-1",
        email="student@example.com",
        full_name="Student User",
        username="student_user",
        password_hash="hashed",
        role="student",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


class TestStartSimulationEndpoint:
    """Tests for POST /api/simulation/start (thin router delegating to service)."""

    @pytest.mark.asyncio
    async def test_start_simulation_returns_service_response(
        self, async_client, monkeypatch, mock_student_user
    ):
        """
        Router should:
        - authenticate via `get_current_user` (architecture: auth in app layer)
        - delegate to `SimulationService.start_simulation`
        - return the service DTO as JSON with 200 status.
        """

        # Override auth dependency to return our test user
        async def override_get_current_user():
            return mock_student_user

        app.dependency_overrides[get_current_user] = override_get_current_user

        # Dummy service implementation that matches architecture contract
        class DummySimulationService:
            def __init__(self, db):
                self.db = db

            async def start_simulation(self, user_id: int, simulation_id: int) -> SimulationStartResponse:
                assert user_id == mock_student_user.id
                assert simulation_id == 42
                return SimulationStartResponse(
                    user_progress_id=1,
                    simulation={"id": simulation_id, "title": "Test Simulation"},
                    current_scene={"id": 10, "title": "Intro"},
                    simulation_status="in_progress",
                    conversation_history=[],
                    is_resuming=False,
                    all_scenes=[],
                )

        # Patch the router's SimulationService to our dummy (per architecture: router depends on service abstraction)
        import modules.simulation.router as simulation_router

        monkeypatch.setattr(simulation_router, "SimulationService", DummySimulationService)

        try:
            payload = {"simulation_id": 42}
            response = await async_client.post("/api/simulation/start", json=payload)

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["user_progress_id"] == 1
            assert data["simulation"]["id"] == 42
            assert data["current_scene"]["id"] == 10
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_start_simulation_maps_not_found_to_404(
        self, async_client, monkeypatch, mock_student_user
    ):
        """Router should translate `NotFoundError` from service into HTTP 404 (per error-handling section in architecture)."""

        async def override_get_current_user():
            return mock_student_user

        app.dependency_overrides[get_current_user] = override_get_current_user

        class FailingService:
            def __init__(self, db):
                self.db = db

            async def start_simulation(self, user_id: int, simulation_id: int):
                raise NotFoundError("Simulation not found")

        import modules.simulation.router as simulation_router

        monkeypatch.setattr(simulation_router, "SimulationService", FailingService)

        try:
            response = await async_client.post("/api/simulation/start", json={"simulation_id": 999})
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert "not found" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()


class TestLinearChatEndpoint:
    """Tests for POST /api/simulation/linear-chat (non-streaming chat)."""

    @pytest.mark.asyncio
    async def test_linear_chat_returns_service_response(
        self, async_client, monkeypatch, mock_student_user
    ):
        """
        Router should:
        - delegate to `SimulationService.process_chat_message`
        - surface the DTO returned by the service.
        """

        async def override_get_current_user():
            return mock_student_user

        app.dependency_overrides[get_current_user] = override_get_current_user

        class DummySimulationService:
            def __init__(self, db):
                self.db = db

            async def process_chat_message(
                self,
                user_id: int,
                user_progress_id: int,
                message: str,
                scene_id: int | None = None,
            ) -> SimulationChatResponse:
                assert user_id == mock_student_user.id
                assert user_progress_id == 1
                assert message == "Hello"
                return SimulationChatResponse(
                    message="Hi from service",
                    scene_id=scene_id or 5,
                    scene_completed=False,
                    persona_name="System",
                    persona_id=None,
                    turn_count=1,
                )

        import modules.simulation.router as simulation_router

        monkeypatch.setattr(simulation_router, "SimulationService", DummySimulationService)

        try:
            payload = {
                "user_progress_id": 1,
                "message": "Hello",
                "scene_id": 5,
            }
            response = await async_client.post("/api/simulation/linear-chat", json=payload)

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["message"] == "Hi from service"
            assert data["scene_id"] == 5
            assert data["turn_count"] == 1
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_linear_chat_maps_forbidden_and_not_found(
        self, async_client, monkeypatch, mock_student_user
    ):
        """
        Verify architecture rule: routers map domain exceptions to HTTP codes.
        - `NotFoundError` → 404
        - `ForbiddenError` → 403
        """

        async def override_get_current_user():
            return mock_student_user

        app.dependency_overrides[get_current_user] = override_get_current_user

        class FailingService:
            def __init__(self, db):
                self.db = db

            call_count = 0

            async def process_chat_message(self, user_id, user_progress_id, message, scene_id=None):
                # First call: NotFoundError, second: ForbiddenError
                if FailingService.call_count == 0:
                    FailingService.call_count += 1
                    raise NotFoundError("User progress not found")
                raise ForbiddenError("Access denied")

        import modules.simulation.router as simulation_router

        monkeypatch.setattr(simulation_router, "SimulationService", FailingService)

        try:
            payload = {"user_progress_id": 1, "message": "Hello"}

            # NotFoundError → 404
            resp1 = await async_client.post("/api/simulation/linear-chat", json=payload)
            assert resp1.status_code == status.HTTP_404_NOT_FOUND

            # ForbiddenError → 403
            resp2 = await async_client.post("/api/simulation/linear-chat", json=payload)
            assert resp2.status_code == status.HTTP_403_FORBIDDEN
        finally:
            app.dependency_overrides.clear()


class TestLinearChatStreamEndpoint:
    """Tests for POST /api/simulation/linear-chat-stream (SSE streaming)."""

    @pytest.mark.asyncio
    async def test_linear_chat_stream_uses_streaming_response(
        self, async_client, monkeypatch, mock_student_user
    ):
        """
        Router should wrap `SimulationService.stream_chat_message` in a `StreamingResponse`
        with `text/event-stream` media type (per architecture: router handles HTTP concerns).
        """

        async def override_get_current_user():
            return mock_student_user

        app.dependency_overrides[get_current_user] = override_get_current_user

        async def fake_stream_chat_message(
            user_id: int,
            user_progress_id: int,
            message: str,
            scene_id: int | None = None,
        ) -> AsyncGenerator[str, None]:
            yield 'data: {"message": "chunk-1"}\n\n'
            yield 'data: {"message": "chunk-2"}\n\n'

        class DummySimulationService:
            def __init__(self, db):
                self.db = db

            # Return an async generator
            async def stream_chat_message(self, *args, **kwargs):
                async for chunk in fake_stream_chat_message(*args, **kwargs):
                    yield chunk

        import modules.simulation.router as simulation_router

        monkeypatch.setattr(simulation_router, "SimulationService", DummySimulationService)

        try:
            payload = {"user_progress_id": 1, "message": "Hello stream"}
            response = await async_client.post("/api/simulation/linear-chat-stream", json=payload)

            assert response.status_code == status.HTTP_200_OK
            # httpx accumulates the streamed body for tests; media type should match SSE
            assert response.headers["content-type"].startswith("text/event-stream")
            body = response.text
            assert "chunk-1" in body
            assert "chunk-2" in body
        finally:
            app.dependency_overrides.clear()


class TestReadEndpoints:
    """Tests for GET /scenes/{id}, /progress/{id}, and /grade endpoints."""

    @pytest.mark.asyncio
    async def test_get_scene_by_id_delegates_to_progress_service(
        self, async_client, monkeypatch, mock_student_user
    ):
        """Router should call `SimulationService.get_scene_by_id` and return its DTO."""

        async def override_get_current_user():
            return mock_student_user

        app.dependency_overrides[get_current_user] = override_get_current_user

        class DummySimulationService:
            def __init__(self, db):
                self.db = db

            def get_scene_by_id(self, scene_id: int, user_id: int) -> SimulationSceneResponse:
                assert scene_id == 123
                assert user_id == mock_student_user.id
                return SimulationSceneResponse(
                    id=scene_id,
                    simulation_id=99,
                    title="Scene Title",
                    description="Scene description",
                    scene_order=1,
                    personas=[],
                )

        import modules.simulation.router as simulation_router

        monkeypatch.setattr(simulation_router, "SimulationService", DummySimulationService)

        try:
            response = await async_client.get("/api/simulation/scenes/123")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["id"] == 123
            assert data["simulation_id"] == 99
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_user_progress_delegates_to_progress_service(
        self, async_client, monkeypatch, mock_student_user
    ):
        """Router should call `SimulationService.get_user_progress` and return its DTO."""

        async def override_get_current_user():
            return mock_student_user

        app.dependency_overrides[get_current_user] = override_get_current_user

        class DummySimulationService:
            def __init__(self, db):
                self.db = db

            def get_user_progress(self, user_progress_id: int, user_id: int) -> UserProgressResponse:
                assert user_progress_id == 5
                assert user_id == mock_student_user.id
                return UserProgressResponse(
                    id=user_progress_id,
                    user_id=user_id,
                    simulation_id=77,
                    simulation_status="in_progress",
                    scenes_completed=[],
                )

        import modules.simulation.router as simulation_router

        monkeypatch.setattr(simulation_router, "SimulationService", DummySimulationService)

        try:
            response = await async_client.get("/api/simulation/progress/5")
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["id"] == 5
            assert data["simulation_id"] == 77
            assert data["simulation_status"] == "in_progress"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_simulation_grading_delegates_to_grading_service(
        self, async_client, monkeypatch, mock_student_user
    ):
        """Router should call `SimulationService.get_simulation_grading` and return grading data."""

        async def override_get_current_user():
            return mock_student_user

        app.dependency_overrides[get_current_user] = override_get_current_user

        class DummySimulationService:
            def __init__(self, db):
                self.db = db

            async def get_simulation_grading(self, user_progress_id: int, user_id: int) -> Dict[str, Any]:
                assert user_progress_id == 9
                assert user_id == mock_student_user.id
                return {
                    "score": 0.95,
                    "feedback": "Excellent performance",
                }

        import modules.simulation.router as simulation_router

        monkeypatch.setattr(simulation_router, "SimulationService", DummySimulationService)

        try:
            response = await async_client.get("/api/simulation/grade", params={"user_progress_id": 9})
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["score"] == 0.95
            assert "Excellent" in data["feedback"]
        finally:
            app.dependency_overrides.clear()


class TestSaveMessageEndpoint:
    """Tests for POST /api/simulation/save-message."""

    @pytest.mark.asyncio
    async def test_save_message_delegates_to_service_and_returns_payload(
        self, async_client, monkeypatch, mock_student_user
    ):
        """Router should call `SimulationService.save_message` and return its result."""

        async def override_get_current_user():
            return mock_student_user

        app.dependency_overrides[get_current_user] = override_get_current_user

        class DummySimulationService:
            def __init__(self, db):
                self.db = db

            def save_message(
                self,
                user_id: int,
                user_progress_id: int,
                scene_id: int,
                sender_name: str,
                message_content: str,
                message_type: str,
            ) -> Dict[str, Any]:
                assert user_id == mock_student_user.id
                assert user_progress_id == 3
                assert scene_id == 7
                assert sender_name == "System"
                assert message_content == "Hello"
                assert message_type == "system"
                return {"success": True, "message_id": 123, "message_order": 1}

        import modules.simulation.router as simulation_router

        monkeypatch.setattr(simulation_router, "SimulationService", DummySimulationService)

        try:
            payload = {
                "user_progress_id": 3,
                "scene_id": 7,
                "sender_name": "System",
                "message_content": "Hello",
                "message_type": "system",
            }
            response = await async_client.post("/api/simulation/save-message", json=payload)
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is True
            assert data["message_id"] == 123
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_save_message_maps_not_found_and_forbidden(
        self, async_client, monkeypatch, mock_student_user
    ):
        """
        Verify architecture rule: routers map domain exceptions to HTTP codes.
        - `NotFoundError` → 404
        - `ForbiddenError` → 403
        """

        async def override_get_current_user():
            return mock_student_user

        app.dependency_overrides[get_current_user] = override_get_current_user

        class FailingService:
            def __init__(self, db):
                self.db = db
                self.call_count = 0

            def save_message(self, user_id, user_progress_id, scene_id,
                             sender_name, message_content, message_type,
                             session_id=None):
                if self.call_count == 0:
                    self.call_count += 1
                    raise NotFoundError("Scene not found")
                raise ForbiddenError("scene_id does not belong to this simulation")

        import modules.simulation.router as simulation_router

        monkeypatch.setattr(simulation_router, "SimulationService", FailingService)

        try:
            payload = {
                "user_progress_id": 3,
                "scene_id": 7,
                "sender_name": "System",
                "message_content": "Hello",
                "message_type": "system",
            }

            # NotFoundError → 404
            resp1 = await async_client.post("/api/simulation/save-message", json=payload)
            assert resp1.status_code == status.HTTP_404_NOT_FOUND
            assert "Scene not found" in resp1.json()["detail"]

            # ForbiddenError → 403
            resp2 = await async_client.post("/api/simulation/save-message", json=payload)
            assert resp2.status_code == status.HTTP_403_FORBIDDEN
            assert "does not belong" in resp2.json()["detail"]
        finally:
            app.dependency_overrides.clear()
