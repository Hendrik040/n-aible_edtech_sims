"""
Daytona Sandbox Service for code execution in simulations.

Manages the lifecycle of Daytona sandboxes — one sandbox per student
simulation session. Uses the async Daytona SDK (AsyncDaytona) so all
methods are natively async with no run_in_executor needed.

Responsibilities:
- Create a sandbox when a student starts a code-enabled simulation
- Execute student code inside the sandbox and return output
- Upload data files (CSVs, etc.) into the sandbox at scene start
- Tear down the sandbox when the simulation ends or times out
"""

import asyncio
import logging
import shlex
import uuid
from typing import Any, Dict, List, Optional

from common.config import get_settings

logger = logging.getLogger(__name__)

# Maximum characters returned from code execution output
MAX_OUTPUT_LENGTH = 5000


class SandboxService:
    """Manages Daytona sandboxes for code execution in simulations."""

    def __init__(self):
        """Initialize the sandbox service, connecting to Daytona if an API key is configured."""
        settings = get_settings()
        self.enabled = bool(settings.daytona_api_key)

        if self.enabled:
            from daytona_sdk import AsyncDaytona, DaytonaConfig

            config_kwargs: Dict[str, Any] = {"api_key": settings.daytona_api_key}
            if settings.daytona_api_url:
                config_kwargs["api_url"] = settings.daytona_api_url
            if settings.daytona_target:
                config_kwargs["target"] = settings.daytona_target

            self.daytona = AsyncDaytona(DaytonaConfig(**config_kwargs))
            logger.info("[DAYTONA] Sandbox service initialized")
        else:
            self.daytona = None
            logger.warning(
                "[DAYTONA] No API key configured — sandbox features disabled"
            )

    def _get_sandbox_image(self):
        """
        Build the declarative Image with pre-installed dependencies.

        Uses the Daytona SDK's declarative Image builder to bake packages
        into the sandbox snapshot at creation time (no runtime pip install).

        Includes both Python 3.12 and R 4.x runtimes so that code challenge
        scenes can use either language within the same sandbox.
        """
        from daytona_sdk import Image

        return (
            Image.base("python:3.12-slim")
            .run_commands(
                "apt-get update && apt-get install -y --no-install-recommends r-base && rm -rf /var/lib/apt/lists/*",
                'Rscript -e "install.packages(c(\'dplyr\', \'ggplot2\', \'readr\'), repos=\'https://cloud.r-project.org\')"',
            )
            .pip_install(["pandas", "numpy", "matplotlib", "openpyxl"])
        )

    async def create_sandbox(self, session_label: str = "") -> Optional[str]:
        """
        Create a new Daytona sandbox for a student session.

        Returns the sandbox_id string, or None if Daytona is not enabled.

        - language="python" gives us a Python-ready environment
        - auto_stop_interval=60 (minutes) stops the sandbox after idle
        - auto_archive_interval=120 archives after 2h
        - auto_delete_interval=1440 deletes after 24h
        """
        if not self.enabled:
            logger.warning("[DAYTONA] Cannot create sandbox — service disabled")
            return None

        from daytona_sdk import CreateSandboxFromImageParams

        try:
            params = CreateSandboxFromImageParams(
                image=self._get_sandbox_image(),
                language="python",
                auto_stop_interval=60,
                auto_archive_interval=120,
                auto_delete_interval=1440,
            )
            sandbox = await self.daytona.create(
                params,
                timeout=120,
                on_snapshot_create_logs=lambda chunk: logger.info(f"[DAYTONA_BUILD] {chunk.rstrip()}"),
            )
            logger.info(
                f"[DAYTONA] Created sandbox {sandbox.id} for session: {session_label}"
            )
            # Pre-import common libraries so students don't have to
            try:
                await sandbox.code_interpreter.run_code(
                    "import pandas as pd\n"
                    "import numpy as np\n"
                    "import matplotlib\n"
                    "matplotlib.use('Agg')\n"
                    "import matplotlib.pyplot as plt\n"
                )
                logger.info(f"[DAYTONA] Pre-imported pandas/numpy/matplotlib in sandbox {sandbox.id}")
            except Exception as init_err:
                logger.warning(f"[DAYTONA] Pre-import failed (non-fatal): {init_err}")
            return sandbox.id
        except Exception as e:
            logger.error(f"[DAYTONA] Sandbox creation failed: {e}")
            return None

    async def _ensure_sandbox_running(self, sandbox_id: str) -> Dict[str, Any]:
        """
        Fetch the sandbox and ensure it is in the 'started' state before use.

        Returns a dict with keys:
          - "sandbox": the AsyncSandbox object (if ready), or None
          - "error": error string if the sandbox cannot be made ready, or None
          - "sandbox_state": the current state string (useful for frontend UX)
          - "restarted": True if the sandbox was woken from stopped/error
        """
        sandbox = await self.daytona.get(sandbox_id)

        # SandboxState is a StrEnum whose __eq__ compares against plain strings
        # (the SDK itself does `while self.state != "started"`).
        # Do NOT use str(sandbox.state) — that returns "SandboxState.STARTED", not "started".
        state = sandbox.state  # compare directly with string literals below

        if state == "started":
            return {"sandbox": sandbox, "error": None, "sandbox_state": "started", "restarted": False}

        if state == "stopped":
            # Stopped sandboxes restart quickly (seconds) — safe to do inline
            logger.info(f"[DAYTONA] Sandbox {sandbox_id} is stopped — starting inline")
            await sandbox.start(timeout=90)
            logger.info(f"[DAYTONA] Sandbox {sandbox_id} started successfully")
            return {"sandbox": sandbox, "error": None, "sandbox_state": "started", "restarted": True}

        if state == "archived":
            # Archived sandboxes can take minutes to restore from object storage.
            # Return immediately so the caller can fire a background task and let
            # the frontend poll /sandbox-state until it's ready.
            logger.info(f"[DAYTONA] Sandbox {sandbox_id} is archived — needs async start")
            return {
                "sandbox": None,
                "error": "sandbox_archived",
                "sandbox_state": "archived",
                "restarted": False,
            }

        if state == "error":
            if sandbox.recoverable:
                logger.info(f"[DAYTONA] Sandbox {sandbox_id} in recoverable error — recovering")
                await sandbox.recover(timeout=90)
                logger.info(f"[DAYTONA] Sandbox {sandbox_id} recovered successfully")
                return {"sandbox": sandbox, "error": None, "sandbox_state": "started", "restarted": True}
            else:
                logger.error(f"[DAYTONA] Sandbox {sandbox_id} in non-recoverable error: {sandbox.error_reason}")
                return {
                    "sandbox": None,
                    "error": "sandbox_error_unrecoverable",
                    "sandbox_state": "error",
                    "restarted": False,
                }

        # destroyed / deleted / unknown — must recreate
        logger.warning(f"[DAYTONA] Sandbox {sandbox_id} is '{state}' — cannot restart")
        return {
            "sandbox": None,
            "error": "sandbox_destroyed",
            "sandbox_state": "destroyed",
            "restarted": False,
        }

    def _is_transient_sandbox_error(self, error: Exception) -> bool:
        """Check if an error is a transient sandbox connectivity issue (e.g. WebSocket rejection)."""
        msg = str(error).lower()
        return any(keyword in msg for keyword in [
            "websocket", "http 400", "connection refused",
            "connect call failed", "server rejected",
        ])

    async def _run_code_with_retry(self, sandbox, sandbox_id: str, code: str, was_restarted: bool):
        """
        Attempt to run code, retrying once on transient errors.

        After a sandbox restart the code interpreter WebSocket may not be
        immediately reachable (HTTP 400 / connection refused). A single
        retry with a short delay handles this race condition.
        """
        max_attempts = 2 if was_restarted else 1
        last_error: Optional[Exception] = None

        for attempt in range(max_attempts):
            try:
                if attempt > 0:
                    logger.info(f"[DAYTONA] Retry {attempt} for sandbox {sandbox_id} after transient error")
                    await asyncio.sleep(2)
                return await sandbox.code_interpreter.run_code(code)
            except Exception as e:
                last_error = e
                if attempt < max_attempts - 1 and self._is_transient_sandbox_error(e):
                    continue
                raise

        raise last_error  # pragma: no cover — loop always raises or returns

    async def execute_code(self, sandbox_id: str, code: str) -> Dict[str, Any]:
        """
        Execute Python code in a sandbox using the stateful code interpreter.

        Returns {"success": bool, "output": str, "error": str | None, "sandbox_state": str | None}

        If the sandbox is stopped or archived it is automatically restarted before
        execution. Uses sandbox.code_interpreter.run_code() which runs in a shared
        default context — variables, imports, and functions persist between calls
        within the same sandbox. Output is truncated to MAX_OUTPUT_LENGTH chars.

        Transient WebSocket errors (HTTP 400, connection refused) after a restart
        are retried once. If the sandbox is truly unreachable the frontend receives
        sandbox_state="stopped" so it can poll and retry via /sandbox-state.
        """
        if not self.enabled:
            return {
                "success": False,
                "output": "",
                "error": "Code execution service is not available",
                "sandbox_state": None,
            }

        try:
            wake = await self._ensure_sandbox_running(sandbox_id)
            if wake["error"]:
                return {
                    "success": False,
                    "output": "",
                    "error": wake["error"],
                    "sandbox_state": wake["sandbox_state"],
                }
            sandbox = wake["sandbox"]
            result = await self._run_code_with_retry(
                sandbox, sandbox_id, code, was_restarted=wake.get("restarted", False),
            )

            stdout = result.stdout or ""
            stderr = result.stderr or ""
            error = result.error

            if error:
                # Include stderr in the error message if it carries additional context
                error_text = f"{error.name}: {error.value}" if error.name else str(error.value)
                if stderr:
                    error_text = f"{error_text}\n{stderr}"
                if len(error_text) > MAX_OUTPUT_LENGTH:
                    error_text = error_text[:MAX_OUTPUT_LENGTH] + "\n... (truncated)"
                return {
                    "success": False,
                    "output": stdout,
                    "error": error_text,
                    "sandbox_state": "started",
                }

            output_text = stdout
            if stderr:
                output_text = output_text + ("\n" if output_text else "") + stderr
            if len(output_text) > MAX_OUTPUT_LENGTH:
                output_text = output_text[:MAX_OUTPUT_LENGTH] + "\n... (truncated)"
            return {
                "success": True,
                "output": output_text,
                "error": None,
                "sandbox_state": "started",
            }
        except Exception as e:
            logger.error(f"[DAYTONA] Code execution failed in sandbox {sandbox_id}: {e}")
            # Transient connectivity errors (WebSocket HTTP 400, connection refused)
            # should be surfaced as a recoverable "stopped" state so the frontend
            # can poll /sandbox-state and auto-retry instead of showing a raw error.
            if self._is_transient_sandbox_error(e):
                return {
                    "success": False,
                    "output": "",
                    "error": "sandbox_not_ready",
                    "sandbox_state": "stopped",
                }
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "sandbox_state": None,
            }

    async def execute_r_code(self, sandbox_id: str, code: str) -> Dict[str, Any]:
        """
        Execute R code in a sandbox using Daytona's process execution API.

        Daytona's code_interpreter only supports Python/JS/TS, so R code is
        written to a temp file and executed via ``Rscript``.

        Returns the same dict shape as execute_code() for frontend compatibility.
        """
        if not self.enabled:
            return {
                "success": False,
                "output": "",
                "error": "Code execution service is not available",
                "sandbox_state": None,
            }

        try:
            wake = await self._ensure_sandbox_running(sandbox_id)
            if wake["error"]:
                return {
                    "success": False,
                    "output": "",
                    "error": wake["error"],
                    "sandbox_state": wake["sandbox_state"],
                }
            sandbox = wake["sandbox"]

            # Write code to a unique temp file to avoid races between concurrent executions
            tmp_path = f"/tmp/_user_code_{uuid.uuid4().hex[:8]}.R"
            await sandbox.fs.upload_file(code.encode("utf-8"), tmp_path)
            try:
                proc = await sandbox.process.exec(
                    f"Rscript {shlex.quote(tmp_path)}", timeout=120
                )
            finally:
                # Clean up temp file (best-effort, ignore errors)
                try:
                    await sandbox.process.exec(
                        f"rm -f {shlex.quote(tmp_path)}", timeout=5
                    )
                except Exception:
                    pass

            stdout = getattr(proc, "stdout", "") or ""
            stderr = getattr(proc, "stderr", "") or ""
            exit_code = getattr(proc, "exit_code", None)

            if exit_code and exit_code != 0:
                error_text = stderr or "R script exited with a non-zero status"
                if len(error_text) > MAX_OUTPUT_LENGTH:
                    error_text = error_text[:MAX_OUTPUT_LENGTH] + "\n... (truncated)"
                return {
                    "success": False,
                    "output": stdout[:MAX_OUTPUT_LENGTH] if stdout else "",
                    "error": error_text,
                    "sandbox_state": "started",
                }

            output_text = stdout
            if stderr:
                output_text = output_text + ("\n" if output_text else "") + stderr
            if len(output_text) > MAX_OUTPUT_LENGTH:
                output_text = output_text[:MAX_OUTPUT_LENGTH] + "\n... (truncated)"
            return {
                "success": True,
                "output": output_text,
                "error": None,
                "sandbox_state": "started",
            }
        except Exception as e:
            logger.error(f"[DAYTONA] R code execution failed in sandbox {sandbox_id}: {e}")
            if self._is_transient_sandbox_error(e):
                return {
                    "success": False,
                    "output": "",
                    "error": "sandbox_not_ready",
                    "sandbox_state": "stopped",
                }
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "sandbox_state": None,
            }

    async def wake_sandbox(self, sandbox_id: str) -> bool:
        """
        Start an archived or stopped sandbox in the background.

        Called as a FastAPI BackgroundTask when execute_code detects the sandbox
        is archived and cannot be restarted inline. Returns True on success.
        """
        if not self.enabled:
            return False
        try:
            sandbox = await self.daytona.get(sandbox_id)
            if sandbox.state != "started":
                logger.info(f"[DAYTONA] Background wake: starting sandbox {sandbox_id}")
                await sandbox.start(timeout=300)
                logger.info(f"[DAYTONA] Background wake: sandbox {sandbox_id} is ready")
            return True
        except Exception as e:
            logger.error(f"[DAYTONA] Background wake failed for sandbox {sandbox_id}: {e}")
            return False

    async def upload_file(
        self, sandbox_id: str, file_path: str, content: bytes
    ) -> bool:
        """
        Upload a data file (CSV, JSON, etc.) into the sandbox filesystem.

        Used to pre-load datasets for code challenge scenes.
        file_path is the path INSIDE the sandbox, e.g. "/home/daytona/data/financials.csv"
        """
        if not self.enabled:
            logger.warning("[DAYTONA] Cannot upload file — service disabled")
            return False

        try:
            sandbox = await self.daytona.get(sandbox_id)
            await sandbox.fs.upload_file(content, file_path)
            logger.info(f"[DAYTONA] Uploaded {file_path} to sandbox {sandbox_id}")
            return True
        except Exception as e:
            logger.error(
                f"[DAYTONA] File upload to sandbox {sandbox_id} failed: {e}"
            )
            return False

    async def upload_scene_data_files(
        self, sandbox_id: str, data_files: List[Dict[str, Any]]
    ) -> int:
        """
        Download data files from S3 and upload them into the sandbox.

        Args:
            sandbox_id: Daytona sandbox ID
            data_files: List of dicts with 's3_key' and 'filename' from scene.data_files JSON

        Returns:
            Number of files successfully uploaded.
        """
        if not self.enabled or not data_files:
            return 0

        from common.services.s3_service import s3_service

        uploaded = 0
        for file_info in data_files:
            s3_key = file_info.get("s3_key")
            filename = file_info.get("filename", "data.csv")
            if not s3_key:
                continue
            try:
                content = await s3_service.download_file(s3_key)
                if content is None:
                    logger.warning(f"[DAYTONA] S3 download returned None for {s3_key}")
                    continue
                sandbox_path = f"/home/daytona/data/{filename}"
                success = await self.upload_file(sandbox_id, sandbox_path, content)
                if success:
                    uploaded += 1
            except Exception as e:
                logger.error(f"[DAYTONA] Failed to transfer {s3_key} to sandbox: {e}")
        return uploaded

    async def delete_sandbox(self, sandbox_id: str) -> bool:
        """Tear down a sandbox. Called when simulation completes or times out."""
        if not self.enabled:
            return False

        try:
            sandbox = await self.daytona.get(sandbox_id)
            await self.daytona.delete(sandbox)
            logger.info(f"[DAYTONA] Deleted sandbox {sandbox_id}")
            return True
        except Exception as e:
            logger.error(f"[DAYTONA] Failed to delete sandbox {sandbox_id}: {e}")
            return False


# Module-level singleton (follows s3_service / cache_service pattern)
sandbox_service = SandboxService()

__all__ = ["SandboxService", "sandbox_service"]
