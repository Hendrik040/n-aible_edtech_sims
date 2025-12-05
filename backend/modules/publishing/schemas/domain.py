"""
Publishing domain models.

Internal domain objects (dataclasses) used within the publishing module.
These are NOT SQLAlchemy models (those are in common/db/models/publishing/).
These are NOT Pydantic schemas (those are in dto.py).
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class PDFMetadata:
    """Metadata for PDF file storage."""
    filename: str
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    wasabi_url: Optional[str] = None
    pdf_url: Optional[str] = None
    file_contents_base64: Optional[str] = None
    temp_pdf_url: Optional[str] = None
    needs_upload: bool = False


@dataclass
class ImageUploadInfo:
    """Information for image upload."""
    persona_id: Optional[int] = None
    scene_id: Optional[int] = None
    scenario_id: Optional[int] = None
    temp_url: Optional[str] = None
