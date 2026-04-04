"""
Tests for SandboxService — focused on transient error handling and retry logic.

Verifies that:
- Transient WebSocket/connection errors are correctly identified
- Code execution retries once after transient errors on restarted sandboxes
- Transient errors that persist are returned as recoverable "stopped" state
- Non-transient errors are returned with sandbox_state=None as before

These tests mock the Daytona SDK entirely and do not require the full
project-level dependencies.
"""

import asyncio
import sys
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

# Ensure backend is on sys.path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)


def _make_sandbox_service():
    """
    Build a SandboxService instance by mocking out __init__ and setting
    attributes directly. This avoids importing any project deps (FastAPI,
    SQLAlchemy, Pydantic settings, etc.).
    """
    # Stub the daytona_sdk module so the import inside the class doesn't fail
    daytona_stub = MagicMock()
    sys.modules.setdefault("daytona_sdk", daytona_stub)

    # Patch get_settings so importing sandbox_service doesn't blow up
    with patch.dict(sys.modules, {"common.config": MagicMock()}):
        # Force re-import so our patches take effect
        import importlib
        if "common.services.sandbox_service" in sys.modules:
            del sys.modules["common.services.sandbox_service"]

        with patch("common.config.get_settings", return_value=MagicMock(
            daytona_api_key="test-key", daytona_api_url="http://test", daytona_target=None,
        )):
            from common.services.sandbox_service import SandboxService

    # Bypass __init__ — create instance directly
    service = object.__new__(SandboxService)
    service.enabled = True
    service.daytona = AsyncMock()
    return service


@pytest.fixture
def sandbox_service():
    return _make_sandbox_service()


class TestIsTransientSandboxError:
    """Tests for _is_transient_sandbox_error classification."""

    def test_websocket_http_400(self, sandbox_service):
        err = Exception("server rejected WebSocket connection: HTTP 400")
        assert sandbox_service._is_transient_sandbox_error(err) is True

    def test_connection_refused(self, sandbox_service):
        err = Exception("Connect call failed ('127.0.0.1', 8080)")
        assert sandbox_service._is_transient_sandbox_error(err) is True

    def test_generic_websocket_error(self, sandbox_service):
        err = Exception("WebSocket handshake failed")
        assert sandbox_service._is_transient_sandbox_error(err) is True

    def test_server_rejected(self, sandbox_service):
        err = Exception("server rejected the request with code 400")
        assert sandbox_service._is_transient_sandbox_error(err) is True

    def test_non_transient_error(self, sandbox_service):
        err = Exception("SyntaxError: invalid syntax")
        assert sandbox_service._is_transient_sandbox_error(err) is False

    def test_permission_error(self, sandbox_service):
        err = Exception("Permission denied")
        assert sandbox_service._is_transient_sandbox_error(err) is False


class TestRunCodeWithRetry:
    """Tests for _run_code_with_retry retry logic."""

    @pytest.mark.asyncio
    async def test_succeeds_first_attempt(self, sandbox_service):
        """No retry needed when first attempt succeeds."""
        mock_sandbox = MagicMock()
        mock_result = SimpleNamespace(stdout="hello", stderr="", error=None)
        mock_sandbox.code_interpreter.run_code = AsyncMock(return_value=mock_result)

        result = await sandbox_service._run_code_with_retry(
            mock_sandbox, "sandbox-1", "print('hello')", was_restarted=False,
        )
        assert result.stdout == "hello"
        assert mock_sandbox.code_interpreter.run_code.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_transient_error_after_restart(self, sandbox_service):
        """Transient error is retried once when sandbox was just restarted."""
        mock_sandbox = MagicMock()
        mock_result = SimpleNamespace(stdout="ok", stderr="", error=None)

        call_count = 0

        async def mock_run_code(code):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("server rejected WebSocket connection: HTTP 400")
            return mock_result

        mock_sandbox.code_interpreter.run_code = mock_run_code

        # Patch asyncio.sleep to avoid actual delays
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await sandbox_service._run_code_with_retry(
                mock_sandbox, "sandbox-1", "print('ok')", was_restarted=True,
            )

        assert result.stdout == "ok"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_without_restart(self, sandbox_service):
        """Transient error is NOT retried when sandbox was NOT restarted."""
        mock_sandbox = MagicMock()
        mock_sandbox.code_interpreter.run_code = AsyncMock(
            side_effect=Exception("server rejected WebSocket connection: HTTP 400")
        )

        with pytest.raises(Exception, match="WebSocket"):
            await sandbox_service._run_code_with_retry(
                mock_sandbox, "sandbox-1", "print('hi')", was_restarted=False,
            )
        assert mock_sandbox.code_interpreter.run_code.call_count == 1

    @pytest.mark.asyncio
    async def test_non_transient_error_not_retried(self, sandbox_service):
        """Non-transient errors are raised immediately, no retry."""
        mock_sandbox = MagicMock()
        mock_sandbox.code_interpreter.run_code = AsyncMock(
            side_effect=Exception("SyntaxError: invalid syntax")
        )

        with pytest.raises(Exception, match="SyntaxError"):
            await sandbox_service._run_code_with_retry(
                mock_sandbox, "sandbox-1", "bad code", was_restarted=True,
            )
        assert mock_sandbox.code_interpreter.run_code.call_count == 1


class TestExecuteCodeTransientErrors:
    """Tests for execute_code handling of transient connectivity errors."""

    @pytest.mark.asyncio
    async def test_transient_error_returns_stopped_state(self, sandbox_service):
        """
        When sandbox reports 'started' but code execution hits a transient
        WebSocket error (after retry exhaustion), return sandbox_state='stopped'
        so the frontend can poll and retry.
        """
        mock_sandbox = MagicMock()
        sandbox_service._ensure_sandbox_running = AsyncMock(return_value={
            "sandbox": mock_sandbox,
            "error": None,
            "sandbox_state": "started",
            "restarted": False,
        })
        mock_sandbox.code_interpreter.run_code = AsyncMock(
            side_effect=Exception("server rejected WebSocket connection: HTTP 400")
        )

        result = await sandbox_service.execute_code("sandbox-1", "print('hello')")

        assert result["success"] is False
        assert result["sandbox_state"] == "stopped"
        assert result["error"] == "sandbox_not_ready"

    @pytest.mark.asyncio
    async def test_non_transient_error_returns_none_state(self, sandbox_service):
        """Non-transient errors still return sandbox_state=None (existing behavior)."""
        mock_sandbox = MagicMock()
        sandbox_service._ensure_sandbox_running = AsyncMock(return_value={
            "sandbox": mock_sandbox,
            "error": None,
            "sandbox_state": "started",
            "restarted": False,
        })
        mock_sandbox.code_interpreter.run_code = AsyncMock(
            side_effect=Exception("Some unexpected internal error")
        )

        result = await sandbox_service.execute_code("sandbox-1", "print('hello')")

        assert result["success"] is False
        assert result["sandbox_state"] is None
        assert "unexpected internal error" in result["error"]

    @pytest.mark.asyncio
    async def test_successful_execution_after_restart_retry(self, sandbox_service):
        """
        After a sandbox restart, transient error on first attempt is retried
        and succeeds on the second attempt.
        """
        mock_sandbox = MagicMock()
        sandbox_service._ensure_sandbox_running = AsyncMock(return_value={
            "sandbox": mock_sandbox,
            "error": None,
            "sandbox_state": "started",
            "restarted": True,
        })

        call_count = 0

        async def mock_run_code(code):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("server rejected WebSocket connection: HTTP 400")
            return SimpleNamespace(stdout="hello\n", stderr="", error=None)

        mock_sandbox.code_interpreter.run_code = mock_run_code

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await sandbox_service.execute_code("sandbox-1", "print('hello')")

        assert result["success"] is True
        assert result["output"] == "hello\n"
        assert result["sandbox_state"] == "started"

    @pytest.mark.asyncio
    async def test_disabled_service_returns_error(self, sandbox_service):
        """Disabled service returns appropriate error."""
        sandbox_service.enabled = False
        result = await sandbox_service.execute_code("sandbox-1", "print('hello')")
        assert result["success"] is False
        assert result["error"] == "Code execution service is not available"

    @pytest.mark.asyncio
    async def test_archived_sandbox_returns_archived_state(self, sandbox_service):
        """Archived sandbox returns sandbox_archived error for frontend polling."""
        sandbox_service._ensure_sandbox_running = AsyncMock(return_value={
            "sandbox": None,
            "error": "sandbox_archived",
            "sandbox_state": "archived",
            "restarted": False,
        })

        result = await sandbox_service.execute_code("sandbox-1", "print('hello')")

        assert result["success"] is False
        assert result["error"] == "sandbox_archived"
        assert result["sandbox_state"] == "archived"
