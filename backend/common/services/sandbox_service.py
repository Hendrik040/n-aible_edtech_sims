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

import logging
from typing import Any, Dict, List, Optional

from common.config import get_settings

logger = logging.getLogger(__name__)

# Maximum characters returned from code execution output
MAX_OUTPUT_LENGTH = 5000


class SandboxService:
    """Manages Daytona sandboxes for code execution in simulations."""

    def __init__(self):
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

        Supported approaches (see DAYTONA_CODE_SANDBOX_IMPLEMENTATION_PLAN.md 1.3.1):
        - Image.debian_slim("3.12").pip_install(...)
        - Image.debian_slim("3.12").pip_install_from_requirements("requirements.txt")
        - Image.debian_slim("3.12").pip_install_from_pyproject("pyproject.toml")
        - Image.base("...").run_commands("apt-get ...").pip_install(...)
        """
        from daytona_sdk import Image

        return Image.debian_slim("3.12").pip_install(
            ["pandas", "numpy", "matplotlib", "openpyxl"]
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

    async def execute_code(self, sandbox_id: str, code: str) -> Dict[str, Any]:
        """
        Execute Python code in a sandbox using the stateful code interpreter.

        Returns {"success": bool, "output": str, "error": str | None}

        Uses sandbox.code_interpreter.run_code() which runs in a shared
        default context — variables, imports, and functions persist between
        calls within the same sandbox. Output is truncated to MAX_OUTPUT_LENGTH chars.
        """
        if not self.enabled:
            return {
                "success": False,
                "output": "",
                "error": "Code execution service is not available",
            }

        try:
            sandbox = await self.daytona.get(sandbox_id)
            result = await sandbox.code_interpreter.run_code(code)

            stdout = result.stdout or ""
            stderr = result.stderr or ""
            error = result.error

            if error:
                error_text = f"{error.name}: {error.value}" if error.name else str(error.value)
                if len(error_text) > MAX_OUTPUT_LENGTH:
                    error_text = error_text[:MAX_OUTPUT_LENGTH] + "\n... (truncated)"
                return {
                    "success": False,
                    "output": stdout,
                    "error": error_text,
                }

            output_text = stdout
            if len(output_text) > MAX_OUTPUT_LENGTH:
                output_text = output_text[:MAX_OUTPUT_LENGTH] + "\n... (truncated)"
            return {
                "success": True,
                "output": output_text,
                "error": None,
            }
        except Exception as e:
            logger.error(f"[DAYTONA] Code execution failed in sandbox {sandbox_id}: {e}")
            return {
                "success": False,
                "output": "",
                "error": str(e),
            }

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
