"""PDF Processing router wiring."""
from fastapi import APIRouter
from modules.pdf_processing.router import router as pdf_processing_router

router = APIRouter()

# Include the PDF processing module router
router.include_router(pdf_processing_router, prefix="/api/pdf-processing", tags=["PDF Processing"])
