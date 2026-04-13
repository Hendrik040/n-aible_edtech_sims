"""
PDF processing pipeline — stubbed for backend_v2.

The original implementation drove persona/scene extraction and image
generation via `.ai_extraction_service` and `.image_generation_service`, both
of which relied on LangChain and have been removed during the Agent SDK
rewrite. This module retains the class surface so that other modules can
import `PDFProcessingPipeline` and `get_pipeline`, but every entry point
raises `NotImplementedError` until the pipeline is rebuilt.
"""
import logging
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session
from fastapi import UploadFile

from common.db.models import User

from .parser_service import parser_service
from .repository import get_repository
from .progress_service import progress_manager  # noqa: F401 — re-exported for callers

logger = logging.getLogger(__name__)


_PIPELINE_STUB_DETAIL = (
    "PDF processing pipeline is not yet available in backend_v2. The AI "
    "extraction and image generation services are being rebuilt on top of "
    "the Claude Agent SDK."
)


class PDFProcessingPipeline:
    """Stub pipeline for orchestrating PDF processing.

    The real implementation will be reintroduced by a later rewrite ticket.
    """

    def __init__(self, db: Session, current_user: Optional[User] = None):
        self.db = db
        self.current_user = current_user
        self.repository = get_repository(db)
        self.parser = parser_service

    async def process_fast_autofill(self, file: UploadFile) -> Dict[str, Any]:
        raise NotImplementedError(_PIPELINE_STUB_DETAIL)

    async def process_full_with_progress(
        self,
        file: UploadFile,
        session_id: str,
        context_files: Optional[list] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError(_PIPELINE_STUB_DETAIL)

    async def process_full(
        self,
        file: UploadFile,
        context_files: Optional[list] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError(_PIPELINE_STUB_DETAIL)


def get_pipeline(db: Session, current_user: Optional[User] = None) -> PDFProcessingPipeline:
    """Return a pipeline instance."""
    return PDFProcessingPipeline(db, current_user)
