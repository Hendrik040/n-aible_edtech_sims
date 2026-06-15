"""
Publishing repository for data access.

Handles all database queries and operations for the publishing module.
"""

import logging
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_

from common.db.models import (
    Simulation, SimulationPersona, SimulationScene, SimulationFile,
    User, scene_personas
)

logger = logging.getLogger(__name__)


class PublishingRepository:
    """Repository for publishing data access."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_simulation_by_id(self, simulation_id: int) -> Optional[Simulation]:
        """Get simulation by ID."""
        return self.db.query(Simulation).filter(
            Simulation.id == simulation_id,
            Simulation.deleted_at.is_(None)
        ).first()
    
    def get_simulation_by_unique_id(self, unique_id: str) -> Optional[Simulation]:
        """Get simulation by unique ID."""
        return self.db.query(Simulation).filter(
            Simulation.unique_id == unique_id,
            Simulation.deleted_at.is_(None)
        ).first()
    
    def get_simulations_by_user(
        self,
        user_id: int,
        status: Optional[str] = None,
        include_drafts: bool = False
    ) -> List[Simulation]:
        """Get simulations by user with optional filtering."""
        query = self.db.query(Simulation).filter(
            Simulation.deleted_at.is_(None),
            Simulation.created_by == user_id
        )
        
        if status:
            if status == "active":
                query = query.filter(Simulation.is_draft == False)
            elif status == "draft":
                query = query.filter(
                    or_(
                        Simulation.is_draft == True,
                        Simulation.status == "creating"
                    )
                )
            elif status == "creating":
                query = query.filter(Simulation.status == "creating")
            elif status == "archived":
                query = query.filter(Simulation.status == "archived")
        
        if not status and not include_drafts:
            query = query.filter(Simulation.is_draft == False)
        
        return query.all()
    
    def get_draft_simulations(self, user_id: int) -> List[Simulation]:
        """Get draft simulations for user."""
        return self.db.query(Simulation).filter(
            Simulation.is_draft == True,
            Simulation.deleted_at.is_(None),
            Simulation.created_by == user_id
        ).all()
    
    def get_simulation_personas(self, simulation_id: int) -> List[SimulationPersona]:
        """Get personas for a simulation."""
        return self.db.query(SimulationPersona).filter(
            SimulationPersona.simulation_id == simulation_id,
            SimulationPersona.deleted_at.is_(None)
        ).all()
    
    def get_simulation_scenes(self, simulation_id: int) -> List[SimulationScene]:
        """Get scenes for a simulation."""
        return self.db.query(SimulationScene).filter(
            SimulationScene.simulation_id == simulation_id,
            SimulationScene.deleted_at.is_(None)
        ).order_by(SimulationScene.scene_order).all()
    
    def get_simulation_file(
        self,
        simulation_id: int,
        filename: str
    ) -> Optional[SimulationFile]:
        """Get simulation file by filename."""
        return self.db.query(SimulationFile).filter(
            SimulationFile.simulation_id == simulation_id,
            SimulationFile.filename == filename
        ).first()
    
    def create_or_update_simulation_file(
        self,
        simulation_id: int,
        filename: str,
        file_path: str,
        file_size: Optional[int] = None,
        file_type: Optional[str] = None
    ) -> SimulationFile:
        """Create or update simulation file."""
        existing = self.get_simulation_file(simulation_id, filename)
        
        if existing:
            existing.file_path = file_path
            if file_size:
                existing.file_size = file_size
            if file_type:
                existing.file_type = file_type
            existing.processing_status = "completed"
            existing.processed_at = datetime.utcnow()
            return existing
        else:
            file = SimulationFile(
                simulation_id=simulation_id,
                filename=filename,
                file_path=file_path,
                file_size=file_size or 0,
                file_type=file_type or "application/pdf",
                processing_status="completed",
                uploaded_at=datetime.utcnow(),
                processed_at=datetime.utcnow()
            )
            self.db.add(file)
            self.db.flush()
            return file
    
    def delete_simulation(self, simulation_id: int, user_id: Optional[int] = None) -> bool:
        """Soft delete a simulation."""
        simulation = self.get_simulation_by_id(simulation_id)
        if not simulation:
            return False

        # Ownership is mandatory: refuse anonymous deletes and non-owner deletes.
        # (Defense-in-depth; the route also requires authentication.)
        if not user_id or simulation.created_by != user_id:
            return False

        simulation.deleted_at = datetime.utcnow()
        if user_id:
            simulation.deleted_by = user_id
        self.db.add(simulation)
        self.db.commit()
        return True
