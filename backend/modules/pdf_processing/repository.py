"""
Database repository for PDF processing module.
Handles all database operations for scenarios, personas, and scenes.
Extracted from api/parse_pdf.py
"""
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from database.models import Scenario, ScenarioPersona, ScenarioScene, scene_personas
from utilities.debug_logging import debug_log
import secrets


class PDFProcessingRepository:
    """Repository for PDF processing database operations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_scenario(self, user_id: Optional[int], filename: str) -> Scenario:
        """Create a new scenario in 'creating' status"""
        unique_id = f"SC-{secrets.token_urlsafe(8).upper()}"
        
        scenario = Scenario(
            unique_id=unique_id,
            title="Creating simulation...",
            description="",
            challenge="",
            industry="Business",
            learning_objectives=[],
            student_role="",
            source_type="pdf_upload",
            pdf_title=filename or "Uploaded PDF",
            pdf_source="Uploaded PDF",
            processing_version="1.0",
            is_public=False,
            allow_remixes=True,
            status="creating",  # Special status to indicate processing
            is_draft=True,
            created_by=user_id,
            name_completed=False,
            description_completed=False,
            student_role_completed=False,
            personas_completed=False,
            scenes_completed=False,
            images_completed=False,
            learning_outcomes_completed=False,
            ai_enhancement_completed=False,
            grading_config_completed=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        self.db.add(scenario)
        self.db.commit()
        self.db.refresh(scenario)
        
        return scenario
    
    def save_autofill_data(self, scenario_id: int, personas_result: Dict[str, Any]) -> bool:
        """Save autofill data (personas only) to scenario"""
        try:
            debug_log(f"[REPOSITORY] Starting autofill save for scenario {scenario_id}")
            
            # Get the scenario
            scenario = self.db.query(Scenario).filter(Scenario.id == scenario_id).first()
            if not scenario:
                debug_log(f"[REPOSITORY] Scenario {scenario_id} not found")
                return False
            
            # Update scenario with autofill data
            title = personas_result.get("title", scenario.title)
            description = personas_result.get("description", "")
            student_role = personas_result.get("student_role", "Business Manager")
            key_figures = personas_result.get("key_figures", [])
            
            scenario.title = title
            scenario.description = description
            scenario.challenge = description
            scenario.student_role = student_role
            scenario.status = "draft"  # Change from "creating" to "draft"
            scenario.name_completed = True
            scenario.description_completed = True
            scenario.student_role_completed = True
            scenario.personas_completed = True
            scenario.updated_at = datetime.utcnow()
            
            self.db.flush()
            
            # Save personas - check for existing ones first
            existing_personas = self.db.query(ScenarioPersona).filter(
                ScenarioPersona.scenario_id == scenario.id,
                ScenarioPersona.deleted_at.is_(None)
            ).all()
            existing_persona_names = {p.name for p in existing_personas}
            
            for figure in key_figures:
                if isinstance(figure, dict) and figure.get("name"):
                    persona_name = figure.get("name", "")
                    
                    # Skip if persona already exists
                    if persona_name in existing_persona_names:
                        debug_log(f"[REPOSITORY] Persona '{persona_name}' already exists, skipping")
                        continue
                    
                    traits = figure.get("personality_traits", {}) or figure.get("traits", {})
                    
                    persona = ScenarioPersona(
                        scenario_id=scenario.id,
                        name=persona_name,
                        role=figure.get("role", ""),
                        background=figure.get("background", ""),
                        correlation=figure.get("correlation", ""),
                        primary_goals=figure.get("primary_goals", []) or figure.get("primaryGoals", []),
                        personality_traits=traits,
                        image_url=figure.get("image_url") or figure.get("imageUrl"),
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    self.db.add(persona)
                    existing_persona_names.add(persona_name)
            
            self.db.commit()
            debug_log(f"[REPOSITORY] Successfully saved autofill data for scenario {scenario_id}")
            return True
            
        except Exception as e:
            debug_log(f"[REPOSITORY] Failed to save autofill data: {str(e)}")
            self.db.rollback()
            # Update scenario status to draft even on error
            try:
                scenario = self.db.query(Scenario).filter(Scenario.id == scenario_id).first()
                if scenario:
                    scenario.status = "draft"
                    self.db.commit()
            except:
                pass
            return False
    
    def save_full_pdf_data(self, scenario_id: int, ai_result: Dict[str, Any]) -> bool:
        """Save full PDF processing data to scenario (personas, scenes, learning outcomes)"""
        try:
            debug_log(f"[REPOSITORY] Starting full save for scenario {scenario_id}")
            
            # Get the scenario
            scenario = self.db.query(Scenario).filter(Scenario.id == scenario_id).first()
            if not scenario:
                debug_log(f"[REPOSITORY] Scenario {scenario_id} not found")
                return False
            
            # Update scenario with AI result data
            title = ai_result.get("title", scenario.title)
            description = ai_result.get("description", "")
            student_role = ai_result.get("student_role", "Business Manager")
            key_figures = ai_result.get("key_figures", [])
            scenes = ai_result.get("scenes", [])
            learning_outcomes = ai_result.get("learning_outcomes", [])
            
            scenario.title = title
            scenario.description = description
            scenario.challenge = description
            scenario.student_role = student_role
            scenario.learning_objectives = learning_outcomes
            scenario.status = "draft"
            scenario.name_completed = True
            scenario.description_completed = True
            scenario.student_role_completed = True
            scenario.personas_completed = len(key_figures) > 0
            scenario.scenes_completed = len(scenes) > 0
            scenario.learning_outcomes_completed = len(learning_outcomes) > 0
            scenario.updated_at = datetime.utcnow()
            
            self.db.flush()
            
            # Save personas
            existing_personas = self.db.query(ScenarioPersona).filter(
                ScenarioPersona.scenario_id == scenario.id,
                ScenarioPersona.deleted_at.is_(None)
            ).all()
            existing_persona_names = {p.name for p in existing_personas}
            
            for figure in key_figures:
                if isinstance(figure, dict) and figure.get("name"):
                    persona_name = figure.get("name", "")
                    
                    if persona_name in existing_persona_names:
                        continue
                    
                    traits = figure.get("personality_traits", {}) or figure.get("traits", {})
                    
                    persona = ScenarioPersona(
                        scenario_id=scenario.id,
                        name=persona_name,
                        role=figure.get("role", ""),
                        background=figure.get("background", ""),
                        correlation=figure.get("correlation", ""),
                        primary_goals=figure.get("primary_goals", []) or figure.get("primaryGoals", []),
                        personality_traits=traits,
                        image_url=figure.get("image_url") or figure.get("imageUrl"),
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    self.db.add(persona)
                    existing_persona_names.add(persona_name)
            
            self.db.flush()  # Flush to get persona IDs
            
            # Build persona mapping: name -> id
            all_personas = self.db.query(ScenarioPersona).filter(
                ScenarioPersona.scenario_id == scenario.id,
                ScenarioPersona.deleted_at.is_(None)
            ).all()
            persona_mapping = {p.name: p.id for p in all_personas}
            debug_log(f"[REPOSITORY] Created persona_mapping with {len(persona_mapping)} personas")
            
            # Helper function to check if persona is the main character (student role)
            def is_main_character(persona_name, student_role):
                if not student_role or not persona_name:
                    return False
                
                # Extract just the name part from student role (before any parentheses)
                student_name = student_role.split('(')[0].strip()
                
                # Normalize names for comparison
                def normalize_name(name):
                    normalized = name.strip()
                    # Remove title prefixes
                    normalized = re.sub(r'^(Mr\.|Mrs\.|Ms\.|Miss|Dr\.|Prof\.|Professor)\s+', '', normalized, flags=re.IGNORECASE)
                    # Remove all non-alphabetic characters
                    normalized = re.sub(r'[^a-zA-Z]', '', normalized).lower()
                    return normalized
                
                return normalize_name(persona_name) == normalize_name(student_name)
            
            # Save scenes
            existing_scenes = self.db.query(ScenarioScene).filter(
                ScenarioScene.scenario_id == scenario.id
            ).all()
            existing_scene_titles = {s.title for s in existing_scenes}
            
            for scene_data in scenes:
                if isinstance(scene_data, dict) and scene_data.get("title"):
                    scene_title = scene_data.get("title", "")
                    
                    if scene_title in existing_scene_titles:
                        continue
                    
                    scene = ScenarioScene(
                        scenario_id=scenario.id,
                        title=scene_title,
                        description=scene_data.get("description", ""),
                        user_goal=scene_data.get("user_goal", ""),
                        scene_order=scene_data.get("sequence_order", 0),
                        estimated_duration=scene_data.get("estimated_duration", 30),
                        image_url=scene_data.get("image_url", ""),
                        image_prompt=f"Business scene: {scene_title}",
                        timeout_turns=int(scene_data.get("timeout_turns") or 15),
                        success_metric=scene_data.get("success_metric", ""),
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    self.db.add(scene)
                    self.db.flush()  # Flush to get scene ID
                    existing_scene_titles.add(scene_title)
                    
                    # Link personas to scene
                    personas_involved = scene_data.get("personas_involved", [])
                    
                    # Filter out the student role from personas_involved
                    personas_involved_filtered = [
                        p for p in personas_involved 
                        if not is_main_character(p, student_role)
                    ]
                    
                    if personas_involved_filtered:
                        unique_persona_names = set(personas_involved_filtered)
                        for persona_name in unique_persona_names:
                            # Try exact match first
                            if persona_name in persona_mapping:
                                persona_id = persona_mapping[persona_name]
                                self.db.execute(
                                    scene_personas.insert().values(
                                        scene_id=scene.id,
                                        persona_id=persona_id,
                                        involvement_level="participant"
                                    )
                                )
                                debug_log(f"[REPOSITORY] Linked persona '{persona_name}' to scene {scene_title}")
                            else:
                                # Try case-insensitive match
                                for mapping_name, persona_id in persona_mapping.items():
                                    if persona_name.lower().strip() == mapping_name.lower().strip():
                                        self.db.execute(
                                            scene_personas.insert().values(
                                                scene_id=scene.id,
                                                persona_id=persona_id,
                                                involvement_level="participant"
                                            )
                                        )
                                        debug_log(f"[REPOSITORY] Linked persona '{persona_name}' (matched '{mapping_name}') to scene {scene_title}")
                                        break
            
            # Check if images exist
            all_scenes = self.db.query(ScenarioScene).filter(
                ScenarioScene.scenario_id == scenario.id
            ).all()
            has_scenes_with_images = any(scene.image_url for scene in all_scenes)
            
            all_personas_final = self.db.query(ScenarioPersona).filter(
                ScenarioPersona.scenario_id == scenario.id,
                ScenarioPersona.deleted_at.is_(None)
            ).all()
            has_personas_with_images = any(persona.image_url for persona in all_personas_final)
            
            scenario.images_completed = has_scenes_with_images or has_personas_with_images
            
            self.db.commit()
            debug_log(f"[REPOSITORY] Successfully saved full data for scenario {scenario_id}")
            return True
            
        except Exception as e:
            debug_log(f"[REPOSITORY] Failed to save full data: {str(e)}")
            self.db.rollback()
            # Update scenario status to draft even on error
            try:
                scenario = self.db.query(Scenario).filter(Scenario.id == scenario_id).first()
                if scenario:
                    scenario.status = "draft"
                    self.db.commit()
            except:
                pass
            return False
    
    def update_scenario_status_to_draft(self, scenario_id: int) -> bool:
        """Update scenario status to draft (used on error)"""
        try:
            scenario = self.db.query(Scenario).filter(Scenario.id == scenario_id).first()
            if scenario:
                scenario.status = "draft"
                self.db.commit()
                return True
            return False
        except Exception as e:
            debug_log(f"[REPOSITORY] Failed to update scenario status: {str(e)}")
            self.db.rollback()
            return False


# Helper function to create repository instance
def get_repository(db: Session) -> PDFProcessingRepository:
    """Get a repository instance"""
    return PDFProcessingRepository(db)
