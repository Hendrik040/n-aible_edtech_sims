"""
Grading Materials API endpoints
Handles upload and management of grading materials (rubrics, references, criteria) for simulations
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import uuid
from datetime import datetime

from database.connection import get_db
from database.models import GradingMaterial, User, Scenario
from middleware.role_auth import require_professor
from services.grading_embedding_service import grading_embedding_service
from common.utils.debug_logging import debug_log

router = APIRouter(prefix="/professor", tags=["Grading Materials"])

@router.post("/simulations/{simulation_id}/grading-materials")
async def upload_grading_materials(
    simulation_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_professor)
):
    """
    Upload grading materials for a simulation
    Supports PDF, DOC, DOCX, TXT files
    """
    try:
        # Verify simulation exists and user has access
        simulation = db.query(Scenario).filter(
            Scenario.id == simulation_id,
            Scenario.created_by == current_user.id
        ).first()
        
        if not simulation:
            raise HTTPException(
                status_code=404, 
                detail="Simulation not found or access denied"
            )
        
        # Validate file
        allowed_extensions = {'.pdf', '.doc', '.docx', '.txt', '.md'}
        
        # Validate file type
        file_extension = os.path.splitext(file.filename)[1].lower()
        if file_extension not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"File type {file_extension} not supported. Allowed: {', '.join(allowed_extensions)}"
            )
        
        # Validate file size (max 10MB)
        file_size = 0
        content = await file.read()
        file_size = len(content)
        
        if file_size > 10 * 1024 * 1024:  # 10MB
            raise HTTPException(
                status_code=400,
                detail=f"File {file.filename} too large. Maximum size is 10MB"
            )
        
        # Extract text content based on file type
        text_content = await _extract_text_content(content, file_extension)
        
        if not text_content or len(text_content.strip()) < 50:
            raise HTTPException(
                status_code=400,
                detail=f"File {file.filename} contains insufficient text content"
            )
        
        # Create grading material record
        material = GradingMaterial(
            simulation_id=simulation_id,
            filename=file.filename,
            file_type=file_extension,
            file_size=file_size,
            original_content=text_content,
            processing_status="pending",
            uploaded_by=current_user.id
        )
        
        db.add(material)
        db.commit()
        db.refresh(material)
        
        # Add background task to process embeddings
        background_tasks.add_task(
            _process_grading_material_async,
            material.id,
            text_content,
            file.filename
        )
        
        uploaded_material = {
            "id": material.id,
            "filename": material.filename,
            "file_type": material.file_type,
            "file_size": material.file_size,
            "processing_status": material.processing_status,
            "uploaded_at": material.created_at.isoformat()
        }
        
        debug_log(f"[GRADING_MATERIALS] Uploaded material {material.filename} for simulation {simulation_id}")
        
        return {
            "message": f"Successfully uploaded grading material: {file.filename}",
            "material": uploaded_material,
            "simulation_id": simulation_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        debug_log(f"[GRADING_MATERIALS] Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to upload grading materials")

@router.get("/simulations/{simulation_id}/grading-materials")
async def get_grading_materials(
    simulation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_professor)
):
    """
    Get all grading materials for a simulation
    """
    try:
        # Verify simulation access
        simulation = db.query(Scenario).filter(
            Scenario.id == simulation_id,
            Scenario.created_by == current_user.id
        ).first()
        
        if not simulation:
            raise HTTPException(
                status_code=404, 
                detail="Simulation not found or access denied"
            )
        
        # Get grading materials
        materials = db.query(GradingMaterial).filter(
            GradingMaterial.simulation_id == simulation_id
        ).order_by(GradingMaterial.created_at.desc()).all()
        
        materials_data = []
        for material in materials:
            # Get chunk count
            chunk_count = len(material.chunks) if material.chunks else 0
            
            materials_data.append({
                "id": material.id,
                "filename": material.filename,
                "file_type": material.file_type,
                "file_size": material.file_size,
                "processing_status": material.processing_status,
                "chunk_count": chunk_count,
                "processing_log": material.processing_log,
                "uploaded_at": material.created_at.isoformat(),
                "updated_at": material.updated_at.isoformat()
            })
        
        return {
            "simulation_id": simulation_id,
            "materials": materials_data,
            "total_count": len(materials_data)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        debug_log(f"[GRADING_MATERIALS] Get materials error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve grading materials")

@router.delete("/grading-materials/{material_id}")
async def delete_grading_material(
    material_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_professor)
):
    """
    Delete a grading material
    """
    try:
        # Verify material exists and user has access
        material = db.query(GradingMaterial).filter(
            GradingMaterial.id == material_id,
            GradingMaterial.uploaded_by == current_user.id
        ).first()
        
        if not material:
            raise HTTPException(
                status_code=404, 
                detail="Grading material not found or access denied"
            )
        
        # Delete the material (cascades to chunks)
        db.delete(material)
        db.commit()
        
        debug_log(f"[GRADING_MATERIALS] Deleted material {material_id}")
        
        return {
            "message": "Grading material deleted successfully",
            "material_id": material_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        debug_log(f"[GRADING_MATERIALS] Delete error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete grading material")

@router.post("/grading-materials/{material_id}/reprocess")
async def reprocess_grading_material(
    material_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_professor)
):
    """
    Reprocess a grading material (regenerate embeddings)
    """
    try:
        # Verify material exists and user has access
        material = db.query(GradingMaterial).filter(
            GradingMaterial.id == material_id,
            GradingMaterial.uploaded_by == current_user.id
        ).first()
        
        if not material:
            raise HTTPException(
                status_code=404, 
                detail="Grading material not found or access denied"
            )
        
        if not material.original_content:
            raise HTTPException(
                status_code=400, 
                detail="No content available for processing"
            )
        
        # Clear existing chunks
        for chunk in material.chunks:
            db.delete(chunk)
        db.commit()
        
        # Add background task to reprocess
        background_tasks.add_task(
            _process_grading_material_async,
            material.id,
            material.original_content,
            material.filename
        )
        
        debug_log(f"[GRADING_MATERIALS] Queued reprocessing for material {material_id}")
        
        return {
            "message": "Grading material queued for reprocessing",
            "material_id": material_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        debug_log(f"[GRADING_MATERIALS] Reprocess error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to reprocess grading material")

async def _process_grading_material_async(material_id: int, content: str, filename: str):
    """
    Background task to process grading material embeddings
    """
    try:
        debug_log(f"[GRADING_MATERIALS] Processing material {material_id} in background")
        result = await grading_embedding_service.process_grading_material(
            material_id, content, filename
        )
        debug_log(f"[GRADING_MATERIALS] Background processing completed: {result}")
    except Exception as e:
        debug_log(f"[GRADING_MATERIALS] Background processing error: {str(e)}")

async def _extract_text_content(content: bytes, file_extension: str) -> str:
    """
    Extract text content from uploaded file
    """
    try:
        if file_extension == '.txt' or file_extension == '.md':
            return content.decode('utf-8', errors='ignore')
        
        elif file_extension == '.pdf':
            # For PDF files, we'll use a simple text extraction
            # In production, you might want to use PyPDF2 or pdfplumber
            try:
                import PyPDF2
                import io
                
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text
            except ImportError:
                # Fallback: return a placeholder
                return f"[PDF content from file - {len(content)} bytes]"
        
        elif file_extension in ['.doc', '.docx']:
            # For Word documents, we'll use a simple approach
            # In production, you might want to use python-docx
            try:
                import docx
                import io
                
                doc = docx.Document(io.BytesIO(content))
                text = ""
                for paragraph in doc.paragraphs:
                    text += paragraph.text + "\n"
                return text
            except ImportError:
                # Fallback: return a placeholder
                return f"[Word document content from file - {len(content)} bytes]"
        
        else:
            # Fallback for unknown types
            return content.decode('utf-8', errors='ignore')
            
    except Exception as e:
        debug_log(f"[GRADING_MATERIALS] Text extraction error: {str(e)}")
        return f"[Error extracting text from file: {str(e)}]"
