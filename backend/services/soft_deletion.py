"""
Soft Deletion Service
Handles soft deletion of scenarios and user progress archiving
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import json
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, text
from database.models import Scenario, UserProgress, User
from database.connection import get_db


class SoftDeletionService:
    """Service for handling soft deletion of scenarios and user progress"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def soft_delete_scenario(
        self, 
        scenario_id: int, 
        deleted_by: int, 
        reason: str = "User deletion"
    ) -> bool:
        """
        Soft delete a scenario by marking it as deleted
        
        Args:
            scenario_id: ID of scenario to delete
            deleted_by: ID of user performing deletion
            reason: Reason for deletion
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get the scenario
            scenario = self.db.query(Scenario).filter(
                Scenario.id == scenario_id,
                Scenario.deleted_at.is_(None)  # Only get non-deleted scenarios
            ).first()
            
            if not scenario:
                return False
            
            # Store scenario info before deletion
            scenario_title = scenario.title
            
            # Archive related user progress (soft delete only)
            self._soft_delete_user_progress_for_scenario(scenario_id, reason)
            
            # Soft delete the scenario
            scenario.deleted_at = datetime.utcnow()
            scenario.deleted_by = deleted_by
            scenario.deletion_reason = reason
            
            self.db.commit()
            
            return True
            
        except Exception as e:
            self.db.rollback()
            return False
    
    def _soft_delete_user_progress_for_scenario(self, scenario_id: int, reason: str):
        """Soft delete user progress for a deleted scenario"""
        try:
            # Get all user progress for this scenario
            user_progress_records = self.db.query(UserProgress).filter(
                UserProgress.scenario_id == scenario_id,
                UserProgress.archived_at.is_(None)  # Only get non-archived records
            ).all()
            
            for progress in user_progress_records:
                # Soft delete the record
                progress.archived_at = datetime.utcnow()
                progress.archived_reason = f"Scenario deleted: {reason}"
            
            
        except Exception as e:
            raise
    
    
    
    def _hard_delete_scenario(self, scenario_id: int):
        """Actually delete the scenario and all related records from the database"""
        try:
            # Delete related records first (in proper order to avoid foreign key violations)
            
            # 1. Delete scene-persona relationships
            self.db.execute(
                text("DELETE FROM scene_personas WHERE scene_id IN (SELECT id FROM scenario_scenes WHERE scenario_id = :scenario_id)"),
                {'scenario_id': scenario_id}
            )
            
            # 2. Delete conversation logs
            self.db.execute(
                text("DELETE FROM conversation_logs WHERE scene_id IN (SELECT id FROM scenario_scenes WHERE scenario_id = :scenario_id)"),
                {'scenario_id': scenario_id}
            )
            
            # 3. Delete scene progress
            self.db.execute(
                text("DELETE FROM scene_progress WHERE scene_id IN (SELECT id FROM scenario_scenes WHERE scenario_id = :scenario_id)"),
                {'scenario_id': scenario_id}
            )
            
            # 4. Delete session memory
            self.db.execute(
                text("DELETE FROM session_memory WHERE scene_id IN (SELECT id FROM scenario_scenes WHERE scenario_id = :scenario_id)"),
                {'scenario_id': scenario_id}
            )
            
            # 5. Delete conversation summaries
            self.db.execute(
                text("DELETE FROM conversation_summaries WHERE scene_id IN (SELECT id FROM scenario_scenes WHERE scenario_id = :scenario_id)"),
                {'scenario_id': scenario_id}
            )
            
            # 6. Delete agent sessions
            self.db.execute(
                text("DELETE FROM agent_sessions WHERE user_progress_id IN (SELECT id FROM user_progress WHERE scenario_id = :scenario_id)"),
                {'scenario_id': scenario_id}
            )
            
            # 7. Update user progress to remove foreign key references
            self.db.execute(
                text("UPDATE user_progress SET current_scene_id = NULL WHERE scenario_id = :scenario_id"),
                {'scenario_id': scenario_id}
            )
            
            # 8. Delete scenario personas
            self.db.execute(
                text("DELETE FROM scenario_personas WHERE scenario_id = :scenario_id"),
                {'scenario_id': scenario_id}
            )
            
            # 9. Delete scenario scenes
            self.db.execute(
                text("DELETE FROM scenario_scenes WHERE scenario_id = :scenario_id"),
                {'scenario_id': scenario_id}
            )
            
            # 10. Delete scenario files
            self.db.execute(
                text("DELETE FROM scenario_files WHERE scenario_id = :scenario_id"),
                {'scenario_id': scenario_id}
            )
            
            # 11. Delete scenario reviews
            self.db.execute(
                text("DELETE FROM scenario_reviews WHERE scenario_id = :scenario_id"),
                {'scenario_id': scenario_id}
            )
            
            # 12. Finally delete the scenario itself
            result = self.db.execute(
                text("DELETE FROM scenarios WHERE id = :scenario_id"),
                {'scenario_id': scenario_id}
            )
            
            deleted_count = result.rowcount
            
        except Exception as e:
            raise
    
    def get_active_scenarios(self, user_id: Optional[int] = None) -> List[Scenario]:
        """Get all active (non-deleted) scenarios"""
        query = self.db.query(Scenario).filter(Scenario.deleted_at.is_(None))
        
        if user_id:
            query = query.filter(Scenario.created_by == user_id)
        
        return query.all()
    
    def get_deleted_scenarios(self, user_id: Optional[int] = None) -> List[Scenario]:
        """Get all deleted scenarios"""
        query = self.db.query(Scenario).filter(Scenario.deleted_at.isnot(None))
        
        if user_id:
            query = query.filter(Scenario.created_by == user_id)
        
        return query.all()
    
    def restore_scenario(self, scenario_id: int, restored_by: int) -> bool:
        """Restore a soft-deleted scenario"""
        try:
            scenario = self.db.query(Scenario).filter(
                Scenario.id == scenario_id,
                Scenario.deleted_at.isnot(None)
            ).first()
            
            if not scenario:
                return False
            
            # Restore the scenario
            scenario.deleted_at = None
            scenario.deleted_by = None
            scenario.deletion_reason = None
            
            self.db.commit()
            return True
            
        except Exception as e:
            self.db.rollback()
            return False
    


def soft_delete_scenario_endpoint(scenario_id: int, user_id: int, reason: str = "User deletion"):
    """Endpoint helper for soft deleting a scenario"""
    from database.connection import get_db_session
    with get_db_session() as db:
        service = SoftDeletionService(db)
        return service.soft_delete_scenario(scenario_id, user_id, reason)
