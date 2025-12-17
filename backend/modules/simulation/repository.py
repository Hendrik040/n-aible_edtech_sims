"""
Simulation Repository.

Data access layer for simulation operations.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from common.db.models import (
    Simulation, SimulationScene, SimulationPersona, UserProgress, SceneProgress,
    ConversationLog, AgentSessions, SessionMemory, ConversationSummaries,
    StudentSimulationInstance, scene_personas
)


class SimulationRepository:
    """Repository for simulation data access."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_simulation_by_id(self, simulation_id: int) -> Optional[Simulation]:
        """Get simulation by ID."""
        return self.db.query(Simulation).filter(
            Simulation.id == simulation_id,
            Simulation.deleted_at.is_(None)
        ).first()
    
    def get_scenes_by_simulation_id(
        self, 
        simulation_id: int,
        eager_load_personas: bool = False
    ) -> List[SimulationScene]:
        """Get all scenes for a simulation, ordered by scene_order.
        
        Note: eager_load_personas parameter is ignored since personas are accessed
        via the association table through get_personas_for_scene() method.
        """
        query = self.db.query(SimulationScene)
        # Personas are accessed via get_personas_for_scene() using the scene_personas association table
        return query.filter(
            SimulationScene.simulation_id == simulation_id,
            SimulationScene.deleted_at.is_(None)
        ).order_by(SimulationScene.scene_order).all()
    
    def get_scene_by_id(self, scene_id: int) -> Optional[SimulationScene]:
        """Get scene by ID."""
        return self.db.query(SimulationScene).filter(
            SimulationScene.id == scene_id,
            SimulationScene.deleted_at.is_(None)
        ).first()
    
    def get_personas_by_simulation_id(
        self, 
        simulation_id: int,
        exclude_deleted: bool = True
    ) -> List[SimulationPersona]:
        """Get all personas for a simulation."""
        query = self.db.query(SimulationPersona).filter(
            SimulationPersona.simulation_id == simulation_id
        )
        if exclude_deleted:
            query = query.filter(SimulationPersona.deleted_at.is_(None))
        return query.all()
    
    def get_user_progress_by_id(
        self, 
        user_progress_id: int
    ) -> Optional[UserProgress]:
        """Get user progress by ID."""
        return self.db.query(UserProgress).filter(
            UserProgress.id == user_progress_id
        ).first()
    
    def get_user_progress_by_user_and_simulation(
        self,
        user_id: int,
        simulation_id: int
    ) -> List[UserProgress]:
        """Get all user progress for a user and simulation."""
        return self.db.query(UserProgress).filter(
            UserProgress.user_id == user_id,
            UserProgress.simulation_id == simulation_id
        ).all()
    
    def create_user_progress(
        self,
        user_id: int,
        simulation_id: int,
        current_scene_id: int,
        orchestrator_data: Dict[str, Any],
        simulation_status: str = "in_progress"
    ) -> UserProgress:
        """Create a new user progress record."""
        user_progress = UserProgress(
            user_id=user_id,
            simulation_id=simulation_id,
            current_scene_id=current_scene_id,
            orchestrator_data=orchestrator_data,
            simulation_status=simulation_status
        )
        self.db.add(user_progress)
        self.db.flush()
        return user_progress
    
    def delete_user_progress_and_related(self, user_progress_id: int) -> None:
        """Delete user progress and all related records."""
        # Delete related records
        self.db.query(SceneProgress).filter(
            SceneProgress.user_progress_id == user_progress_id
        ).delete()
        self.db.query(ConversationLog).filter(
            ConversationLog.user_progress_id == user_progress_id
        ).delete()
        self.db.query(AgentSessions).filter(
            AgentSessions.user_progress_id == user_progress_id
        ).delete()
        self.db.query(SessionMemory).filter(
            SessionMemory.user_progress_id == user_progress_id
        ).delete()
        self.db.query(ConversationSummaries).filter(
            ConversationSummaries.user_progress_id == user_progress_id
        ).delete()
        self.db.query(StudentSimulationInstance).filter(
            StudentSimulationInstance.user_progress_id == user_progress_id
        ).delete()
        
        # Delete user progress
        self.db.query(UserProgress).filter(
            UserProgress.id == user_progress_id
        ).delete()
    
    def get_scene_progress(
        self,
        user_progress_id: int,
        scene_id: int
    ) -> Optional[SceneProgress]:
        """Get scene progress for a user progress and scene."""
        return self.db.query(SceneProgress).filter(
            and_(
                SceneProgress.user_progress_id == user_progress_id,
                SceneProgress.scene_id == scene_id
            )
        ).first()
    
    def create_scene_progress(
        self,
        user_progress_id: int,
        scene_id: int,
        status: str = "in_progress"
    ) -> SceneProgress:
        """Create a new scene progress record."""
        scene_progress = SceneProgress(
            user_progress_id=user_progress_id,
            scene_id=scene_id,
            status=status
        )
        self.db.add(scene_progress)
        self.db.flush()
        return scene_progress
    
    def get_conversation_logs(
        self,
        user_progress_id: int,
        scene_id: Optional[int] = None,
        limit: Optional[int] = None,
        order_desc: bool = False
    ) -> List[ConversationLog]:
        """Get conversation logs for a user progress."""
        query = self.db.query(ConversationLog).filter(
            ConversationLog.user_progress_id == user_progress_id
        )
        if scene_id is not None:
            query = query.filter(ConversationLog.scene_id == scene_id)
        
        if order_desc:
            query = query.order_by(desc(ConversationLog.message_order))
        else:
            query = query.order_by(ConversationLog.message_order)
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def get_last_conversation_log(
        self,
        user_progress_id: int
    ) -> Optional[ConversationLog]:
        """Get the last conversation log for a user progress."""
        return self.db.query(ConversationLog).filter(
            ConversationLog.user_progress_id == user_progress_id
        ).order_by(desc(ConversationLog.message_order)).first()
    
    def create_conversation_log(
        self,
        user_progress_id: int,
        scene_id: int,
        message_type: str,
        sender_name: str,
        message_content: str,
        message_order: int,
        persona_id: Optional[int] = None
    ) -> ConversationLog:
        """Create a new conversation log."""
        log = ConversationLog(
            user_progress_id=user_progress_id,
            scene_id=scene_id,
            message_type=message_type,
            sender_name=sender_name,
            message_content=message_content,
            message_order=message_order,
            persona_id=persona_id
        )
        self.db.add(log)
        self.db.flush()
        return log
    
    def get_student_simulation_instance(
        self,
        user_progress_id: int
    ) -> Optional[StudentSimulationInstance]:
        """Get student simulation instance by user progress ID."""
        return self.db.query(StudentSimulationInstance).filter(
            StudentSimulationInstance.user_progress_id == user_progress_id
        ).first()
    
    def get_personas_for_scene(self, scene_id: int) -> List[SimulationPersona]:
        """Get personas involved in a specific scene."""
        return self.db.query(SimulationPersona).join(
            scene_personas, SimulationPersona.id == scene_personas.c.persona_id
        ).filter(
            scene_personas.c.scene_id == scene_id
        ).filter(
            SimulationPersona.deleted_at.is_(None)
        ).all()
    
    def get_personas_by_ids(self, persona_ids: List[int]) -> List[SimulationPersona]:
        """Get personas by list of IDs."""
        return self.db.query(SimulationPersona).filter(
            SimulationPersona.id.in_(persona_ids),
            SimulationPersona.deleted_at.is_(None)
        ).all()
    
    def check_scene_intro_exists(
        self,
        user_progress_id: int,
        scene_id: int
    ) -> Optional[ConversationLog]:
        """Check if a scene intro message already exists for a scene."""
        return self.db.query(ConversationLog).filter(
            ConversationLog.user_progress_id == user_progress_id,
            ConversationLog.scene_id == scene_id,
            ConversationLog.message_type == "system",
            ConversationLog.sender_name == "System"
        ).first()
    
    def delete_all_user_progress_for_simulation(self, user_id: int, simulation_id: int) -> None:
        """Delete all user progress and related records for a user and simulation."""
        existing_progresses = self.get_user_progress_by_user_and_simulation(user_id, simulation_id)
        for progress in existing_progresses:
            self.delete_user_progress_and_related(progress.id)
        self.db.flush()
