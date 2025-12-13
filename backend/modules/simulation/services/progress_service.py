"""
Progress Service.

Handles simulation progress and state retrieval operations.
"""

from sqlalchemy.orm import Session

from modules.simulation.repository import SimulationRepository
from modules.simulation.schemas.dto import (
    UserProgressResponse, ScenarioSceneResponse, ScenarioPersonaResponse,
    SimulationScenarioResponse
)
from common.exceptions import NotFoundError, ForbiddenError


class ProgressService:
    """Service for simulation progress and state retrieval."""
    
    def __init__(self, db: Session, repository: SimulationRepository):
        self.db = db
        self.repository = repository
    
    def get_user_progress(
        self,
        user_progress_id: int,
        user_id: int
    ) -> UserProgressResponse:
        """Get detailed user progress for a simulation."""
        user_progress = self.repository.get_user_progress_by_id(user_progress_id)
        if not user_progress:
            raise NotFoundError("User progress not found")
        
        if user_progress.user_id != user_id:
            raise ForbiddenError("Access denied")
        
        scenario = self.repository.get_scenario_by_id(user_progress.scenario_id)
        if not scenario:
            raise NotFoundError("Scenario not found")
        
        scenes = self.repository.get_scenes_by_scenario_id(user_progress.scenario_id)
        current_scene = self.repository.get_scene_by_id(user_progress.current_scene_id) if user_progress.current_scene_id else None
        
        # Build response
        return UserProgressResponse(
            id=user_progress.id,
            user_id=user_progress.user_id,
            scenario_id=user_progress.scenario_id,
            current_scene_id=user_progress.current_scene_id,
            simulation_status=user_progress.simulation_status,
            scenes_completed=user_progress.scenes_completed or [],
            orchestrator_data=user_progress.orchestrator_data or {},
            created_at=user_progress.created_at,
            updated_at=user_progress.updated_at,
            completed_at=user_progress.completed_at,
            scenario=SimulationScenarioResponse(
                id=scenario.id,
                title=scenario.title,
                description=scenario.description
            ) if scenario else None,
            current_scene=ScenarioSceneResponse(
                id=current_scene.id,
                scenario_id=current_scene.scenario_id,
                title=current_scene.title,
                description=current_scene.description,
                scene_order=current_scene.scene_order,
                user_goal=current_scene.user_goal,
                timeout_turns=current_scene.timeout_turns,
                success_metric=current_scene.success_metric,
                created_at=current_scene.created_at,
                updated_at=current_scene.updated_at,
                personas=[
                    ScenarioPersonaResponse(
                        id=p.id,
                        scenario_id=p.scenario_id,
                        name=p.name,
                        role=p.role,
                        background=getattr(p, 'background', None)
                    )
                    for p in self.repository.get_personas_for_scene(current_scene.id)
                ]
            ) if current_scene else None
        )
    
    def get_scene_by_id(self, scene_id: int) -> ScenarioSceneResponse:
        """Get scene data by ID."""
        scene = self.repository.get_scene_by_id(scene_id)
        if not scene:
            raise NotFoundError("Scene not found")
        
        # Get personas for this scene
        personas = self.repository.get_personas_for_scene(scene_id)
        personas_data = [
            ScenarioPersonaResponse(
                id=p.id,
                scenario_id=p.scenario_id,
                name=p.name,
                role=p.role,
                background=getattr(p, 'background', None),
                correlation=getattr(p, 'correlation', None),
                primary_goals=(
                    [p.primary_goals] if isinstance(getattr(p, 'primary_goals', None), str) and getattr(p, 'primary_goals', None) else
                    getattr(p, 'primary_goals', []) if isinstance(getattr(p, 'primary_goals', None), list) else []
                ),
                personality_traits=getattr(p, 'personality_traits', None) or {},
                image_url=getattr(p, 'image_url', None),
                created_at=getattr(p, 'created_at', None),
                updated_at=getattr(p, 'updated_at', None)
            )
            for p in personas
        ]
        
        return ScenarioSceneResponse(
            id=scene.id,
            scenario_id=scene.scenario_id,
            title=scene.title,
            description=scene.description,
            scene_order=scene.scene_order,
            user_goal=scene.user_goal,
            timeout_turns=scene.timeout_turns,
            success_metric=scene.success_metric,
            image_url=getattr(scene, 'image_url', None),
            estimated_duration=getattr(scene, 'estimated_duration', None),
            created_at=scene.created_at,
            updated_at=scene.updated_at,
            personas=personas_data
        )

