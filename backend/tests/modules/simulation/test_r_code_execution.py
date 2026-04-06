"""
Tests for R code execution support in SandboxService.

Verifies that:
- execute_r_code writes code to a temp file and invokes Rscript
- Successful R execution returns the same shape as Python execution
- R errors (non-zero exit code) are surfaced correctly
- Transient sandbox errors are classified as recoverable
- Disabled service returns appropriate error
- The sandbox image includes R installation commands
"""

import sys
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure backend is on sys.path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)


def _make_sandbox_service():
    """
    Build a SandboxService instance by mocking out __init__ and setting
    attributes directly. Avoids importing any project deps.
    """
    daytona_stub = MagicMock()
    sys.modules.setdefault("daytona_sdk", daytona_stub)

    with patch.dict(sys.modules, {"common.config": MagicMock()}):
        import importlib
        if "common.services.sandbox_service" in sys.modules:
            del sys.modules["common.services.sandbox_service"]

        with patch("common.config.get_settings", return_value=MagicMock(
            daytona_api_key="test-key", daytona_api_url="http://test", daytona_target=None,
        )):
            from common.services.sandbox_service import SandboxService

    service = object.__new__(SandboxService)
    service.enabled = True
    service.daytona = AsyncMock()
    return service


@pytest.fixture
def sandbox_service():
    return _make_sandbox_service()


class TestExecuteRCode:
    """Tests for execute_r_code method."""

    @pytest.mark.asyncio
    async def test_successful_r_execution(self, sandbox_service):
        """Successful R code produces success=True and stdout output."""
        mock_sandbox = MagicMock()
        mock_sandbox.fs.upload_file = AsyncMock()
        mock_sandbox.process.exec = AsyncMock(return_value=SimpleNamespace(
            exit_code=0, stdout="[1] 42\n", stderr="",
        ))
        sandbox_service._ensure_sandbox_running = AsyncMock(return_value={
            "sandbox": mock_sandbox,
            "error": None,
            "sandbox_state": "started",
            "restarted": False,
        })

        result = await sandbox_service.execute_r_code("sandbox-1", "cat(42)")

        assert result["success"] is True
        assert "[1] 42" in result["output"]
        assert result["error"] is None
        assert result["sandbox_state"] == "started"

        # Verify code was written to a unique temp file
        mock_sandbox.fs.upload_file.assert_called_once()
        call_args = mock_sandbox.fs.upload_file.call_args
        assert call_args[0][0] == b"cat(42)"
        tmp_path = call_args[0][1]
        assert tmp_path.startswith("/tmp/student_code_")
        assert tmp_path.endswith(".R")

        # Verify Rscript was invoked with the same unique path
        mock_sandbox.process.exec.assert_called_once()
        exec_cmd = mock_sandbox.process.exec.call_args[0][0]
        assert exec_cmd == f"Rscript {tmp_path}"

    @pytest.mark.asyncio
    async def test_r_execution_error(self, sandbox_service):
        """R errors (non-zero exit code) return success=False with stderr."""
        mock_sandbox = MagicMock()
        mock_sandbox.fs.upload_file = AsyncMock()
        mock_sandbox.process.exec = AsyncMock(return_value=SimpleNamespace(
            exit_code=1, stdout="", stderr="Error in foo : object 'x' not found\n",
        ))
        sandbox_service._ensure_sandbox_running = AsyncMock(return_value={
            "sandbox": mock_sandbox,
            "error": None,
            "sandbox_state": "started",
            "restarted": False,
        })

        result = await sandbox_service.execute_r_code("sandbox-1", "print(x)")

        assert result["success"] is False
        assert "object 'x' not found" in result["error"]
        assert result["sandbox_state"] == "started"

    @pytest.mark.asyncio
    async def test_r_execution_disabled_service(self, sandbox_service):
        """Disabled service returns appropriate error."""
        sandbox_service.enabled = False
        result = await sandbox_service.execute_r_code("sandbox-1", "cat(1)")
        assert result["success"] is False
        assert result["error"] == "Code execution service is not available"

    @pytest.mark.asyncio
    async def test_r_execution_sandbox_not_running(self, sandbox_service):
        """Archived sandbox returns the wake error."""
        sandbox_service._ensure_sandbox_running = AsyncMock(return_value={
            "sandbox": None,
            "error": "sandbox_archived",
            "sandbox_state": "archived",
            "restarted": False,
        })

        result = await sandbox_service.execute_r_code("sandbox-1", "cat(1)")
        assert result["success"] is False
        assert result["error"] == "sandbox_archived"
        assert result["sandbox_state"] == "archived"

    @pytest.mark.asyncio
    async def test_r_execution_transient_error(self, sandbox_service):
        """Transient sandbox errors return stopped state for frontend polling."""
        mock_sandbox = MagicMock()
        sandbox_service._ensure_sandbox_running = AsyncMock(return_value={
            "sandbox": mock_sandbox,
            "error": None,
            "sandbox_state": "started",
            "restarted": False,
        })
        mock_sandbox.fs.upload_file = AsyncMock(
            side_effect=Exception("server rejected WebSocket connection: HTTP 400")
        )

        result = await sandbox_service.execute_r_code("sandbox-1", "cat(1)")
        assert result["success"] is False
        assert result["sandbox_state"] == "stopped"
        assert result["error"] == "sandbox_not_ready"

    @pytest.mark.asyncio
    async def test_r_output_truncation(self, sandbox_service):
        """Long R output is truncated to MAX_OUTPUT_LENGTH."""
        mock_sandbox = MagicMock()
        mock_sandbox.fs.upload_file = AsyncMock()
        long_output = "x" * 6000
        mock_sandbox.process.exec = AsyncMock(return_value=SimpleNamespace(
            exit_code=0, stdout=long_output, stderr="",
        ))
        sandbox_service._ensure_sandbox_running = AsyncMock(return_value={
            "sandbox": mock_sandbox,
            "error": None,
            "sandbox_state": "started",
            "restarted": False,
        })

        result = await sandbox_service.execute_r_code("sandbox-1", "cat(rep('x', 6000))")
        assert result["success"] is True
        assert "... (truncated)" in result["output"]
        assert len(result["output"]) < 6000


class TestSandboxImageIncludesR:
    """Verify the sandbox image builder includes R installation."""

    def test_image_includes_r_base(self, sandbox_service):
        """The sandbox image should install r-base."""
        # Mock the Image class
        mock_image = MagicMock()
        mock_image.run_commands.return_value = mock_image
        mock_image.pip_install.return_value = mock_image

        with patch.dict(sys.modules, {"daytona_sdk": MagicMock()}):
            import importlib
            if "common.services.sandbox_service" in sys.modules:
                del sys.modules["common.services.sandbox_service"]

            with patch("common.config.get_settings", return_value=MagicMock(
                daytona_api_key="test-key", daytona_api_url="http://test", daytona_target=None,
            )):
                daytona_mod = sys.modules["daytona_sdk"]
                daytona_mod.Image.base.return_value = mock_image

                from common.services.sandbox_service import SandboxService
                service = object.__new__(SandboxService)
                service.enabled = True
                result = service._get_sandbox_image()

                # Image.base should be called with python base image
                daytona_mod.Image.base.assert_called_once()
                base_arg = daytona_mod.Image.base.call_args[0][0]
                assert "python" in base_arg

                # run_commands should include r-base installation
                run_commands_call = mock_image.run_commands.call_args
                commands = run_commands_call[0]
                r_install_found = any("r-base" in cmd for cmd in commands)
                assert r_install_found, "Image should install r-base"

                # pip_install should still include pandas/numpy/matplotlib
                pip_call = mock_image.pip_install.call_args[0][0]
                assert "pandas" in pip_call
                assert "numpy" in pip_call


class TestCodeExecutionRequestLanguage:
    """Verify CodeExecutionRequest DTO accepts language field."""

    def test_default_language_is_python(self):
        """Language defaults to 'python' when not specified."""
        with patch.dict(sys.modules, {"common.config": MagicMock()}):
            if "common.services.sandbox_service" in sys.modules:
                del sys.modules["common.services.sandbox_service"]
            if "modules.simulation.schemas.dto" in sys.modules:
                del sys.modules["modules.simulation.schemas.dto"]

            from modules.simulation.schemas.dto import CodeExecutionRequest
            req = CodeExecutionRequest(user_progress_id=1, code="print(1)", scene_id=1)
            assert req.language == "python"

    def test_language_r(self):
        """Language can be set to 'r'."""
        with patch.dict(sys.modules, {"common.config": MagicMock()}):
            if "modules.simulation.schemas.dto" in sys.modules:
                del sys.modules["modules.simulation.schemas.dto"]

            from modules.simulation.schemas.dto import CodeExecutionRequest
            req = CodeExecutionRequest(user_progress_id=1, code="cat(1)", scene_id=1, language="r")
            assert req.language == "r"

    def test_invalid_language_rejected(self):
        """Invalid language values are rejected by the DTO."""
        from pydantic import ValidationError
        with patch.dict(sys.modules, {"common.config": MagicMock()}):
            if "modules.simulation.schemas.dto" in sys.modules:
                del sys.modules["modules.simulation.schemas.dto"]

            from modules.simulation.schemas.dto import CodeExecutionRequest
            with pytest.raises(ValidationError):
                CodeExecutionRequest(user_progress_id=1, code="print(1)", scene_id=1, language="c++")

    def test_empty_code_rejected(self):
        """Empty code is rejected by the DTO."""
        from pydantic import ValidationError
        with patch.dict(sys.modules, {"common.config": MagicMock()}):
            if "modules.simulation.schemas.dto" in sys.modules:
                del sys.modules["modules.simulation.schemas.dto"]

            from modules.simulation.schemas.dto import CodeExecutionRequest
            with pytest.raises(ValidationError):
                CodeExecutionRequest(user_progress_id=1, code="", scene_id=1)

    def test_unique_temp_file_per_execution(self):
        """Each R execution should use a unique temp file path."""
        sandbox_service = _make_sandbox_service()
        mock_sandbox = MagicMock()
        mock_sandbox.fs.upload_file = AsyncMock()
        mock_sandbox.process.exec = AsyncMock(return_value=SimpleNamespace(
            exit_code=0, stdout="ok\n", stderr="",
        ))
        sandbox_service._ensure_sandbox_running = AsyncMock(return_value={
            "sandbox": mock_sandbox,
            "error": None,
            "sandbox_state": "started",
            "restarted": False,
        })

        import asyncio
        asyncio.get_event_loop().run_until_complete(sandbox_service.execute_r_code("s1", "cat(1)"))
        asyncio.get_event_loop().run_until_complete(sandbox_service.execute_r_code("s1", "cat(2)"))

        paths = [call[0][1] for call in mock_sandbox.fs.upload_file.call_args_list]
        assert len(paths) == 2
        assert paths[0] != paths[1], "Each execution should use a unique temp file path"
