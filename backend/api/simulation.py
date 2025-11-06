"""
Sequential Timeline Simulation API
Handles guided simulation with AI personas, goal validation, and progress tracking
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import and_, desc
from typing import List, Optional, Dict, Any
import json
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import openai
import os

from database.connection import get_db, settings
from database.models import (
    Scenario, ScenarioScene, ScenarioPersona, ScenarioFile, User,
    UserProgress, SceneProgress, ConversationLog, AgentSessions,
    SessionMemory, ConversationSummaries, StudentSimulationInstance,
    scene_personas
)
from utilities.auth import get_current_user
from utilities.debug_logging import debug_log
from agents.persona_agent import PersonaAgent
from agents.grading_agent import grading_agent
from database.schemas import (
    SimulationStartRequest, SimulationStartResponse, SimulationScenarioResponse,
    SimulationChatRequest, SimulationChatResponse,
    GoalValidationRequest, GoalValidationResponse,
    SceneProgressRequest, SceneProgressResponse,
    UserProgressResponse, SimulationAnalyticsResponse,
    ScenarioResponse, ScenarioSceneResponse, ScenarioPersonaResponse,
    SaveMessageRequest
)
from .chat_orchestrator import ChatOrchestrator, SimulationState
from services.few_shot_examples import few_shot_examples_service

def generate_timeout_message(next_scene: Optional[Dict[str, Any]] = None) -> str:
    """Generate timeout message for scene progression
    
    Matches the format from ChatOrchestrator.generate_timeout_message
    """
    if next_scene:
        return f"⏰ **Time's up!** You've reached the maximum turns for this scene. Moving to the next scene.\n\n**{next_scene.get('title', 'Next Scene')}**\n\n**Objective:** {next_scene.get('objectives', ['Continue the simulation'])[0]}"
    else:
        return "⏰ **Time's up!** You've reached the maximum turns for this scene. This was the final scene - simulation complete!"

def generate_scene_intro_message(scene: dict, db_scene: Any = None, db: Session = None) -> str:
    """Generate the scene introduction message that appears at the start of each scene
    
    Matches the format from frontend's generateSceneIntroduction function
    """
    # Use database scene data if provided for more accuracy
    if db_scene:
        title = db_scene.title
        description = db_scene.description
        user_goal = db_scene.user_goal
        timeout_turns = db_scene.timeout_turns if db_scene.timeout_turns is not None else 15
        scene_order = db_scene.scene_order
    else:
        title = scene.get('title', 'Scene')
        description = scene.get('description', '')
        user_goal = scene.get('objectives', ['Complete the scene'])[0] if scene.get('objectives') else scene.get('user_goal', 'Complete the scene')
        timeout_turns = scene.get('timeout_turns') or scene.get('max_turns', 15)
        scene_order = scene.get('scene_order', 1)
    
    # Get personas involved with their roles
    personas_involved = scene.get('personas_involved', [])
    
    # Build persona list with roles
    persona_text = ""
    if personas_involved and db and db_scene:
        from database.models import ScenarioPersona, scene_personas as sp_table
        # Get full persona details for personas involved in this scene
        scene_personas = db.query(ScenarioPersona).join(
            sp_table, ScenarioPersona.id == sp_table.c.persona_id
        ).filter(
            sp_table.c.scene_id == db_scene.id
        ).all()
        
        if scene_personas:
            persona_text = "\n**Active Participants:**\n"
            for persona in scene_personas:
                persona_id = persona.name.lower().replace(' ', '_')
                persona_text += f"• @{persona_id}: {persona.name} ({persona.role})\n"
    elif personas_involved:
        # Fallback without role information
        persona_text = "\n**Active Participants:**\n"
        for persona_name in personas_involved:
            persona_id = persona_name.lower().replace(' ', '_')
            persona_text += f"• @{persona_id}: {persona_name}\n"
    
    intro = f"""**Scene {scene_order} — {title}**

*{description}*

**Objective:** {user_goal}
{persona_text}
*You have {timeout_turns} turns to achieve the objective.*"""
    
    return intro

router = APIRouter(prefix="/api/simulation", tags=["Simulation"])

# Performance optimization constants
SIMULATION_EXECUTOR = ThreadPoolExecutor(max_workers=6)
MAX_CONCURRENT_AI_CALLS = 3

# Global semaphore for AI calls
_ai_semaphore = asyncio.Semaphore(MAX_CONCURRENT_AI_CALLS)

# OpenAI configuration - defer validation to request time
def _get_openai_client():
    """Get configured OpenAI client, raise error if not configured"""
    api_key = settings.openai_api_key
    if not api_key or not api_key.strip():
        raise HTTPException(
            status_code=503,
            detail="OpenAI API key not configured. Please contact administrator."
        )
    return openai.OpenAI(api_key=api_key)

async def _get_openai_client_async():
    """Async wrapper for OpenAI client creation"""
    return await asyncio.get_event_loop().run_in_executor(
        SIMULATION_EXECUTOR, _get_openai_client
    )

def validate_goal_with_function_calling(
    conversation_history: str,
    scene_goal: str,
    scene_description: str,
    current_attempts: int,
    max_attempts: int,
    db: Session = None,
    user_progress_id: int = None,
    current_scene_id: int = None,
    perform_db_progression: bool = False
) -> dict:
    """
    Use OpenAI function calling to validate if user has achieved the scene goal
    """
    import json
    
    # --- PATCH: Pre-check for generic/irrelevant responses ---
    irrelevant_responses = {"test", "hello", "ok", "hi", "thanks", "hey", "goodbye", "bye"}
    # Extract the last user message from the conversation history
    last_user_message = ""
    for line in reversed(conversation_history.strip().split("\n")):
        if line.lower().startswith("user:"):
            last_user_message = line[5:].strip()
            break
    if last_user_message.lower() in irrelevant_responses or len(last_user_message) < 3:
        return {
            "goal_achieved": False,
            "confidence_score": 0.0,
            "reasoning": "Your last message did not address the scene's goal.",
            "next_action": "continue",
            "hint_message": "Please provide a response that directly addresses the scene's goal and aligns with the success metric."
        }
    # --- END PATCH ---
    # Define the function for scene progression
    function_definitions = [
        {
            "name": "progress_to_next_scene",
            "description": "Progress to the next scene when the user has achieved the current scene goal",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_achieved": {
                        "type": "boolean",
                        "description": "Whether the user has achieved the scene goal"
                    },
                    "confidence_score": {
                        "type": "number",
                        "description": "Confidence score from 0.0 to 1.0"
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Brief explanation of why the goal was or wasn't achieved"
                    },
                    "next_action": {
                        "type": "string",
                        "enum": ["continue", "progress", "hint", "force_progress"],
                        "description": "What action to take next"
                    },
                    "hint_message": {
                        "type": "string",
                        "description": "Optional hint message if the user needs guidance"
                    },
                    "should_progress": {
                        "type": "boolean",
                        "description": "Whether to actually progress to the next scene in the database"
                    }
                },
                "required": ["goal_achieved", "confidence_score", "reasoning", "next_action", "should_progress"]
            }
        }
    ]
    
    # --- PATCH: Improved strict prompt ---
    evaluation_prompt = f"""
You are a goal validation agent for a business simulation. Analyze the conversation and determine if the user has achieved the scene goal.

SCENE SUCCESS METRIC: {scene_goal}
SCENE GOAL: {scene_goal}
SCENE DESCRIPTION: {scene_description}

RECENT CONVERSATION:
{conversation_history}

CURRENT ATTEMPTS: {current_attempts}/{max_attempts}

Grade ONLY based on the success metric above, and secondarily on the scene goal if relevant. Do NOT consider or reference any learning outcomes.

Be moderately lenient: If the user's last message is on-topic and makes a good-faith attempt to address the success metric or goal, mark the goal as achieved. Do not require perfect answers or exact wording. Only mark the goal as not achieved if the response is completely off-topic, irrelevant, or generic (e.g., 'test', 'hello', 'ok').

When the user's last message does NOT achieve the goal, explain why it was insufficient or off-topic, but do NOT simply repeat or quote the user's message. Only reference the user's message if it adds clarity to your reasoning.

Analyze the conversation and determine:
1. Has the user achieved the scene goal? (goal_achieved: true/false)
2. Confidence score (0.0-1.0) based on how clearly the goal was achieved
3. Brief reasoning for your decision (do NOT simply repeat the user's last message if the goal was not achieved)
4. Next action: 
   - "continue" if they need more interaction
   - "progress" if goal is achieved and ready to move on
   - "hint" if they're stuck and need guidance
   - "force_progress" if max attempts reached
5. Optional hint message if action is "hint"
6. Should progress: Set to true if the goal is achieved and you want to actually move to the next scene

Call the progress_to_next_scene function with your analysis.
"""
    # --- END PATCH ---
    try:
        client = _get_openai_client()
        
        # First call to get function call
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # Updated to current model
            messages=[{"role": "user", "content": evaluation_prompt}],
            tools=[{"type": "function", "function": function_definitions[0]}],
            tool_choice={"type": "function", "function": {"name": "progress_to_next_scene"}},
            max_tokens=300,
            temperature=0.3
        )
        
        message = response.choices[0].message
        
        if message.tool_calls:
            # Parse the tool call arguments
            tool_call = message.tool_calls[0]
            arguments = json.loads(tool_call.function.arguments)
            
            # Check if we should actually progress to the next scene
            should_progress = arguments.get("should_progress", False)
            
            if should_progress and db and user_progress_id and current_scene_id:
                debug_log(f"Executing scene progression for user {user_progress_id}, scene {current_scene_id}")
                
                # Get user progress
                user_progress = db.query(UserProgress).filter(UserProgress.id == user_progress_id).first()
                if user_progress:
                    # Get current scene
                    current_scene = db.query(ScenarioScene).filter(ScenarioScene.id == current_scene_id).first()
                    if current_scene:
                        # Find next scene
                        next_scene = db.query(ScenarioScene).filter(
                            and_(
                                ScenarioScene.scenario_id == user_progress.scenario_id,
                                ScenarioScene.scene_order > current_scene.scene_order
                            )
                        ).order_by(ScenarioScene.scene_order).first()
                        
                        if next_scene:
                            debug_log(f"Found next_scene with id={next_scene.id}, title={next_scene.title}")
                            # Update user progress to next scene
                            user_progress.current_scene_id = next_scene.id
                            user_progress.last_activity = datetime.utcnow()
                            
                            # Mark current scene as completed
                            completed_scenes = user_progress.scenes_completed or []
                            if current_scene_id not in completed_scenes:
                                completed_scenes.append(current_scene_id)
                                user_progress.scenes_completed = completed_scenes
                            
                            # Update scene progress
                            scene_progress = db.query(SceneProgress).filter(
                                and_(
                                    SceneProgress.user_progress_id == user_progress_id,
                                    SceneProgress.scene_id == current_scene_id
                                )
                            ).first()
                            
                            if scene_progress:
                                scene_progress.status = "completed"
                                scene_progress.goal_achieved = True
                                scene_progress.completed_at = datetime.utcnow()
                            
                            # Create scene progress for next scene
                            next_scene_progress = SceneProgress(
                                user_progress_id=user_progress_id,
                                scene_id=next_scene.id,
                                status="in_progress",
                                started_at=datetime.utcnow()
                            )
                            db.add(next_scene_progress)
                            
                            # Commit the changes
                            db.commit()
                            debug_log(f"Returning next_scene (id={next_scene.id}), simulation_complete=False")
                            
                            # Add progression info to result
                            arguments["next_scene_id"] = next_scene.id
                            arguments["next_scene_title"] = next_scene.title
                        else:
                            # No more scenes - simulation complete
                            user_progress.simulation_status = "completed"
                            user_progress.completed_at = datetime.utcnow()
                            db.commit()
                            debug_log("Simulation completed")
                            arguments["simulation_complete"] = True
            
            # Return the parsed result
            return {
                "goal_achieved": arguments.get("goal_achieved", False),
                "confidence_score": arguments.get("confidence_score", 0.0),
                "reasoning": arguments.get("reasoning", ""),
                "next_action": arguments.get("next_action", "continue"),
                "hint_message": arguments.get("hint_message"),
                "next_scene_id": arguments.get("next_scene_id"),
                "next_scene_title": arguments.get("next_scene_title"),
                "simulation_complete": arguments.get("simulation_complete", False)
            }
        else:
            # Fallback if no function call
            return {
                "goal_achieved": False,
                "confidence_score": 0.0,
                "reasoning": "No function call made",
                "next_action": "continue",
                "hint_message": None
            }
            
    except Exception as e:
        debug_log(f"Goal validation failed: {str(e)}")
        return {
            "goal_achieved": False,
            "confidence_score": 0.0,
            "reasoning": f"Error during validation: {str(e)}",
            "next_action": "continue",
            "hint_message": None
        }

@router.post("/start", response_model=SimulationStartResponse)
async def start_simulation(
    request: SimulationStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start a new simulation or resume existing one"""
    # --- PATCH: Always create a new UserProgress and clean up all old progress/logs ---
    # Delete all previous progress and related logs for this user and scenario
    # Use the authenticated user's ID
    existing_progresses = db.query(UserProgress).filter(
        UserProgress.user_id == current_user.id,
        UserProgress.scenario_id == request.scenario_id
    ).all()
    for progress in existing_progresses:
        db.query(SceneProgress).filter(SceneProgress.user_progress_id == progress.id).delete()
        db.query(ConversationLog).filter(ConversationLog.user_progress_id == progress.id).delete()
        db.query(AgentSessions).filter(AgentSessions.user_progress_id == progress.id).delete()
        db.query(SessionMemory).filter(SessionMemory.user_progress_id == progress.id).delete()
        db.query(ConversationSummaries).filter(ConversationSummaries.user_progress_id == progress.id).delete()
        db.query(StudentSimulationInstance).filter(StudentSimulationInstance.user_progress_id == progress.id).delete()
        db.delete(progress)
    db.commit()
    # --- END PATCH ---
    # Verify scenario exists
    scenario = db.query(Scenario).filter(Scenario.id == request.scenario_id).first()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    # Get first scene in order
    first_scene = db.query(ScenarioScene).filter(
        ScenarioScene.scenario_id == request.scenario_id
    ).order_by(ScenarioScene.scene_order).first()
    if not first_scene:
        raise HTTPException(status_code=400, detail="Scenario has no scenes")
    # Always create a new UserProgress
    # Use eager loading to avoid N+1 queries for scene personas
    all_scenes = db.query(ScenarioScene).options(
        selectinload(ScenarioScene.personas)
    ).filter(
        ScenarioScene.scenario_id == scenario.id
    ).order_by(ScenarioScene.scene_order).all()
    all_personas = db.query(ScenarioPersona).filter(
        ScenarioPersona.scenario_id == scenario.id,
        ScenarioPersona.deleted_at.is_(None)
    ).all()
    # Build persona map from already loaded relationships
    scene_personas_map = {}
    for scene in all_scenes:
        # Get personas from the loaded relationship
        involved_personas = [p for p in scene.personas if p.deleted_at is None]
        scene_personas_map[scene.id] = [p.name for p in involved_personas]
    
    scenario_data = {
        "id": scenario.id,
        "title": scenario.title,
        "description": scenario.description,
        "challenge": scenario.challenge,
        "student_role": scenario.student_role,  # Add student role to orchestrator data
        "scenes": [
            {
                "id": scene.id,
                "title": scene.title,
                "description": scene.description,
                "objectives": [scene.user_goal] if scene.user_goal else ["Complete the scene interaction"],
                "image_url": scene.image_url,
                "agent_ids": [p.name.lower().replace(" ", "_") for p in all_personas],
                "personas_involved": scene_personas_map.get(scene.id, []),  # Add personas_involved
                "max_turns": scene.timeout_turns if scene.timeout_turns is not None else 15,
                "success_criteria": f"User achieves: {scene.user_goal or 'scene completion'}"
            }
            for scene in all_scenes
        ],
        "personas": [
            {
                "id": persona.name.lower().replace(" ", "_"),
                "db_id": persona.id,  # Include the actual database ID
                "identity": {
                    "name": persona.name,
                    "role": persona.role,
                    "bio": persona.background or "Professional team member"
                },
                "personality": {
                    "goals": persona.primary_goals or ["Support team objectives"],
                    "traits": persona.personality_traits or "Professional and collaborative"
                },
                "system_prompt": persona.system_prompt,
                "image_url": persona.image_url
            }
            for persona in all_personas
        ]
    }
    user_progress = UserProgress(
        user_id=current_user.id,  # Use authenticated user
        scenario_id=request.scenario_id,
        current_scene_id=first_scene.id,
        simulation_status="waiting_for_begin",
        session_count=1,
        scenes_completed=[],
        orchestrator_data=scenario_data,
        started_at=datetime.utcnow(),
        last_activity=datetime.utcnow()
    )
    db.add(user_progress)
    db.flush()  # Get ID
    # Create scene progress for first scene
    scene_progress = SceneProgress(
        user_progress_id=user_progress.id,
        scene_id=first_scene.id,
        status="in_progress",
        started_at=datetime.utcnow()
    )
    db.add(scene_progress)
    current_scene = first_scene
    
    # Save initial welcome message to conversation history so it persists on reload
    welcome_text = f"""🎯 **{scenario.title}**

{scenario.description}

**Your Role:** {scenario.student_role}

**Current Scene:** {current_scene.title}

**Instructions:**
• Type **"begin"** to start the simulation
• Type **"help"** for available commands
• Use natural conversation to interact with personas"""
    
    welcome_log = ConversationLog(
        user_progress_id=user_progress.id,
        scene_id=current_scene.id,
        message_type="system",
        sender_name="System",
        message_content=welcome_text,
        message_order=1,
        timestamp=datetime.utcnow()
    )
    db.add(welcome_log)
    db.commit()
    
    # Prepare response data
    # Ensure learning_objectives is always a list
    learning_objectives = scenario.learning_objectives
    if isinstance(learning_objectives, str):
        learning_objectives = [learning_objectives]
    elif learning_objectives is None:
        learning_objectives = []
    
    # Get case study PDF URL from ScenarioFile
    case_study_url = None
    scenario_file = db.query(ScenarioFile).filter(
        ScenarioFile.scenario_id == scenario.id,
        ScenarioFile.processing_status == "completed"
    ).first()
    if scenario_file and scenario_file.file_path:
        case_study_url = scenario_file.file_path
        debug_log(f"[SIMULATION] Found case study PDF: {case_study_url}")
    
    scenario_data = SimulationScenarioResponse(
        id=scenario.id,
        title=scenario.title,
        description=scenario.description,
        challenge=scenario.challenge,
        industry=scenario.industry,
        learning_objectives=learning_objectives,
        student_role=scenario.student_role,
        total_scenes=len(all_scenes),  # Add total scenes count
        case_study_url=case_study_url  # Add case study PDF URL
    )
    
    # Get only personas involved in the current scene
    main_character_name = (scenario.student_role or '').strip().lower()
    
    # Query the junction table to get involved personas for the current scene
    involved_personas = db.query(ScenarioPersona).join(
        scene_personas, ScenarioPersona.id == scene_personas.c.persona_id
    ).filter(
        scene_personas.c.scene_id == current_scene.id
    ).all()

    # Helper function to check if persona is the main character
    def is_main_character(persona_name, student_role):
        if not student_role:
            return False
        # Extract just the name part from student role (before any parentheses or additional info)
        student_name = student_role.split('(')[0].strip().lower()
        persona_name_clean = persona_name.strip().lower()
        return persona_name_clean == student_name

    personas_data = [
        ScenarioPersonaResponse(
            id=persona.id,
            scenario_id=persona.scenario_id,
            name=persona.name,
            role=persona.role,
            background=persona.background,
            correlation=persona.correlation,
            primary_goals=(
                [persona.primary_goals] if isinstance(persona.primary_goals, str) and persona.primary_goals else
                persona.primary_goals if isinstance(persona.primary_goals, list) else []
            ),
            personality_traits=persona.personality_traits or {},
            image_url=persona.image_url,
            created_at=persona.created_at,
            updated_at=persona.updated_at
        ) for persona in involved_personas
        if not is_main_character(persona.name, scenario.student_role)
    ]
    
    scene_data = ScenarioSceneResponse(
        id=current_scene.id,
        scenario_id=current_scene.scenario_id,
        title=current_scene.title,
        description=current_scene.description,
        user_goal=current_scene.user_goal,
        scene_order=current_scene.scene_order,
        estimated_duration=current_scene.estimated_duration,
        image_url=current_scene.image_url,
        image_prompt=current_scene.image_prompt,
        timeout_turns=current_scene.timeout_turns,  # Ensure this is included
        success_metric=current_scene.success_metric,  # Ensure this is included
        personas_involved=scene_personas_map.get(current_scene.id, []),  # Add personas_involved
        created_at=current_scene.created_at,
        updated_at=current_scene.updated_at,
        personas=personas_data
    )
    
    # Get conversation history for the response
    conversation_logs = db.query(ConversationLog).filter(
        ConversationLog.user_progress_id == user_progress.id
    ).order_by(ConversationLog.message_order, ConversationLog.timestamp).all()
    
    # Format conversation logs for frontend
    messages_history = []
    # Pre-fetch all personas to avoid N+1 queries
    persona_map = {}
    if conversation_logs:
        persona_ids = [log.persona_id for log in conversation_logs if log.persona_id]
        if persona_ids:
            personas = db.query(ScenarioPersona).filter(ScenarioPersona.id.in_(persona_ids)).all()
            persona_map = {p.id: p for p in personas}
    
    for log in conversation_logs:
        persona_name = None
        persona_role = None
        if log.persona_id and log.persona_id in persona_map:
            persona = persona_map[log.persona_id]
            persona_name = persona.name
            persona_role = persona.role
        
        message_dict = {
            "id": log.id,
            "sender": log.sender_name or ("User" if log.message_type == "user" else "System"),
            "text": log.message_content,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            "type": log.message_type,
            "persona_id": log.persona_id,
            "persona_name": persona_name,
            "persona_role": persona_role,
            "scene_id": log.scene_id
        }
        messages_history.append(message_dict)
    
    # Build all scenes with personas for frontend lookup (similar to student instance endpoint)
    scenes_with_personas = []
    for scene in all_scenes:
        # Get personas from the loaded relationship
        involved_personas = [p for p in scene.personas if p.deleted_at is None]
        # Filter out main character
        filtered_personas = [
            p for p in involved_personas
            if not (scenario.student_role and p.name.strip().lower() == scenario.student_role.split('(')[0].strip().lower())
        ]
        
        scenes_with_personas.append({
            "id": scene.id,
            "title": scene.title,
            "scene_order": scene.scene_order,
            "personas": [
                {
                    "id": p.id,
                    "name": p.name,
                    "role": p.role,
                    "background": p.background,
                    "correlation": p.correlation,
                    "primary_goals": p.primary_goals,
                    "personality_traits": p.personality_traits,
                    "image_url": p.image_url if p.image_url else None
                }
                for p in filtered_personas
            ]
        })
    
    response = SimulationStartResponse(
        user_progress_id=user_progress.id,
        scenario=scenario_data,
        current_scene=scene_data,
        simulation_status=user_progress.simulation_status,
        conversation_history=messages_history,
        is_resuming=len(messages_history) > 0
    )
    
    # Add all_scenes to response (not in schema, but frontend can handle it)
    response_dict = response.model_dump()
    response_dict["all_scenes"] = scenes_with_personas
    
    return response_dict

@router.post("/chat", response_model=SimulationChatResponse)
async def chat_with_persona(
    request: SimulationChatRequest,
    db: Session = Depends(get_db)
):
    """Send message to AI persona and get response"""
    
    start_time = time.time()
    
    # Get user progress and validate
    user_progress = db.query(UserProgress).filter(
        UserProgress.id == request.user_progress_id
    ).first()
    
    if not user_progress:
        raise HTTPException(status_code=404, detail="User progress not found")
    
    # Get user to check if they're a professor (skip conversation logging for professors)
    user = db.query(User).filter(User.id == user_progress.user_id).first()
    is_professor_testing = user and user.role in ['professor', 'admin']
    
    # Get scene and personas
    scene = db.query(ScenarioScene).filter(
        ScenarioScene.id == request.scene_id
    ).first()
    
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    # Get all personas for the scenario
    scene_personas = db.query(ScenarioPersona).filter(
        ScenarioPersona.scenario_id == scene.scenario_id,
        ScenarioPersona.deleted_at.is_(None)
    ).all()
    
    if not scene_personas:
        raise HTTPException(status_code=400, detail="No personas found for scene")
    
    # Determine target persona
    if request.target_persona_id:
        target_persona = next((p for p in scene_personas if p.id == request.target_persona_id), None)
        if not target_persona:
            raise HTTPException(status_code=400, detail="Target persona not found in scene")
    else:
        # Use first persona if none specified
        target_persona = scene_personas[0]
    
    # Get recent conversation context (skip for professors testing)
    recent_messages = []
    if not is_professor_testing:
        recent_messages = db.query(ConversationLog).filter(
            and_(
                ConversationLog.user_progress_id == request.user_progress_id,
                ConversationLog.scene_id == request.scene_id
            )
        ).order_by(desc(ConversationLog.message_order)).limit(10).all()
    
    # Get current attempt number
    scene_progress = db.query(SceneProgress).filter(
        and_(
            SceneProgress.user_progress_id == request.user_progress_id,
            SceneProgress.scene_id == request.scene_id
        )
    ).first()
    
    current_attempt = scene_progress.attempts if scene_progress else 1
    
    # Get next message order and log user message (skip for professors testing)
    next_message_order = 1
    if not is_professor_testing:
        last_message = db.query(ConversationLog).filter(
            and_(
                ConversationLog.user_progress_id == request.user_progress_id,
                ConversationLog.scene_id == request.scene_id
            )
        ).order_by(desc(ConversationLog.message_order)).first()
        
        next_message_order = (last_message.message_order + 1) if last_message else 1
        
        # Log user message
        user_log = ConversationLog(
            user_progress_id=request.user_progress_id,
            scene_id=request.scene_id,
            message_type="user",
            sender_name="User",
            message_content=request.message,
            message_order=next_message_order,
            attempt_number=current_attempt,
            timestamp=datetime.utcnow()
        )
        db.add(user_log)
        db.flush()
    
    # Build AI context
    conversation_context = []
    for msg in reversed(recent_messages[-6:]):  # Last 6 messages for context
        role = "user" if msg.message_type == "user" else "assistant"
        conversation_context.append({
            "role": role,
            "content": msg.message_content
        })
    
    # Add current user message
    conversation_context.append({
        "role": "user",
        "content": request.message
    })
    
    # Create persona data for few-shot examples
    persona_data = {
        'name': target_persona.name,
        'role': target_persona.role,
        'personality_traits': target_persona.personality_traits or {},
        'primary_goals': target_persona.primary_goals or []
    }
    
    # Use custom system prompt if available, otherwise generate default
    if target_persona.system_prompt:
        # Honor custom system prompt verbatim (no scene context appended)
        system_prompt = target_persona.system_prompt
        # When using a custom prompt, strip prior assistant context to avoid overriding it
        conversation_context = [conversation_context[-1]]
    else:
        # Get role-specific examples
        examples = few_shot_examples_service.get_adaptive_examples(persona_data, current_attempt)
        
        # Create AI prompt with persona and scene context
        system_prompt = f"""You are {target_persona.name}, a {target_persona.role} in this business simulation.

{examples}

PERSONA BACKGROUND:
{target_persona.background}

PERSONA CORRELATION TO CASE:
{target_persona.correlation}

PERSONALITY TRAITS: {json.dumps(target_persona.personality_traits)}

PRIMARY GOALS: {', '.join(target_persona.primary_goals or [])}

SCENE CONTEXT:
Title: {scene.title}
Description: {scene.description}
User Goal: {scene.user_goal}

BUSINESS SIMULATION INSTRUCTIONS:
- Stay in character as {target_persona.name} with your professional expertise
- Respond naturally based on your role, personality, and business knowledge
- Help guide the user toward the scene goal through realistic business interaction
- Encourage strategic thinking and analytical depth in the user's approach
- Don't directly give away answers, but provide realistic business insights and frameworks
- Keep responses concise and professional (2-4 sentences typically)
- If the user seems stuck, provide subtle hints through natural business conversation
- Focus on developing the user's business acumen and strategic thinking
- Consider multiple stakeholders and perspectives in your responses
- Use appropriate business terminology and frameworks relevant to your role
- Follow the examples above to maintain consistent character behavior
- Keep your response concise. Use paragraph breaks for readability.
"""
    
    try:
        # Call OpenAI API
        client = _get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt}
            ] + conversation_context,
            max_tokens=500,
            temperature=0.7
        )
        
        ai_response = response.choices[0].message.content
        processing_time = time.time() - start_time
        
        # Log AI response (skip for professors testing)
        if not is_professor_testing:
            ai_log = ConversationLog(
                user_progress_id=request.user_progress_id,
                scene_id=request.scene_id,
                message_type="ai_persona",
                sender_name=target_persona.name,
                persona_id=target_persona.id,
                message_content=ai_response,
                message_order=next_message_order + 1,
                attempt_number=current_attempt,
                ai_model_version="gpt-4o",
                processing_time=processing_time,
                timestamp=datetime.utcnow()
            )
            db.add(ai_log)
        
        # Update scene progress
        if scene_progress:
            scene_progress.messages_sent += 1
            scene_progress.ai_responses += 1
        else:
            scene_progress = SceneProgress(
                user_progress_id=request.user_progress_id,
                scene_id=request.scene_id,
                status="in_progress",
                messages_sent=1,
                ai_responses=1,
                attempts=1,
                started_at=datetime.utcnow()
            )
            db.add(scene_progress)
        
        # Update user progress
        user_progress.last_activity = datetime.utcnow()
        
        db.commit()
        
        return SimulationChatResponse(
            message_id=ai_log.id,
            persona_name=target_persona.name,
            persona_response=ai_response,
            message_order=next_message_order + 1,
            processing_time=processing_time,
            ai_model_version="gpt-4o"
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"AI processing failed: {str(e)}"
        )

@router.post("/validate-goal", response_model=GoalValidationResponse)
async def validate_scene_goal(
    request: GoalValidationRequest,
    db: Session = Depends(get_db)
):
    """Check if user has achieved the scene goal"""
    
    # Get user progress and scene
    user_progress = db.query(UserProgress).filter(
        UserProgress.id == request.user_progress_id
    ).first()
    
    if not user_progress:
        raise HTTPException(status_code=404, detail="User progress not found")
    
    scene = db.query(ScenarioScene).filter(
        ScenarioScene.id == request.scene_id
    ).first()
    
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    # Get recent conversation
    recent_messages = db.query(ConversationLog).filter(
        and_(
            ConversationLog.user_progress_id == request.user_progress_id,
            ConversationLog.scene_id == request.scene_id
        )
    ).order_by(desc(ConversationLog.message_order)).limit(10).all()
    
    if not recent_messages:
        return GoalValidationResponse(
            goal_achieved=False,
            confidence_score=0.0,
            reasoning="No conversation yet",
            next_action="continue"
        )
    
    # Build conversation summary for AI evaluation
    conversation_summary = []
    for msg in reversed(recent_messages):
        speaker = msg.sender_name or "System"
        conversation_summary.append(f"{speaker}: {msg.message_content}")
    
    conversation_text = "\n".join(conversation_summary)
    
    # Get scene progress for attempt tracking
    scene_progress = db.query(SceneProgress).filter(
        and_(
            SceneProgress.user_progress_id == request.user_progress_id,
            SceneProgress.scene_id == request.scene_id
        )
    ).first()
    
    current_attempts = scene_progress.attempts if scene_progress else 0
    max_attempts = scene.max_attempts or 5
    
    # AI evaluation prompt
    goal_for_validation = scene.success_metric or scene.user_goal
    evaluation_prompt = f"""Evaluate whether the user has achieved the scene goal based on the conversation.

SCENE GOAL: {goal_for_validation}

SCENE DESCRIPTION: {scene.description}

RECENT CONVERSATION:
{conversation_text}

CURRENT ATTEMPTS: {current_attempts}/{max_attempts}

Analyze the conversation and determine:
1. Has the user achieved the scene goal? (true/false)
2. Confidence score (0.0-1.0) 
3. Brief reasoning for your decision
4. Next recommended action: "continue", "progress", "hint", or "force_progress"
5. If action is "hint", provide a helpful hint message

Respond in JSON format:
{{
    "goal_achieved": boolean,
    "confidence_score": float,
    "reasoning": "string",
    "next_action": "string",
    "hint_message": "string or null"
}}
"""
    
    try:
        client = _get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": evaluation_prompt}],
            max_tokens=300,
            temperature=0.3
        )
        
        result = json.loads(response.choices[0].message.content)
        
        # Update scene progress if goal achieved
        if result["goal_achieved"] and scene_progress:
            scene_progress.goal_achieved = True
            scene_progress.goal_achievement_score = result["confidence_score"] * 100
            
            # Mark conversation that led to progress
            if recent_messages:
                recent_messages[0].led_to_progress = True
        
        # Check if we should force progression
        if current_attempts >= max_attempts and not result["goal_achieved"]:
            result["next_action"] = "force_progress"
            result["hint_message"] = f"You've reached the maximum attempts ({max_attempts}). Let's move to the next scene with a summary."
        
        db.commit()
        
        return GoalValidationResponse(
            goal_achieved=result["goal_achieved"],
            confidence_score=result["confidence_score"],
            reasoning=result["reasoning"],
            next_action=result["next_action"],
            hint_message=result.get("hint_message")
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Goal validation failed: {str(e)}"
        )

@router.post("/progress", response_model=SceneProgressResponse)
async def progress_to_next_scene(
    request: SceneProgressRequest,
    db: Session = Depends(get_db)
):
    """Move user to the next scene in the simulation"""
    
    # Get user progress
    user_progress = db.query(UserProgress).filter(
        UserProgress.id == request.user_progress_id
    ).first()
    
    if not user_progress:
        raise HTTPException(status_code=404, detail="User progress not found")
    
    # Get current scene
    current_scene = db.query(ScenarioScene).filter(
        ScenarioScene.id == request.current_scene_id
    ).first()
    
    if not current_scene:
        raise HTTPException(status_code=404, detail="Current scene not found")
    
    # Update scene progress
    scene_progress = db.query(SceneProgress).filter(
        and_(
            SceneProgress.user_progress_id == request.user_progress_id,
            SceneProgress.scene_id == request.current_scene_id
        )
    ).first()
    
    if scene_progress:
        scene_progress.status = "completed"
        scene_progress.goal_achieved = request.goal_achieved
        scene_progress.forced_progression = request.forced_progression
        scene_progress.completed_at = datetime.utcnow()
        
        if request.forced_progression:
            user_progress.forced_progressions += 1
    
    # Update user progress - add completed scene
    completed_scenes = user_progress.scenes_completed or []
    if request.current_scene_id not in completed_scenes:
        completed_scenes.append(request.current_scene_id)
        user_progress.scenes_completed = completed_scenes
    
    # Find next scene
    next_scene = db.query(ScenarioScene).filter(
        and_(
            ScenarioScene.scenario_id == user_progress.scenario_id,
            ScenarioScene.scene_order > current_scene.scene_order
        )
    ).order_by(ScenarioScene.scene_order).first()
    
    if next_scene:
        # Move to next scene
        user_progress.current_scene_id = next_scene.id
        user_progress.last_activity = datetime.utcnow()
        
        # Create scene progress for next scene
        next_scene_progress = SceneProgress(
            user_progress_id=request.user_progress_id,
            scene_id=next_scene.id,
            status="in_progress",
            started_at=datetime.utcnow()
        )
        db.add(next_scene_progress)
        
        # Clear conversation history and restart all agents for scene transition
        print("Scene transition detected - clearing conversation history and restarting agents for new scene")
        
        # Note: We need to get the orchestrator instance to access the agent manager
        # For now, we'll clear conversation history and let the system recreate agents
        print("Scene transition clearing - this will be handled by the orchestrator when it's recreated")
        
        # Get all personas for the scenario
        scene_personas = db.query(ScenarioPersona).filter(
            ScenarioPersona.scenario_id == user_progress.scenario_id
        ).all()
        
        # Get personas involved in this specific scene
        from database.models import scene_personas as scene_personas_table
        involved_personas = db.query(ScenarioPersona).join(
            scene_personas_table, ScenarioPersona.id == scene_personas_table.c.persona_id
        ).filter(
            scene_personas_table.c.scene_id == next_scene.id
        ).all()
        involved_persona_names = [p.name for p in involved_personas]
        
        # Helper function to check if persona is the main character
        def is_main_character_progress(persona_name, student_role):
            if not student_role:
                return False
            # Extract just the name part from student role (before any parentheses or additional info)
            student_name = student_role.split('(')[0].strip().lower()
            persona_name_clean = persona_name.strip().lower()
            return persona_name_clean == student_name

        personas_data = [
            ScenarioPersonaResponse(
                id=persona.id,
                scenario_id=persona.scenario_id,
                name=persona.name,
                role=persona.role,
                background=persona.background,
                correlation=persona.correlation,
                primary_goals=(
                    [persona.primary_goals] if isinstance(persona.primary_goals, str) and persona.primary_goals else
                    persona.primary_goals if isinstance(persona.primary_goals, list) else []
                ),
                personality_traits=persona.personality_traits or {},
                image_url=persona.image_url,
                created_at=persona.created_at,
                updated_at=persona.updated_at
            ) for persona in scene_personas
            if not is_main_character_progress(persona.name, user_progress.scenario.student_role)
        ]
        
        next_scene_data = ScenarioSceneResponse(
            id=next_scene.id,
            scenario_id=next_scene.scenario_id,
            title=next_scene.title,
            description=next_scene.description,
            user_goal=next_scene.user_goal,
            scene_order=next_scene.scene_order,
            estimated_duration=next_scene.estimated_duration,
            image_url=next_scene.image_url,
            image_prompt=next_scene.image_prompt,
            timeout_turns=next_scene.timeout_turns,  # Ensure this is included
            success_metric=next_scene.success_metric,  # Ensure this is included
            personas_involved=involved_persona_names,  # Add personas_involved
            created_at=next_scene.created_at,
            updated_at=next_scene.updated_at,
            personas=personas_data
        )
        
        db.commit()
        
        # Return all required fields for SceneProgressResponse
        return SceneProgressResponse(
            id=scene_progress.id,
            scene_id=scene_progress.scene_id,
            status=scene_progress.status,
            attempts=scene_progress.attempts,
            hints_used=scene_progress.hints_used,
            goal_achieved=scene_progress.goal_achieved,
            forced_progression=scene_progress.forced_progression,
            time_spent=scene_progress.time_spent,
            messages_sent=scene_progress.messages_sent,
            ai_responses=scene_progress.ai_responses,
            goal_achievement_score=scene_progress.goal_achievement_score,
            interaction_quality=scene_progress.interaction_quality,
            scene_feedback=scene_progress.scene_feedback,
            started_at=scene_progress.started_at,
            completed_at=scene_progress.completed_at,
            success=True,
            next_scene=next_scene_data,
            simulation_complete=False
        )
    else:
        # Simulation complete
        user_progress.simulation_status = "completed"
        user_progress.completed_at = datetime.utcnow()
        user_progress.completion_percentage = 100.0
        
        # Calculate final score (simple average of scene scores)
        all_scene_progress = db.query(SceneProgress).filter(
            SceneProgress.user_progress_id == request.user_progress_id
        ).all()
        
        if all_scene_progress:
            scores = [sp.goal_achievement_score for sp in all_scene_progress if sp.goal_achievement_score]
            if scores:
                user_progress.final_score = sum(scores) / len(scores)
        
        db.commit()
        
        # Create a default scene progress response if scene_progress is None
        if scene_progress is None:
            # Create a minimal scene progress response for completion
            return SceneProgressResponse(
                id=0,  # Use 0 as a placeholder ID
                scene_id=request.current_scene_id,
                status="completed",
                attempts=0,
                hints_used=0,
                goal_achieved=request.goal_achieved,
                forced_progression=request.forced_progression,
                time_spent=0,
                messages_sent=0,
                ai_responses=0,
                goal_achievement_score=None,
                interaction_quality=None,
                scene_feedback=None,
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                success=True,
                simulation_complete=True,
                completion_summary="Congratulations! You have completed the simulation."
            )
        else:
            return SceneProgressResponse(
                id=scene_progress.id,
                scene_id=scene_progress.scene_id,
                status=scene_progress.status,
                attempts=scene_progress.attempts,
                hints_used=scene_progress.hints_used,
                goal_achieved=scene_progress.goal_achieved,
                forced_progression=scene_progress.forced_progression,
                time_spent=scene_progress.time_spent,
                messages_sent=scene_progress.messages_sent,
                ai_responses=scene_progress.ai_responses,
                goal_achievement_score=scene_progress.goal_achievement_score,
                interaction_quality=scene_progress.interaction_quality,
                scene_feedback=scene_progress.scene_feedback,
                started_at=scene_progress.started_at,
                completed_at=scene_progress.completed_at,
                success=True,
                simulation_complete=True,
                completion_summary="Congratulations! You have completed the simulation."
            )

@router.get("/progress/{user_progress_id}", response_model=UserProgressResponse)
async def get_user_progress(
    user_progress_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed user progress for a simulation"""
    
    user_progress = db.query(UserProgress).filter(
        UserProgress.id == user_progress_id
    ).first()
    
    if not user_progress:
        raise HTTPException(status_code=404, detail="User progress not found")
    
    # Verify that the user_progress belongs to the current user
    if user_progress.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied: You can only access your own simulation progress")
    
    return UserProgressResponse(
        id=user_progress.id,
        user_id=user_progress.user_id,
        scenario_id=user_progress.scenario_id,
        current_scene_id=user_progress.current_scene_id,
        simulation_status=user_progress.simulation_status,
        scenes_completed=user_progress.scenes_completed or [],
        total_attempts=user_progress.total_attempts,
        hints_used=user_progress.hints_used,
        forced_progressions=user_progress.forced_progressions,
        completion_percentage=user_progress.completion_percentage,
        total_time_spent=user_progress.total_time_spent,
        session_count=user_progress.session_count,
        final_score=user_progress.final_score,
        started_at=user_progress.started_at,
        completed_at=user_progress.completed_at,
        last_activity=user_progress.last_activity
    ) 

@router.get("/scenes/{scene_id}", response_model=ScenarioSceneResponse)
async def get_scene_by_id(
    scene_id: int,
    db: Session = Depends(get_db)
):
    """Get scene data by ID"""
    
    scene = db.query(ScenarioScene).filter(ScenarioScene.id == scene_id).first()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    
    # Get personas involved in this specific scene through the junction table
    from database.models import scene_personas
    scene_personas = db.query(ScenarioPersona).join(
        scene_personas, ScenarioPersona.id == scene_personas.c.persona_id
    ).filter(
        scene_personas.c.scene_id == scene.id
    ).all()
    
    # Get scenario to check student role for main character filtering
    scenario = db.query(Scenario).filter(Scenario.id == scene.scenario_id).first()
    
    # Helper function to check if persona is the main character
    def is_main_character_scene(persona_name, student_role):
        if not student_role:
            return False
        # Extract just the name part from student role (before any parentheses or additional info)
        student_name = student_role.split('(')[0].strip().lower()
        persona_name_clean = persona_name.strip().lower()
        return persona_name_clean == student_name

    personas_data = [
        ScenarioPersonaResponse(
            id=persona.id,
            scenario_id=persona.scenario_id,
            name=persona.name,
            role=persona.role,
            background=persona.background,
            correlation=persona.correlation,
            primary_goals=(
                [persona.primary_goals] if isinstance(persona.primary_goals, str) and persona.primary_goals else
                persona.primary_goals if isinstance(persona.primary_goals, list) else []
            ),
            personality_traits=persona.personality_traits or {},
            image_url=persona.image_url,
            created_at=persona.created_at,
            updated_at=persona.updated_at
        ) for persona in scene_personas
        if not is_main_character_scene(persona.name, scenario.student_role if scenario else None)
    ]
    
    return ScenarioSceneResponse(
        id=scene.id,
        scenario_id=scene.scenario_id,
        title=scene.title,
        description=scene.description,
        user_goal=scene.user_goal,
        scene_order=scene.scene_order,
        estimated_duration=scene.estimated_duration,
        image_url=scene.image_url,
        image_prompt=scene.image_prompt,
        timeout_turns=scene.timeout_turns,  # Ensure this is included
        success_metric=scene.success_metric,  # Ensure this is included
        created_at=scene.created_at,
        updated_at=scene.updated_at,
        personas=personas_data
    )

@router.post("/linear-chat", response_model=SimulationChatResponse)
async def linear_simulation_chat(
    request: SimulationChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Handle orchestrated chat interactions in linear simulation"""
    # Import ChatOrchestrator at the top of the function
    from api.chat_orchestrator import ChatOrchestrator
    
    def _safe_scene_id():
        # Use the correct scene ID from the current scene if available
        if 'correct_scene_id' in locals():
            return correct_scene_id
        scene_id = getattr(orchestrator.state, 'current_scene_id', None)
        if not isinstance(scene_id, int):
            scene_id = getattr(user_progress, 'current_scene_id', None)
            if not isinstance(scene_id, int):
                scene_id = None
        return scene_id
    
    # Initialize variables for return statement
    scene_completed = False
    next_scene_id = None
    timeout_turns = 15  # Default value
    scene_intro_message = None  # Will be set if a new scene starts
    
    try:
        # Get user progress - user_progress_id is required
        if not request.user_progress_id:
            raise HTTPException(
                status_code=400, 
                detail="user_progress_id is required"
            )
        
        user_progress = db.query(UserProgress).filter(
            UserProgress.id == request.user_progress_id
        ).first()
        
        if not user_progress:
            raise HTTPException(status_code=404, detail="User progress not found")
        
        # Verify that the user_progress belongs to the current user
        if user_progress.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied: You can only access your own simulation data")
        
        if not user_progress.orchestrator_data:
            raise HTTPException(status_code=400, detail="Simulation not properly initialized")
        
        # Initialize orchestrator with LangChain enabled
        # Check if this is a professor test simulation
        is_professor_test = current_user.role in ['professor', 'admin']
        orchestrator = ChatOrchestrator(user_progress.orchestrator_data, enable_langchain=True, is_professor_test=is_professor_test)
        orchestrator.user_progress_id = user_progress.id
        
        # Initialize LangChain session if not already done
        if orchestrator.langchain_enabled and not orchestrator.state.scene_memory_initialized:
            await orchestrator.initialize_langchain_session(user_progress.id)
        
        # Load saved state if it exists
        if user_progress.orchestrator_data and 'state' in user_progress.orchestrator_data:
            saved_state = user_progress.orchestrator_data['state']
            orchestrator.state.simulation_started = saved_state.get('simulation_started', False)
            orchestrator.state.user_ready = saved_state.get('user_ready', False)
            orchestrator.state.current_scene_index = saved_state.get('current_scene_index', 0)
        
        # Professor test simulations will only clear conversation history on scene transitions
        # This preserves context within the same test session until the user moves to a new scene
        if current_user.role in ['professor', 'admin'] and user_progress.user_id == current_user.id and orchestrator.langchain_enabled:
            print("Professor test simulation detected - conversation history will be cleared on scene transitions only")
        
        # Check if this is a new scene (scene transition) and clear conversation history
        # This ensures each scene starts with fresh conversation context
        if orchestrator.langchain_enabled:
            # Initialize _last_scene_id if not set
            if not hasattr(orchestrator, '_last_scene_id'):
                orchestrator._last_scene_id = None
            
            # Initialize current_scene_id from user progress if not set
            print(f"[DEBUG] Before initialization - orchestrator.state.current_scene_id: {getattr(orchestrator.state, 'current_scene_id', 'NOT_SET')}")
            print(f"[DEBUG] user_progress.current_scene_id: {user_progress.current_scene_id}")
            if not hasattr(orchestrator.state, 'current_scene_id') or orchestrator.state.current_scene_id is None or orchestrator.state.current_scene_id == "":
                orchestrator.state.current_scene_id = user_progress.current_scene_id
                print(f"[DEBUG] Initialized orchestrator.state.current_scene_id from user_progress: {orchestrator.state.current_scene_id}")
            else:
                print(f"[DEBUG] orchestrator.state.current_scene_id already set to: {orchestrator.state.current_scene_id}")
            
            # Check if we're in a different scene than before
            current_scene_id = orchestrator.state.current_scene_id
            print(f"[DEBUG] Scene transition check - _last_scene_id: {orchestrator._last_scene_id}, current_scene_id: {current_scene_id}")
            
            # Clear conversation history on scene transitions
            if orchestrator._last_scene_id is not None and orchestrator._last_scene_id != current_scene_id:
                print(f"Scene transition detected: {orchestrator._last_scene_id} -> {current_scene_id}")
                print("Scene transition detected - clearing conversation history for new scene")
                
                # Clear conversation history for all existing persona agents
                if hasattr(orchestrator, 'persona_agents') and orchestrator.persona_agents:
                    print(f"[DEBUG] Found {len(orchestrator.persona_agents)} existing persona agents to clear")
                    for persona_id, agent in orchestrator.persona_agents.items():
                        print(f"[DEBUG] Clearing conversation history for existing agent: {persona_id}")
                        agent.clear_conversation_history(user_progress.id)
                        print(f"Cleared conversation history for existing persona agent: {persona_id}")
            elif orchestrator._last_scene_id is None:
                print(f"[DEBUG] First time setting _last_scene_id to: {current_scene_id}")
            
            # Store current scene ID for next comparison
            orchestrator._last_scene_id = current_scene_id
            orchestrator.state.turn_count = saved_state.get('turn_count', 0)
            orchestrator.state.state_variables = saved_state.get('state_variables', {})
        # Get current scene and timeout_turns
        current_scene = orchestrator.scenario.get('scenes', [{}])[orchestrator.state.current_scene_index]
        timeout_turns = current_scene.get('timeout_turns') or current_scene.get('max_turns', 15)
        
        # Ensure we're using the correct scene_id (frontend might send wrong one after scene change)
        correct_scene_id = current_scene.get('id')
        
        # Handle "begin" command to start simulation
        if request.message.lower().strip() == "begin":
            # Save "begin" user message to conversation log
            last_msg = db.query(ConversationLog).filter(
                ConversationLog.user_progress_id == user_progress.id
            ).order_by(desc(ConversationLog.message_order)).first()
            begin_order = (last_msg.message_order + 1) if last_msg else 1
            
            begin_user_log = ConversationLog(
                user_progress_id=user_progress.id,
                scene_id=user_progress.current_scene_id,
                message_type="user",
                sender_name="User",
                message_content=request.message,
                message_order=begin_order,
                timestamp=datetime.utcnow()
            )
            db.add(begin_user_log)
            db.flush()
            print(f"[DEBUG] Logged 'begin' command with order {begin_order}")
            
            if orchestrator.state.simulation_started:
                ai_response = "The simulation has already begun. You can now interact with team members using @mentions (e.g., @rahul_ashok) or ask for help."
                persona_name = "ChatOrchestrator"
                persona_id = None
            else:
                # Start simulation
                orchestrator.state.simulation_started = True
                orchestrator.state.user_ready = True
                user_progress.simulation_status = "in_progress"
                
                # Don't overwrite orchestrator_data, just update the state
                # user_progress.orchestrator_data already contains the scenario data
                
                # Save the updated state immediately
                state_dict = {
                    'current_scene_id': orchestrator.state.current_scene_id,
                    'current_scene_index': orchestrator.state.current_scene_index,
                    'turn_count': orchestrator.state.turn_count,
                    'simulation_started': orchestrator.state.simulation_started,
                    'user_ready': orchestrator.state.user_ready,
                    'state_variables': orchestrator.state.state_variables
                }
                
                if user_progress.orchestrator_data:
                    user_progress.orchestrator_data['state'] = state_dict
                else:
                    user_progress.orchestrator_data = {'state': state_dict}
                
                # Mark the JSON field as modified so SQLAlchemy will update it
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(user_progress, "orchestrator_data")
                
                # Commit the state change immediately
                db.commit()
                print(f"[DEBUG] Saved state after begin - simulation_started: {state_dict['simulation_started']}")
                
                # Generate cinematic prologue (scenario introduction only)
                scenario = user_progress.orchestrator_data
                prologue = f"""# {scenario['title']}

{scenario['description']}

**Challenge:** {scenario['challenge']}

You are about to enter a multi-scene simulation where you'll interact with various team members to achieve specific objectives. Each scene has its own goals and participants.

**Available Agents:**
"""
                for persona in scenario['personas']:
                    name = persona['identity']['name']
                    role = persona['identity']['role']
                    bio = persona['identity']['bio']
                    prologue += f"• @{persona['id']}: {name} ({role}) - {bio}\n"
                
                prologue += f"""
**Instructions:** Use @mentions to speak with specific agents (e.g., @{scenario['personas'][0]['id']}). Type 'help' for assistance.

*The simulation begins now...*
"""
                ai_response = prologue
                persona_name = "ChatOrchestrator"
                persona_id = None
                
                # Note: Scene introduction will be saved AFTER the prologue response is logged
                # This ensures proper message ordering
                # We'll set the scene_intro_message flag to save it later
        
        elif request.message.lower().strip() == "help":
            ai_response = f"""**Help - Simulation Commands**

**@mention syntax:** Use @agent_id to speak with specific agents
**Current Goal:** {orchestrator._get_current_scene_goal()}
**Turns Remaining:** {orchestrator._get_turns_remaining()}

**Available Commands:**
• help - Show this help
• begin - Start the simulation (if not started)

**Current Scene:** Scene {orchestrator.state.current_scene_index + 1} of {len(orchestrator.scenes)}
"""
            persona_name = "ChatOrchestrator"
            persona_id = None
        
        elif request.message.strip() == "SUBMIT_FOR_GRADING":
            # Special message to submit current scene for grading
            print(f"[DEBUG] SUBMIT_FOR_GRADING message received")
            
            # Define scene_id_to_use first
            scene_id_to_use = request.scene_id if request.scene_id is not None else user_progress.current_scene_id
            print(f"[DEBUG] SUBMIT_FOR_GRADING - scene_id_to_use: {scene_id_to_use}")
            
            # No need to check for duplicates since we're not logging SUBMIT_FOR_GRADING messages
            
            # Don't log SUBMIT_FOR_GRADING to conversation - it's a UI action, not a user message
            print(f"[DEBUG] SUBMIT_FOR_GRADING - UI action, not logging to conversation")
            
            # For SUBMIT_FOR_GRADING, we want to force progression regardless of goal achievement
            # Check if there's a next scene available
            print(f"[DEBUG] (Submit) Current scene index: {orchestrator.state.current_scene_index}")
            print(f"[DEBUG] (Submit) Total scenes: {len(orchestrator.scenario.get('scenes', []))}")
            
            if orchestrator.state.current_scene_index + 1 < len(orchestrator.scenario.get('scenes', [])):
                # Move to next scene
                next_scene_index = orchestrator.state.current_scene_index + 1
                next_scene = orchestrator.scenario.get('scenes', [])[next_scene_index]
                next_scene_id = next_scene.get('id')
                print(f"[DEBUG] (Submit) Moving to next scene: index={next_scene_index}, id={next_scene_id}, title={next_scene.get('title')}")
                
                scene_completed = True
                ai_response = f"🎉 **Scene Submitted!** Moving to next scene:\n\n**{next_scene.get('title', 'Next Scene')}**\n\n**Objective:** {next_scene.get('objectives', ['Continue the simulation'])[0]}"
                
                # Update orchestrator state
                orchestrator.state.current_scene_index = next_scene_index
                orchestrator.state.turn_count = 0
                print(f"[DEBUG] TURN COUNT RESET TO 0 ON SUBMIT PROGRESSION")
                orchestrator.state.scene_completed = False
                orchestrator.state.current_scene_id = next_scene_id
                
                # Clear conversation history and restart all agents for scene transition
                if orchestrator.langchain_enabled:
                    print(f"[DEBUG] SUBMIT_FOR_GRADING - Clearing conversation history and restarting agents for scene transition")
                    from agents.persona_agent import PersonaAgent, PersonaAgentManager
                    
                    # Clear all existing agents for this session to force restart
                    if hasattr(orchestrator, 'persona_agent_manager'):
                        orchestrator.persona_agent_manager.clear_session_agents(f"user_{user_progress.id}")
                        print(f"[DEBUG] SUBMIT_FOR_GRADING - Cleared all existing agents for session")
                    
                    # Clear the ACTUAL persona agents in the orchestrator, not temporary ones
                    if hasattr(orchestrator, 'persona_agents') and orchestrator.persona_agents:
                        print(f"[DEBUG] SUBMIT_FOR_GRADING - Found {len(orchestrator.persona_agents)} existing persona agents to clear")
                        for agent_id, persona_agent in orchestrator.persona_agents.items():
                            print(f"[DEBUG] SUBMIT_FOR_GRADING - Clearing conversation history for existing agent: {agent_id}")
                            result = persona_agent.clear_conversation_history(user_progress.id)
                            print(f"[DEBUG] SUBMIT_FOR_GRADING - clear_conversation_history result: {result}")
                            print(f"[DEBUG] SUBMIT_FOR_GRADING - Cleared conversation history for existing persona agent: {agent_id}")
                    else:
                        print(f"[DEBUG] SUBMIT_FOR_GRADING - No existing persona agents found in orchestrator - skipping clearing")
                print(f"[DEBUG] NEW SCENE START (after submit progression): index={orchestrator.state.current_scene_index}, turn_count={orchestrator.state.turn_count}, scene_id={next_scene_id}")
                
                # CRITICAL: Update UserProgress.current_scene_id to match the orchestrator state
                user_progress.current_scene_id = next_scene_id
                print(f"[DEBUG] Updated UserProgress.current_scene_id to {next_scene_id}")
                
                # Clear the ACTUAL persona agents in the orchestrator, not temporary ones
                if orchestrator.langchain_enabled:
                    print("Scene transition detected - clearing conversation history for new scene")
                    if hasattr(orchestrator, 'persona_agents') and orchestrator.persona_agents:
                        print(f"[DEBUG] Found {len(orchestrator.persona_agents)} existing persona agents to clear")
                        for agent_id, persona_agent in orchestrator.persona_agents.items():
                            print(f"[DEBUG] Clearing conversation history for existing agent: {agent_id}")
                            persona_agent.clear_conversation_history(user_progress.id)
                            print(f"Cleared conversation history for existing persona agent: {agent_id}")
                    else:
                        print(f"[DEBUG] No existing persona agents found in orchestrator - skipping clearing")
                
                # Mark current scene as completed in UserProgress
                completed_scenes = user_progress.scenes_completed or []
                if scene_id_to_use and scene_id_to_use not in completed_scenes:
                    completed_scenes.append(scene_id_to_use)
                    user_progress.scenes_completed = completed_scenes
                    print(f"[DEBUG] Added scene {scene_id_to_use} to completed scenes: {completed_scenes}")
                
                # Update SceneProgress for the completed scene
                scene_progress = db.query(SceneProgress).filter(
                    and_(
                        SceneProgress.user_progress_id == user_progress.id,
                        SceneProgress.scene_id == scene_id_to_use
                    )
                ).first()
                
                if scene_progress:
                    scene_progress.status = "completed"
                    scene_progress.completed_at = datetime.utcnow()
                    print(f"[DEBUG] Marked SceneProgress {scene_id_to_use} as completed")
                
                # Create SceneProgress for the new scene
                new_scene_progress = db.query(SceneProgress).filter(
                    and_(
                        SceneProgress.user_progress_id == user_progress.id,
                        SceneProgress.scene_id == next_scene_id
                    )
                ).first()
                
                if not new_scene_progress:
                    new_scene_progress = SceneProgress(
                        user_progress_id=user_progress.id,
                        scene_id=next_scene_id,
                        status="in_progress",
                        started_at=datetime.utcnow()
                    )
                    db.add(new_scene_progress)
                    print(f"[DEBUG] Created SceneProgress for new scene {next_scene_id}")
                else:
                    new_scene_progress.status = "in_progress"
                    new_scene_progress.started_at = datetime.utcnow()
                    print(f"[DEBUG] Reactivated SceneProgress for scene {next_scene_id}")
                
                # Update timeout_turns for the new scene
                new_scene = orchestrator.scenario.get('scenes', [{}])[next_scene_index]
                new_timeout_turns = new_scene.get('timeout_turns') or new_scene.get('max_turns', 15)
                print(f"[DEBUG] NEW SCENE timeout_turns: {new_timeout_turns}")
                
                # --- PATCH: Persist orchestrator state to DB after progression ---
                state_dict = {
                    'current_scene_id': orchestrator.state.current_scene_id,
                    'current_scene_index': orchestrator.state.current_scene_index,
                    'turn_count': orchestrator.state.turn_count,
                    'simulation_started': orchestrator.state.simulation_started,
                    'user_ready': orchestrator.state.user_ready,
                    'state_variables': orchestrator.state.state_variables
                }
                user_progress.orchestrator_data['state'] = state_dict
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(user_progress, "orchestrator_data")
                db.commit()
                print(f"[DEBUG] SUBMIT_FOR_GRADING - Saved orchestrator state after progression: {state_dict}")
                
                # Save scene introduction message to database for the new scene
                next_scene_from_db = db.query(ScenarioScene).filter(
                    ScenarioScene.id == next_scene_id
                ).first()
                
                if next_scene_from_db:
                    # Check if scene intro already exists for this scene
                    existing_intro = db.query(ConversationLog).filter(
                        ConversationLog.user_progress_id == user_progress.id,
                        ConversationLog.scene_id == next_scene_id,
                        ConversationLog.message_type == "system",
                        ConversationLog.sender_name == "System"
                    ).first()
                    
                    if not existing_intro:
                        # Get the next message order
                        last_msg = db.query(ConversationLog).filter(
                            ConversationLog.user_progress_id == user_progress.id
                        ).order_by(desc(ConversationLog.message_order)).first()
                        next_order = (last_msg.message_order + 1) if last_msg else 1
                        
                        scene_intro_text = generate_scene_intro_message(next_scene, next_scene_from_db, db)
                        scene_intro_log = ConversationLog(
                            user_progress_id=user_progress.id,
                            scene_id=next_scene_id,
                            message_type="system",
                            sender_name="System",
                            persona_id=None,
                            message_content=scene_intro_text,
                            message_order=next_order,
                            timestamp=datetime.utcnow()
                        )
                        db.add(scene_intro_log)
                        db.commit()  # Commit immediately to ensure it's saved before early return
                        scene_intro_message = scene_intro_text  # Set for response
                        print(f"[DEBUG] Saved and COMMITTED scene introduction message to database for new scene {next_scene_id} with order {next_order}")
                    else:
                        print(f"[DEBUG] Scene intro already exists for scene {next_scene_id}, skipping")
                # --- END PATCH ---
                
                # Get the full next scene object for the frontend
                orchestrator_personas = orchestrator.scenario.get('personas', [])
                print(f"[DEBUG] SUBMIT_FOR_GRADING - Available orchestrator personas: {orchestrator_personas}")
                
                # Convert orchestrator persona format to frontend-expected format
                # BUT ONLY include personas involved in this specific scene
                personas_involved_names = next_scene.get('personas_involved', [])
                print(f"[DEBUG] SUBMIT_FOR_GRADING - Personas involved in next scene: {personas_involved_names}")
                
                # Prefetch scenario and all personas to avoid N+1 queries
                scenario = db.query(Scenario).filter(Scenario.id == user_progress.scenario_id).first()
                
                # Get all persona IDs and batch fetch their image URLs
                persona_db_ids = [p.get('db_id') for p in orchestrator_personas if p.get('db_id')]
                persona_map = {}
                if persona_db_ids:
                    db_personas = db.query(ScenarioPersona).filter(
                        ScenarioPersona.id.in_(persona_db_ids)
                    ).all()
                    persona_map = {p.id: p.image_url for p in db_personas}
                
                # Helper function to check if persona is the main character
                def is_main_character_submit(persona_name, student_role):
                    if not student_role:
                        return False
                    # Extract just the name part from student role (before any parentheses or additional info)
                    student_name = student_role.split('(')[0].strip().lower()
                    persona_name_clean = persona_name.strip().lower()
                    return persona_name_clean == student_name
                
                personas = []
                for persona in orchestrator_personas:
                    persona_name = persona.get('identity', {}).get('name', '')
                    # Only include personas that are involved in this scene AND not the main character
                    if persona_name in personas_involved_names:
                        if scenario and not is_main_character_submit(persona_name, scenario.student_role):
                            # Get image_url from preloaded map
                            image_url = persona_map.get(persona.get('db_id'))
                            
                            personas.append({
                                'id': persona.get('id', ''),
                                'name': persona_name,
                                'role': persona.get('identity', {}).get('role', ''),
                                'background': persona.get('identity', {}).get('bio', ''),
                                'correlation': '',
                                'primary_goals': persona.get('personality', {}).get('goals', []),
                                'personality_traits': persona.get('personality', {}).get('traits', {}),
                                'image_url': image_url,
                                'created_at': None,
                                'updated_at': None
                            })
                            print(f"[DEBUG] SUBMIT_FOR_GRADING - Included persona: {persona_name}")
                        else:
                            print(f"[DEBUG] SUBMIT_FOR_GRADING - Excluded persona: {persona_name} (main character)")
                    else:
                        print(f"[DEBUG] SUBMIT_FOR_GRADING - Excluded persona: {persona_name} (not involved in scene)")
                
                print(f"[DEBUG] SUBMIT_FOR_GRADING - Filtered personas for scene: {[p['name'] for p in personas]}")
                next_scene_obj = {
                    'id': next_scene.get('id'),
                    'title': next_scene.get('title'),
                    'description': next_scene.get('description'),
                    'objectives': next_scene.get('objectives', []),
                    'image_url': next_scene.get('image_url'),
                    'scene_order': next_scene_index + 1,  # scene_order is 1-based
                    'user_goal': next_scene.get('objectives', ['Continue the simulation'])[0] if next_scene.get('objectives') else 'Continue the simulation',
                    'timeout_turns': next_scene.get('timeout_turns') or next_scene.get('max_turns', 15),
                    'personas': personas,  # Only personas involved in this specific scene
                    'personas_involved': personas_involved_names  # Add personas_involved
                }
                print(f"[DEBUG] SUBMIT_FOR_GRADING - next_scene_obj personas: {next_scene_obj.get('personas')}")
            else:
                # No more scenes - simulation complete
                scene_completed = True
                next_scene_id = None
                ai_response = "🎉 **Congratulations! You have completed the entire simulation.**"
                print(f"[DEBUG] Simulation complete via SUBMIT_FOR_GRADING")
                print(f"[DEBUG] (Submit) No more scenes available, simulation complete")
            
            persona_name = "System"
            persona_id = None
            
            # Return immediately to prevent further processing
            print(f"[DEBUG] SUBMIT_FOR_GRADING - Returning early with scene_completed: {scene_completed}, next_scene_id: {next_scene_id}, scene_intro: {scene_intro_message is not None}")
            return SimulationChatResponse(
                message=ai_response,
                scene_id=_safe_scene_id(),
                scene_completed=scene_completed,
                next_scene_id=next_scene_id,
                next_scene=next_scene_obj if 'next_scene_obj' in locals() else None,
                persona_name=persona_name,
                persona_id=str(persona_id) if persona_id is not None else None,  # Convert to str at API boundary
                turn_count=orchestrator.state.turn_count,
                scene_intro_message=scene_intro_message  # Include scene intro message
            )
        
        else:
            # --- PATCH START: Timeout Turns Enforcement ---
            # Recalculate timeout_turns in case scene changed
            current_scene = orchestrator.scenario.get('scenes', [{}])[orchestrator.state.current_scene_index]
            timeout_turns = current_scene.get('timeout_turns') or current_scene.get('max_turns', 15)
            print(f"[DEBUG] Scene index: {orchestrator.state.current_scene_index}, timeout_turns: {timeout_turns}, scene: {current_scene}")
            should_increment = request.message.lower().strip() not in ["help", "begin"]
            if should_increment:
                # Log user message to ConversationLog
                scene_id_to_use = request.scene_id if request.scene_id is not None else user_progress.current_scene_id
                
                # Get the next message order
                last_msg = db.query(ConversationLog).filter(
                    ConversationLog.user_progress_id == user_progress.id
                ).order_by(desc(ConversationLog.message_order)).first()
                next_order = (last_msg.message_order + 1) if last_msg else 1
                
                user_log = ConversationLog(
                    user_progress_id=user_progress.id,
                    scene_id=scene_id_to_use,
                    message_type="user",
                    sender_name="User",
                    message_content=request.message,
                    message_order=next_order,
                    attempt_number=0,  # Set to 0 or actual attempt if tracked
                    timestamp=datetime.utcnow()
                )
                db.add(user_log)
                db.flush()
                print(f"[DEBUG] Logged user message: {request.message} with order {next_order} (user_progress_id={user_progress.id}, scene_id={scene_id_to_use})")
                orchestrator.state.turn_count = orchestrator.state.turn_count + 1 if hasattr(orchestrator.state, 'turn_count') else 1
                print(f"[DEBUG] AFTER INCREMENT: turn_count={orchestrator.state.turn_count}, timeout_turns={timeout_turns}")
            print(f"[DEBUG] ABOUT TO CHECK TURN LIMIT: turn_count={orchestrator.state.turn_count}, timeout_turns={timeout_turns}")
            print(f"[DEBUG] TIMEOUT CHECK: {orchestrator.state.turn_count} >= {timeout_turns} = {orchestrator.state.turn_count >= timeout_turns}")
            
            # --- CRITICAL: Check for timeout turns BEFORE generating AI response ---
            if orchestrator.state.turn_count >= timeout_turns:
                print(f"[DEBUG] TIMEOUT REACHED: turn_count={orchestrator.state.turn_count}, timeout_turns={timeout_turns} - FORCING SCENE PROGRESSION")
                
                # Find next scene
                if orchestrator.state.current_scene_index + 1 < len(orchestrator.scenario.get('scenes', [])):
                    next_scene_index = orchestrator.state.current_scene_index + 1
                    next_scene = orchestrator.scenario.get('scenes', [])[next_scene_index]
                    next_scene_id = next_scene.get('id')
                    print(f"[DEBUG] TIMEOUT PROGRESSION: Moving to next scene: index={next_scene_index}, id={next_scene_id}, title={next_scene.get('title')}")
                    
                    # Update orchestrator state
                    orchestrator.state.current_scene_index = next_scene_index
                    orchestrator.state.turn_count = 0
                    orchestrator.state.scene_completed = False
                    orchestrator.state.current_scene_id = next_scene_id
                    
                    # Update database state for timeout progression
                    user_progress.current_scene_id = next_scene_id
                    completed_scenes = user_progress.scenes_completed or []
                    current_scene_id = orchestrator.scenario.get('scenes', [{}])[orchestrator.state.current_scene_index - 1].get('id')
                    if current_scene_id and current_scene_id not in completed_scenes:
                        completed_scenes.append(current_scene_id)
                        user_progress.scenes_completed = completed_scenes
                    
                    # Mark scene progress as completed with forced progression
                    scene_progress = db.query(SceneProgress).filter(
                        and_(
                            SceneProgress.user_progress_id == user_progress.id,
                            SceneProgress.scene_id == current_scene_id
                        )
                    ).first()
                    
                    if scene_progress:
                        scene_progress.status = "completed"
                        scene_progress.goal_achieved = False  # Timeout means goal not achieved
                        scene_progress.forced_progression = True
                        scene_progress.completed_at = datetime.utcnow()
                        user_progress.forced_progressions += 1
                    
                    # Create SceneProgress for new scene
                    new_scene_progress = db.query(SceneProgress).filter(
                        and_(
                            SceneProgress.user_progress_id == user_progress.id,
                            SceneProgress.scene_id == next_scene_id
                        )
                    ).first()
                    
                    if not new_scene_progress:
                        new_scene_progress = SceneProgress(
                            user_progress_id=user_progress.id,
                            scene_id=next_scene_id,
                            status="in_progress",
                            started_at=datetime.utcnow()
                        )
                        db.add(new_scene_progress)
                    
                    # Save scene introduction message for the new scene
                    next_scene_from_db = db.query(ScenarioScene).filter(
                        ScenarioScene.id == next_scene_id
                    ).first()
                    
                    if next_scene_from_db:
                        existing_intro = db.query(ConversationLog).filter(
                            ConversationLog.user_progress_id == user_progress.id,
                            ConversationLog.scene_id == next_scene_id,
                            ConversationLog.message_type == "system",
                            ConversationLog.sender_name == "System"
                        ).first()
                        
                        if not existing_intro:
                            last_msg = db.query(ConversationLog).filter(
                                ConversationLog.user_progress_id == user_progress.id
                            ).order_by(desc(ConversationLog.message_order)).first()
                            next_order = (last_msg.message_order + 1) if last_msg else 1
                            
                            scene_intro_text = generate_scene_intro_message(next_scene, next_scene_from_db, db)
                            scene_intro_log = ConversationLog(
                                user_progress_id=user_progress.id,
                                scene_id=next_scene_id,
                                message_type="system",
                                sender_name="System",
                                persona_id=None,
                                message_content=scene_intro_text,
                                message_order=next_order,
                                timestamp=datetime.utcnow()
                            )
                            db.add(scene_intro_log)
                            scene_intro_message = scene_intro_text
                    
                    # Generate timeout message using ChatOrchestrator
                    timeout_msg = orchestrator.generate_timeout_message(next_scene)
                    
                    # Return timeout response immediately
                    return SimulationChatResponse(
                        message=timeout_msg,
                        scene_id=next_scene_id,
                        scene_completed=True,
                        next_scene_id=next_scene_id,
                        persona_name="System",
                        persona_id=None,
                        turn_count=0,
                        scene_intro_message=scene_intro_message
                    )
                else:
                    # No more scenes - simulation complete
                    user_progress.simulation_status = "completed"
                    user_progress.completed_at = datetime.utcnow()
                    
                    # Mark final scene as completed
                    current_scene_id = orchestrator.scenario.get('scenes', [{}])[orchestrator.state.current_scene_index].get('id')
                    completed_scenes = user_progress.scenes_completed or []
                    if current_scene_id and current_scene_id not in completed_scenes:
                        completed_scenes.append(current_scene_id)
                        user_progress.scenes_completed = completed_scenes
                    
                    scene_progress = db.query(SceneProgress).filter(
                        and_(
                            SceneProgress.user_progress_id == user_progress.id,
                            SceneProgress.scene_id == current_scene_id
                        )
                    ).first()
                    
                    if scene_progress:
                        scene_progress.status = "completed"
                        scene_progress.goal_achieved = False
                        scene_progress.forced_progression = True
                        scene_progress.completed_at = datetime.utcnow()
                        user_progress.forced_progressions += 1
                    
                    db.commit()
                    
                    # Generate final timeout message using ChatOrchestrator
                    final_timeout_msg = orchestrator.generate_timeout_message(None)  # None means final scene
                    
                    return SimulationChatResponse(
                        message=final_timeout_msg,
                        scene_id=current_scene_id,
                        scene_completed=True,
                        next_scene_id=None,
                        persona_name="System",
                        persona_id=None,
                        turn_count=orchestrator.state.turn_count,
                        simulation_complete=True
                    )
            
            # Build comprehensive conversation context and memory FIRST (before any system prompts)
            scene_id_to_use = request.scene_id if request.scene_id is not None else user_progress.current_scene_id
            
            # Get ALL conversation messages for this scene (not just recent ones)
            all_messages = db.query(ConversationLog).filter(
                and_(
                    ConversationLog.user_progress_id == user_progress.id,
                    ConversationLog.scene_id == scene_id_to_use
                )
            ).order_by(ConversationLog.message_order).all()
            
            # Build comprehensive conversation history in proper format for AI model
            conversation_context = []
            agent_memory_summary = []
            
            for msg in all_messages:
                role = "user" if msg.message_type == "user" else "assistant"
                conversation_context.append({
                    "role": role,
                    "content": msg.message_content
                })
                
                # Build agent memory summary for system prompt
                if msg.message_type in ["ai_persona", "orchestrator"] and msg.sender_name:
                    agent_memory_summary.append(f"{msg.sender_name}: {msg.message_content}")
            
            # Add the current user message
            conversation_context.append({
                "role": "user",
                "content": request.message
            })
            
            # Create comprehensive memory context for system prompt (SCENE-ISOLATED)
            memory_context = ""
            if agent_memory_summary:
                memory_context = f"\n\nPREVIOUS AGENT RESPONSES IN THIS SCENE (Scene ID: {scene_id_to_use}):\n" + "\n".join(agent_memory_summary[-10:])  # Last 10 agent responses from THIS SCENE ONLY
            
            # Also create text version for debugging
            conversation_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation_context])
            print(f"[DEBUG] Scene {scene_id_to_use} - Conversation history: {conversation_text[:500]}...")
            print(f"[DEBUG] Scene {scene_id_to_use} - Agent memory summary: {len(agent_memory_summary)} responses")
            print(f"[DEBUG] Scene {scene_id_to_use} - Memory context length: {len(memory_context)} characters")
            
            # --- PATCH: Always generate persona response, even on last turn ---
            # All persona mention handling, OpenAI calls, and goal validation logic must be below this line, not inside any else or after any return
            # Check if user is addressing a specific persona with @mention
            import re
            mention_match = re.search(r'@(\w+)', request.message)
            
            print(f"[DEBUG] User message: {request.message}")
            print(f"[DEBUG] Simulation started: {orchestrator.state.simulation_started}")
            print(f"[DEBUG] Mention match: {mention_match.group(1) if mention_match else None}")
            
            if mention_match:
                # User is addressing a specific persona
                persona_id = mention_match.group(1)
                
                # Find the persona in the scenario data with fuzzy matching
                target_persona = None
                available_personas = [p['id'] for p in orchestrator.scenario.get('personas', [])]
                print(f"[DEBUG] Looking for persona: {persona_id}")
                print(f"[DEBUG] Available personas: {available_personas}")
                
                # Create a mapping of name variations to persona IDs
                name_mapping = {}
                for persona in orchestrator.scenario.get('personas', []):
                    name = persona['identity']['name'].lower()
                    # Add various name variations
                    name_mapping[name] = persona['id']
                    name_mapping[name.replace("'", "").replace(" ", "_")] = persona['id']
                    name_mapping[name.replace("'", "").replace(" ", "")] = persona['id']
                    # Add first name only
                    first_name = name.split()[0]
                    name_mapping[first_name] = persona['id']
                    name_mapping[first_name.replace("'", "")] = persona['id']
                
                print(f"[DEBUG] Name mapping: {name_mapping}")
                # Diagnostics: list all orchestrator personas and their system_prompt status
                try:
                    orchestrator_personas = orchestrator.scenario.get('personas', [])
                    for op in orchestrator_personas:
                        op_id = op.get('id')
                        op_db_id = op.get('db_id')
                        op_name = op.get('identity', {}).get('name')
                        op_sp = op.get('system_prompt')
                        op_has = isinstance(op_sp, str) and op_sp.strip() != ""
                        op_prev = (op_sp[:80] + '…') if op_has and len(op_sp) > 80 else (op_sp or None)
                        pass
                except Exception as e:
                    print(f"[STREAM DIAG] Error listing orchestrator personas: {e}")
                # Diagnostics: list all DB personas for this scenario and their system_prompt
                try:
                    from database.models import ScenarioPersona as _DBPersona
                    scenario_id_for_db = orchestrator.scenario.get('id')
                    if scenario_id_for_db:
                        db_personas_all = db.query(_DBPersona).filter(_DBPersona.scenario_id == scenario_id_for_db).all()
                        for dp in db_personas_all:
                            dp_has = isinstance(dp.system_prompt, str) and (dp.system_prompt or '').strip() != ''
                            dp_prev = ((dp.system_prompt or '')[:80] + '…') if dp_has and len(dp.system_prompt) > 80 else (dp.system_prompt or None)
                            pass
                except Exception as e:
                    print(f"[STREAM DIAG] Error listing DB personas: {e}")
                
                # Try to find the persona by name
                search_name = persona_id.lower()
                if search_name in name_mapping:
                    persona_id = name_mapping[search_name]
                    target_persona = next((p for p in orchestrator.scenario.get('personas', []) if p['id'] == persona_id), None)
                else:
                    # Try fuzzy matching
                    for name, pid in name_mapping.items():
                        if (search_name in name or name in search_name or
                            search_name.replace("'", "").replace("_", "") in name.replace("'", "").replace("_", "")):
                            persona_id = pid
                            target_persona = next((p for p in orchestrator.scenario.get('personas', []) if p['id'] == persona_id), None)
                            break
                
                if target_persona:
                    # Prefer custom system prompt from persona if available; otherwise build default
                    persona_name = target_persona['identity']['name']
                    # Use the actual database ID for logging
                    persona_id = target_persona.get('db_id')
                    custom_prompt = target_persona.get('system_prompt')
                    # DB verification (read-only): log what's actually stored for this persona's system_prompt
                    try:
                        from database.models import ScenarioPersona as _DBPersona
                        db_check = db.query(_DBPersona).filter(_DBPersona.id == persona_id).first()
                        if db_check is not None:
                            db_prompt = db_check.system_prompt
                            has_db_prompt = isinstance(db_prompt, str) and db_prompt.strip() != ""
                            # logging removed
                            # If DB has a prompt and orchestrator persona lacks it or differs, sync and use DB value verbatim
                            if has_db_prompt and (not has_custom or (isinstance(custom_prompt, str) and custom_prompt.strip() != db_prompt.strip())):
                                # logging removed
                                system_prompt = db_prompt
                                conversation_context = [{"role": "user", "content": request.message}]
                                has_custom = True
                                prompt_locked = True
                        else:
                            pass
                    except Exception as e:
                        pass
                    has_custom = isinstance(custom_prompt, str) and custom_prompt.strip() != ""
                    # logging removed
                    if has_custom:
                        # logging removed
                        # Use custom system prompt verbatim and restrict context to only current user message
                        system_prompt = custom_prompt
                        conversation_context = [{"role": "user", "content": request.message}]
                        prompt_locked = True
                    else:
                        # Create persona data for few-shot examples
                        persona_data = {
                            'name': target_persona['identity']['name'],
                            'role': target_persona['identity']['role'],
                            'personality_traits': target_persona.get('personality', {}),
                            'primary_goals': target_persona.get('personality', {}).get('goals', [])
                        }
                        examples = few_shot_examples_service.get_adaptive_examples(persona_data, orchestrator.state.turn_count)
                        if not prompt_locked:
                            system_prompt = f"""You are {target_persona['identity']['name']}, a {target_persona['identity']['role']} in this business simulation.

{examples}

PERSONA BACKGROUND: {target_persona['identity']['bio']}

CURRENT SCENE: {orchestrator.scenario.get('scenes', [{}])[orchestrator.state.current_scene_index].get('title', '...')} - {orchestrator.scenario.get('scenes', [{}])[orchestrator.state.current_scene_index].get('description', '...')}

SCENARIO CONTEXT: {orchestrator.scenario.get('description', '')}

PERSONALITY: {target_persona.get('personality', {})}

BUSINESS SIMULATION FOCUS:
You are in a strategic business meeting about {orchestrator.scenario.get('title', '...')} to address the challenges of {orchestrator.scenario.get('challenge', '')}. 

Your role is to:
- Provide professional business insights relevant to your expertise
- Encourage strategic thinking and analytical depth in the user's approach
- Guide toward practical, implementable business solutions
- Consider multiple stakeholders and perspectives
- Use appropriate business terminology and frameworks
- Help develop the user's business acumen and strategic thinking

CRITICAL MEMORY INSTRUCTIONS:
- You have access to the COMPLETE conversation history from THIS SCENE ONLY
- You MUST remember and reference information shared in previous interactions within this scene
- If the user tells you something personal (like their birthday), you MUST remember it for this scene
- When asked about something you previously discussed in this scene, provide the specific information
- DO NOT reference information from other scenes - only use information from the current scene
- Use the conversation history to maintain continuity and context

{memory_context}

Respond as {target_persona['identity']['name']} would, providing strategic business insights and professional guidance relevant to your role and the current challenges. Focus on developing the user's business analysis skills and strategic thinking.

This is about {orchestrator.scenario.get('title', '...')} and its challenges, NOT about any other company or system.

User's message: {request.message}"""
                else:
                    # Fallback to orchestrator
                    system_prompt = f"""You are the ChatOrchestrator managing a business simulation about {orchestrator.scenario.get('title', '...')}.

Available personas: {', '.join([p['id'] for p in orchestrator.scenario.get('personas', [])])}

CRITICAL MEMORY INSTRUCTIONS:
- You have access to the COMPLETE conversation history from THIS SCENE ONLY
- You MUST remember and reference information shared in previous interactions within this scene
- If the user tells you something personal (like their birthday), you MUST remember it for this scene
- When asked about something you previously discussed in this scene, provide the specific information
- DO NOT reference information from other scenes - only use information from the current scene

{memory_context}

Gently redirect them to use a valid persona mention or provide general guidance."""
                    persona_name = "ChatOrchestrator"
                    persona_id = None
            else:
                # General orchestrator response
                system_prompt = f"""You are the ChatOrchestrator for a strategic business simulation about {orchestrator.scenario.get('title', '...')}.

CURRENT SCENE: {orchestrator.scenario.get('scenes', [{}])[orchestrator.state.current_scene_index].get('title', '...')}
OBJECTIVE: {orchestrator.scenario.get('scenes', [{}])[orchestrator.state.current_scene_index].get('objectives', ['...'])[0]}

BUSINESS SIMULATION GUIDANCE:
The user can:
- Use @mentions to talk to specific team members (e.g., {', '.join([p['id'] for p in orchestrator.scenario.get('personas', [])])})
- Ask strategic questions about the business situation
- Request guidance on business analysis approaches
- Seek help with developing solutions and recommendations

Your role is to:
- Guide users toward strategic thinking and business analysis
- Encourage consideration of multiple stakeholders and perspectives
- Help develop practical, implementable business solutions
- Foster critical analysis and questioning of assumptions
- Promote professional communication and presentation skills

CRITICAL MEMORY INSTRUCTIONS:
- You have access to the COMPLETE conversation history from THIS SCENE ONLY
- You MUST remember and reference information shared in previous interactions within this scene
- If the user tells you something personal (like their birthday), you MUST remember it for this scene
- When asked about something you previously discussed in this scene, provide the specific information
- DO NOT reference information from other scenes - only use information from the current scene

{memory_context}

This is about {orchestrator.scenario.get('title', '...')} and its strategic business challenges, NOT about any other company or system.

Respond helpfully and guide them toward productive business interactions with the team members. Focus on developing their strategic thinking and business acumen. You have access to the full conversation history, so you can reference previous interactions.

User's message: {request.message}"""
                persona_name = "ChatOrchestrator"
                persona_id = None
            
            # Make OpenAI API call
            try:
                client = _get_openai_client()
            except HTTPException as e:
                print(f"[ERROR] Failed to initialize OpenAI client: {e}")
                raise e
            
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt}
                ] + conversation_context,
                max_tokens=600,
                temperature=0.7
            )
            
            ai_response = response.choices[0].message.content
        
        # Check for goal completion and scene progression using AI function calling
        scene_completed = False
        next_scene_id = None
        
        # Only check goal completion if simulation is started and not a system command
        if (orchestrator.state.simulation_started and 
            request.message.lower().strip() not in ["begin", "help"]):
            
            # Get current scene goal
            current_scene = orchestrator.scenes[orchestrator.state.current_scene_index] if orchestrator.scenes else None
            if current_scene and current_scene.get('objectives'):
                scene_goal = current_scene['objectives'][0]
                scene_description = current_scene.get('description', '')
                
                # Get current attempts
                scene_progress = db.query(SceneProgress).filter(
                    and_(
                        SceneProgress.user_progress_id == user_progress.id,
                        SceneProgress.scene_id == scene_id_to_use
                    )
                ).first()
                
                current_attempts = scene_progress.attempts if scene_progress else 0
                max_attempts = current_scene.get('max_attempts', 5)
                print(f"[DEBUG] Current attempts: {current_attempts}/{max_attempts}")
                
                # Only run validation if timeout is not reached (timeout is now checked earlier)
                try:
                    validation_result = validate_goal_with_function_calling(
                        conversation_history=conversation_text,
                        scene_goal=scene_goal,
                        scene_description=scene_description,
                        current_attempts=current_attempts,
                        max_attempts=max_attempts,
                        db=db,
                        user_progress_id=user_progress.id,
                        current_scene_id=scene_id_to_use,
                        perform_db_progression=False
                    )
                    
                    print(f"[DEBUG] Goal validation result: {validation_result}")
                except Exception as e:
                    print(f"[ERROR] Goal validation failed: {str(e)}")
                    # Fallback to simple validation
                    validation_result = {
                        "goal_achieved": False,
                        "confidence_score": 0.0,
                        "reasoning": f"Error during validation: {str(e)}",
                        "next_action": "continue",
                        "hint_message": None,
                        "next_scene_id": None,
                        "next_scene_title": None,
                        "simulation_complete": False
                    }
                    
                    # Handle the validation result
                    print(f"[DEBUG] ABOUT TO RUN GOAL VALIDATION: turn_count={orchestrator.state.turn_count}, timeout_turns={timeout_turns}")
                
                if validation_result.get("next_scene_id") or validation_result.get("simulation_complete"):
                    # Only allow progression if turn limit is reached
                    if orchestrator.state.turn_count < timeout_turns:
                        print(f"[DEBUG] LLM wants to progress, but turn limit not reached: turn_count={orchestrator.state.turn_count}, timeout_turns={timeout_turns}")
                        # Optionally, inform the user they need more turns
                        # Do NOT progress the scene, just continue
                    else:
                        # Scene progression was triggered by the AI function call
                        scene_completed = True
                        next_scene_id = validation_result.get("next_scene_id")
                        # Don't append completion messages to ai_response - let the persona respond first
                        # The completion message will be handled by the frontend after the persona response
                        # Update orchestrator state to match database
                        if next_scene_id:
                            # Find the scene index for the new scene
                            next_scene_obj = None
                            for i, scene in enumerate(orchestrator.scenes):
                                if scene.get('id') == next_scene_id:
                                    orchestrator.state.current_scene_index = i
                                    next_scene_obj = scene
                                    break
                            orchestrator.state.turn_count = 0
                            print(f"[DEBUG] TURN COUNT RESET TO 0 ON GOAL VALIDATION PROGRESSION")
                            orchestrator.state.scene_completed = False
                            orchestrator.state.current_scene_id = next_scene_id
                            print(f"[DEBUG] NEW SCENE START (after goal validation progression): index={orchestrator.state.current_scene_index}, turn_count={orchestrator.state.turn_count}")
                            
                            # CRITICAL: Update UserProgress.current_scene_id to match the orchestrator state
                            user_progress.current_scene_id = next_scene_id
                            print(f"[DEBUG] Updated UserProgress.current_scene_id to {next_scene_id} (goal validation)")
                            
                            # Mark current scene as completed
                            scene_id_to_use = request.scene_id if request.scene_id is not None else user_progress.current_scene_id
                            completed_scenes = user_progress.scenes_completed or []
                            if scene_id_to_use and scene_id_to_use not in completed_scenes:
                                completed_scenes.append(scene_id_to_use)
                                user_progress.scenes_completed = completed_scenes
                                print(f"[DEBUG] Added scene {scene_id_to_use} to completed scenes (goal validation): {completed_scenes}")
                            
                            # Update SceneProgress
                            current_scene_progress = db.query(SceneProgress).filter(
                                and_(
                                    SceneProgress.user_progress_id == user_progress.id,
                                    SceneProgress.scene_id == scene_id_to_use
                                )
                            ).first()
                            
                            if current_scene_progress:
                                current_scene_progress.status = "completed"
                                current_scene_progress.goal_achieved = True
                                current_scene_progress.completed_at = datetime.utcnow()
                                print(f"[DEBUG] Marked SceneProgress {scene_id_to_use} as completed (goal validation)")
                            
                            # Create SceneProgress for new scene
                            new_scene_progress = db.query(SceneProgress).filter(
                                and_(
                                    SceneProgress.user_progress_id == user_progress.id,
                                    SceneProgress.scene_id == next_scene_id
                                )
                            ).first()
                            
                            if not new_scene_progress:
                                new_scene_progress = SceneProgress(
                                    user_progress_id=user_progress.id,
                                    scene_id=next_scene_id,
                                    status="in_progress",
                                    started_at=datetime.utcnow()
                                )
                                db.add(new_scene_progress)
                                print(f"[DEBUG] Created SceneProgress for new scene {next_scene_id} (goal validation)")
                            else:
                                new_scene_progress.status = "in_progress"
                                print(f"[DEBUG] Reactivated SceneProgress for scene {next_scene_id} (goal validation)")
                            
                            # Save scene introduction message to database for the new scene
                            if next_scene_obj:
                                next_scene_from_db = db.query(ScenarioScene).filter(
                                    ScenarioScene.id == next_scene_id
                                ).first()
                                
                                if next_scene_from_db:
                                    # Check if scene intro already exists for this scene
                                    existing_intro = db.query(ConversationLog).filter(
                                        ConversationLog.user_progress_id == user_progress.id,
                                        ConversationLog.scene_id == next_scene_id,
                                        ConversationLog.message_type == "system",
                                        ConversationLog.sender_name == "System"
                                    ).first()
                                    
                                    if not existing_intro:
                                        # Get the next message order
                                        last_msg = db.query(ConversationLog).filter(
                                            ConversationLog.user_progress_id == user_progress.id
                                        ).order_by(desc(ConversationLog.message_order)).first()
                                        next_order = (last_msg.message_order + 1) if last_msg else 1
                                        
                                        scene_intro_text = generate_scene_intro_message(next_scene_obj, next_scene_from_db, db)
                                        scene_intro_log = ConversationLog(
                                            user_progress_id=user_progress.id,
                                            scene_id=next_scene_id,
                                            message_type="system",
                                            sender_name="System",
                                            persona_id=None,
                                            message_content=scene_intro_text,
                                            message_order=next_order,
                                            timestamp=datetime.utcnow()
                                        )
                                        db.add(scene_intro_log)
                                        # Don't commit here - will be committed at the end of the function
                                        db.flush()
                                        scene_intro_message = scene_intro_text  # Set for response
                                        print(f"[DEBUG] Saved scene introduction message to database after goal validation for scene {next_scene_id} with order {next_order}")
                                    else:
                                        print(f"[DEBUG] Scene intro already exists for scene {next_scene_id} (goal validation), skipping")
                
                elif validation_result["next_action"] == "hint" and validation_result["hint_message"]:
                    # Add hint to response
                    ai_response += f"\n\n💡 **Hint:** {validation_result['hint_message']}"
                
                elif validation_result["next_action"] == "force_progress":
                    # Force progression due to max attempts - handled by the function call now
                    pass
        
        # Update orchestrator state in database
        user_progress.last_activity = datetime.utcnow()
        
        # Update StudentSimulationInstance completion percentage and time spent based on progress
        from database.models import StudentSimulationInstance
        simulation_instance = db.query(StudentSimulationInstance).filter(
            StudentSimulationInstance.user_progress_id == user_progress.id
        ).first()
        
        if simulation_instance:
            total_scenes = len(orchestrator.scenes)
            completed_scenes = db.query(SceneProgress).filter(
                SceneProgress.user_progress_id == user_progress.id,
                SceneProgress.status == "completed"
            ).count()
            
            if total_scenes > 0:
                completion_percentage = (completed_scenes / total_scenes) * 100
                simulation_instance.completion_percentage = completion_percentage
                print(f"[DEBUG] Updated completion: {completed_scenes}/{total_scenes} scenes = {completion_percentage}%")
            
            # Update total time spent (prefer started_at -> completed_at; fallback to progress activity)
            try:
                from datetime import datetime as dt, timezone as tz
                start_dt = simulation_instance.started_at or user_progress.created_at
                end_dt = simulation_instance.completed_at or user_progress.last_activity or user_progress.updated_at or dt.now(tz.utc)

                if start_dt:
                    if start_dt.tzinfo is None:
                        start_dt = start_dt.replace(tzinfo=tz.utc)
                    if end_dt and end_dt.tzinfo is None:
                        end_dt = end_dt.replace(tzinfo=tz.utc)
                    if end_dt:
                        time_delta = end_dt - start_dt
                        simulation_instance.total_time_spent = max(0, int(time_delta.total_seconds()))
                        print(f"[DEBUG] Updated time spent: {simulation_instance.total_time_spent} seconds ({simulation_instance.total_time_spent // 60} minutes)")
            except Exception as e:
                print(f"[WARNING] Could not calculate time spent: {e}")
        
        # Save updated orchestrator state - ALWAYS save the state
        state_dict = {
            'current_scene_id': orchestrator.state.current_scene_id,
            'current_scene_index': orchestrator.state.current_scene_index,
            'turn_count': orchestrator.state.turn_count,
            'simulation_started': orchestrator.state.simulation_started,
            'user_ready': orchestrator.state.user_ready,
            'state_variables': orchestrator.state.state_variables
        }
        
        # Ensure orchestrator_data exists and update state
        if not user_progress.orchestrator_data:
            user_progress.orchestrator_data = {}
        
        # Always update the state - Force SQLAlchemy to detect JSON change
        user_progress.orchestrator_data['state'] = state_dict
        # Mark the JSON field as modified so SQLAlchemy will update it
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(user_progress, "orchestrator_data")
        print(f"[DEBUG] Saving state at end - simulation_started: {state_dict['simulation_started']}")
        
        # Log conversation with persona information
        # Get the next message order
        last_msg = db.query(ConversationLog).filter(
            ConversationLog.user_progress_id == user_progress.id
        ).order_by(desc(ConversationLog.message_order)).first()
        next_order = (last_msg.message_order + 1) if last_msg else 1
        
        conversation_log = ConversationLog(
            user_progress_id=user_progress.id,
            scene_id=request.scene_id or user_progress.current_scene_id,
            message_type="ai_persona" if persona_name != "ChatOrchestrator" else "orchestrator",
            sender_name=persona_name,
            persona_id=persona_id,  # This will be None for orchestrator messages
            message_content=ai_response,  # Store only the AI response content
            message_order=next_order,
            timestamp=datetime.utcnow()
        )
        db.add(conversation_log)
        db.flush()
        print(f"[DEBUG] Logged AI response with order {next_order}")
        
        # If this was a "begin" command AND we just started (not already running), save the scene introduction AFTER the prologue
        # We check the message, not the state, because state was just set above
        if request.message.lower().strip() == "begin":
            current_scene_obj = orchestrator.scenario.get('scenes', [{}])[orchestrator.state.current_scene_index]
            current_scene_from_db = db.query(ScenarioScene).filter(
                ScenarioScene.id == current_scene_obj.get('id')
            ).first()
            
            if current_scene_from_db:
                # Check if scene intro already exists for this scene
                existing_intro = db.query(ConversationLog).filter(
                    ConversationLog.user_progress_id == user_progress.id,
                    ConversationLog.scene_id == current_scene_from_db.id,
                    ConversationLog.message_type == "system",
                    ConversationLog.sender_name == "System"
                ).first()
                
                if not existing_intro:
                    # Get the next message order (after the prologue)
                    last_msg_after_prologue = db.query(ConversationLog).filter(
                        ConversationLog.user_progress_id == user_progress.id
                    ).order_by(desc(ConversationLog.message_order)).first()
                    scene_intro_order = (last_msg_after_prologue.message_order + 1) if last_msg_after_prologue else 1
                    
                    scene_intro_text = generate_scene_intro_message(current_scene_obj, current_scene_from_db, db)
                    scene_intro_log = ConversationLog(
                        user_progress_id=user_progress.id,
                        scene_id=current_scene_from_db.id,
                        message_type="system",
                        sender_name="System",
                        persona_id=None,
                        message_content=scene_intro_text,
                        message_order=scene_intro_order,
                        timestamp=datetime.utcnow()
                    )
                    db.add(scene_intro_log)
                    db.flush()
                    scene_intro_message = scene_intro_text  # Set for response
                    print(f"[DEBUG] Saved scene introduction message to database AFTER prologue for scene {current_scene_from_db.id} with order {scene_intro_order}")
                else:
                    print(f"[DEBUG] Scene intro already exists for scene {current_scene_from_db.id}, skipping")
        
        # Commit everything including the state update
        db.commit()
        print(f"[DEBUG] Final commit - simulation_started: {state_dict['simulation_started']}")
        
        # When returning SimulationChatResponse, always ensure scene_id is an int
        scene_id = orchestrator.state.current_scene_id
        if not isinstance(scene_id, int):
            scene_id = user_progress.current_scene_id if hasattr(user_progress, 'current_scene_id') and isinstance(user_progress.current_scene_id, int) else None
        
        print(f"[DEBUG] Returning response - scene_completed: {scene_completed}, next_scene_id: {next_scene_id}, scene_intro_message: {scene_intro_message is not None}")
        if scene_intro_message:
            print(f"[DEBUG] Scene intro message (first 100 chars): {scene_intro_message[:100]}")
        
        return SimulationChatResponse(
            message=ai_response,
            scene_id=_safe_scene_id(),
            scene_completed=scene_completed,
            next_scene_id=next_scene_id,
            persona_name=persona_name,
            persona_id=str(persona_id) if persona_id is not None else None,  # Convert to str at API boundary
            turn_count=orchestrator.state.turn_count,
            scene_intro_message=scene_intro_message  # Include scene intro if a new scene started
        )
        
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Linear simulation chat error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}") 

@router.post("/linear-chat-stream")
async def linear_simulation_chat_stream(
    request: SimulationChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Handle orchestrated chat interactions with streaming responses"""
    
    async def generate_stream(db_session: Session):
        """Generator function for streaming OpenAI responses"""
        # Import ChatOrchestrator at the top of the function
        from api.chat_orchestrator import ChatOrchestrator
        
        # logging removed
        scene_completed = False
        next_scene_id = None
        timeout_turns = 15
        scene_intro_message = None
        full_response = ""
        
        try:
            # Get user progress
            if not request.user_progress_id:
                yield f"data: {json.dumps({'error': 'user_progress_id is required'})}\n\n"
                return
            
            user_progress = db_session.query(UserProgress).filter(
                UserProgress.id == request.user_progress_id
            ).first()
            
            if not user_progress:
                yield f"data: {json.dumps({'error': 'User progress not found'})}\n\n"
                return
            
            # Verify ownership
            if user_progress.user_id != current_user.id:
                yield f"data: {json.dumps({'error': 'Access denied'})}\n\n"
                return
            
            if not user_progress.orchestrator_data:
                yield f"data: {json.dumps({'error': 'Simulation not properly initialized'})}\n\n"
                return
            
            # Initialize orchestrator with LangChain enabled
            # Check if this is a professor test simulation
            is_professor_test = current_user.role in ['professor', 'admin']
            orchestrator = ChatOrchestrator(user_progress.orchestrator_data, enable_langchain=True, is_professor_test=is_professor_test)
            orchestrator.user_progress_id = user_progress.id
            
            # Initialize LangChain session if not already done
            if orchestrator.langchain_enabled and not orchestrator.state.scene_memory_initialized:
                await orchestrator.initialize_langchain_session(user_progress.id)
            
            # Load saved state
            if user_progress.orchestrator_data and 'state' in user_progress.orchestrator_data:
                saved_state = user_progress.orchestrator_data['state']
                orchestrator.state.simulation_started = saved_state.get('simulation_started', False)
                orchestrator.state.user_ready = saved_state.get('user_ready', False)
                orchestrator.state.current_scene_index = saved_state.get('current_scene_index', 0)
                orchestrator.state.turn_count = saved_state.get('turn_count', 0)
                orchestrator.state.state_variables = saved_state.get('state_variables', {})
            
            # Professor test simulations will only clear conversation history on scene transitions
            # This preserves context within the same test session until the user moves to a new scene
            if current_user.role in ['professor', 'admin'] and user_progress.user_id == current_user.id and orchestrator.langchain_enabled:
                print("Professor test simulation detected - conversation history will be cleared on scene transitions only")
            
            # Check if this is a new scene (scene transition) and clear conversation history
            # This ensures each scene starts with fresh conversation context
            if orchestrator.langchain_enabled:
                # Initialize _last_scene_id if not set
                if not hasattr(orchestrator, '_last_scene_id'):
                    orchestrator._last_scene_id = None
                
                # Initialize current_scene_id from user progress if not set
                print(f"[DEBUG] Before initialization - orchestrator.state.current_scene_id: {getattr(orchestrator.state, 'current_scene_id', 'NOT_SET')}")
                print(f"[DEBUG] user_progress.current_scene_id: {user_progress.current_scene_id}")
                if not hasattr(orchestrator.state, 'current_scene_id') or orchestrator.state.current_scene_id is None or orchestrator.state.current_scene_id == "":
                    orchestrator.state.current_scene_id = user_progress.current_scene_id
                    print(f"[DEBUG] Initialized orchestrator.state.current_scene_id from user_progress: {orchestrator.state.current_scene_id}")
                else:
                    print(f"[DEBUG] orchestrator.state.current_scene_id already set to: {orchestrator.state.current_scene_id}")
                
                # Check if we're in a different scene than before
                current_scene_id = orchestrator.state.current_scene_id
                print(f"[DEBUG] Scene transition check - _last_scene_id: {orchestrator._last_scene_id}, current_scene_id: {current_scene_id}")
                
                # Clear conversation history on scene transitions
                if orchestrator._last_scene_id is not None and orchestrator._last_scene_id != current_scene_id:
                    print(f"Scene transition detected: {orchestrator._last_scene_id} -> {current_scene_id}")
                    print("Scene transition detected - clearing conversation history for new scene")
                    
                    # Clear conversation history for all existing persona agents
                    if hasattr(orchestrator, 'persona_agents') and orchestrator.persona_agents:
                        print(f"[DEBUG] Found {len(orchestrator.persona_agents)} existing persona agents to clear")
                        for persona_id, agent in orchestrator.persona_agents.items():
                            print(f"[DEBUG] Clearing conversation history for existing agent: {persona_id}")
                            agent.clear_conversation_history(user_progress.id)
                            print(f"Cleared conversation history for existing persona agent: {persona_id}")
                elif orchestrator._last_scene_id is None:
                    print(f"[DEBUG] First time setting _last_scene_id to: {current_scene_id}")
                
                # Store current scene ID for next comparison
                orchestrator._last_scene_id = current_scene_id
            
            current_scene = orchestrator.scenario.get('scenes', [{}])[orchestrator.state.current_scene_index]
            timeout_turns = current_scene.get('timeout_turns') or current_scene.get('max_turns', 15)
            correct_scene_id = current_scene.get('id')
            
            # Handle "begin" command
            if request.message.lower().strip() == "begin":
                # Check if simulation is already started - if so, ignore the begin command
                if orchestrator.state.simulation_started:
                    print(f"[STREAM DEBUG] Simulation already started, ignoring 'begin' command")
                    # Return a message saying simulation is already running
                    already_started_msg = "The simulation is already in progress. You can continue interacting with the personas."
                    for char in already_started_msg:
                        yield f"data: {json.dumps({'content': char, 'done': False})}\n\n"
                        await asyncio.sleep(0.03)
                    yield f"data: {json.dumps({'done': True, 'persona_name': 'ChatOrchestrator', 'persona_id': None, 'scene_completed': False, 'next_scene_id': None, 'turn_count': orchestrator.state.turn_count, 'full_content': already_started_msg})}\n\n"
                    return
                
                last_msg = db_session.query(ConversationLog).filter(
                    ConversationLog.user_progress_id == user_progress.id
                ).order_by(desc(ConversationLog.message_order)).first()
                begin_order = (last_msg.message_order + 1) if last_msg else 1
                
                begin_user_log = ConversationLog(
                    user_progress_id=user_progress.id,
                    scene_id=user_progress.current_scene_id,
                    message_type="user",
                    sender_name="User",
                    message_content=request.message,
                    message_order=begin_order,
                    timestamp=datetime.utcnow()
                )
                db_session.add(begin_user_log)
                db_session.flush()
                
                orchestrator.state.simulation_started = True
                orchestrator.state.user_ready = True
                user_progress.simulation_status = "in_progress"
                
                # Save orchestrator state
                state_dict = {
                    'current_scene_id': orchestrator.state.current_scene_id,
                    'current_scene_index': orchestrator.state.current_scene_index,
                    'turn_count': orchestrator.state.turn_count,
                    'simulation_started': orchestrator.state.simulation_started,
                    'user_ready': orchestrator.state.user_ready,
                    'state_variables': orchestrator.state.state_variables
                }
                
                if not user_progress.orchestrator_data:
                    user_progress.orchestrator_data = {}
                
                user_progress.orchestrator_data['state'] = state_dict
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(user_progress, "orchestrator_data")
                db_session.commit()
                print(f"[STREAM DEBUG] Saved state after begin - simulation_started: {state_dict['simulation_started']}, simulation_status: {user_progress.simulation_status}")
                
                # Generate scene intro message
                scene_intro_message = generate_scene_intro_message(current_scene)
                
                # Stream welcome message with natural typing speed
                welcome_msg = "🎬 **Simulation Started!**\n\nThe simulation has begun. You can now interact with the personas in this scene."
                for char in welcome_msg:
                    full_response += char
                    yield f"data: {json.dumps({'content': char, 'done': False})}\n\n"
                    await asyncio.sleep(0.03)  
                
                # Save the welcome message to database so it appears on resume
                welcome_log = ConversationLog(
                    user_progress_id=user_progress.id,
                    scene_id=user_progress.current_scene_id,
                    message_type="orchestrator",
                    sender_name="ChatOrchestrator",
                    message_content=welcome_msg,
                    message_order=begin_order + 1,
                    timestamp=datetime.utcnow()
                )
                db_session.add(welcome_log)
                print(f"[STREAM DEBUG] Saved welcome message: order={begin_order + 1}")
                
                # Save scene intro message to database
                scene_intro_log = ConversationLog(
                    user_progress_id=user_progress.id,
                    scene_id=user_progress.current_scene_id,
                    message_type="system",
                    sender_name="System",
                    message_content=scene_intro_message,
                    message_order=begin_order + 2,
                    timestamp=datetime.utcnow()
                )
                db_session.add(scene_intro_log)
                db_session.commit()
                print(f"[STREAM DEBUG] Saved scene intro message: order={begin_order + 2}")
                
                # Send metadata
                yield f"data: {json.dumps({'done': True, 'persona_name': 'ChatOrchestrator', 'persona_id': None, 'scene_completed': False, 'next_scene_id': None, 'turn_count': 0, 'scene_intro_message': scene_intro_message, 'full_content': full_response})}\n\n"
                return
            
            # Save user message
            next_order = 1
            last_msg = db_session.query(ConversationLog).filter(
                ConversationLog.user_progress_id == user_progress.id
            ).order_by(desc(ConversationLog.message_order)).first()
            next_order = (last_msg.message_order + 1) if last_msg else 1
            
            user_log = ConversationLog(
                user_progress_id=user_progress.id,
                scene_id=correct_scene_id,
                message_type="user",
                sender_name="User",
                message_content=request.message,
                message_order=next_order,
                timestamp=datetime.utcnow()
            )
            db_session.add(user_log)
            db_session.flush()
            print(f"[STREAM] User msg saved: order={next_order}, scene_id={correct_scene_id}")
            
            # Increment turn count
            if request.message.lower().strip() not in ["begin", "help"]:
                orchestrator.state.turn_count += 1
            
            # Get conversation history
            conversation_logs = db_session.query(ConversationLog).filter(
                ConversationLog.user_progress_id == user_progress.id
            ).order_by(ConversationLog.message_order).all()
            
            conversation_context = []
            for log in conversation_logs[-20:]:  # Last 20 messages
                if log.message_type == "user":
                    conversation_context.append({"role": "user", "content": log.message_content})
                elif log.message_type in ["ai_persona", "system", "orchestrator"]:
                    conversation_context.append({"role": "assistant", "content": log.message_content})
            
            # Determine which persona to respond using LangChain integration
            import re
            persona_name = "ChatOrchestrator"
            persona_id = None
            ai_response = ""
            
            # Memory context for any response
            memory_context = ""
            if hasattr(orchestrator, 'memory_service') and orchestrator.memory_service:
                relevant_memories = orchestrator.memory_service.retrieve_relevant_context(
                    request.message, scene_id=correct_scene_id
                )
                if relevant_memories:
                    memory_context = "\n\n**Relevant Context from Previous Interactions:**\n" + "\n".join(
                        [f"- {mem['content']}" for mem in relevant_memories[:3]]
                    )
            
            # Check for @mention in the message
            prompt_locked = False
            mention_match = re.search(r'@(\w+)', request.message.lower())
            # logging removed
            
            if mention_match:
                persona_id = mention_match.group(1)
                
                # Build name mapping for persona lookup
                name_mapping = {}
                for persona in orchestrator.scenario.get('personas', []):
                    name = persona['identity']['name'].lower()
                    # Add various name variations
                    name_mapping[name] = persona['id']
                    name_mapping[name.replace("'", "").replace(" ", "_")] = persona['id']
                    name_mapping[name.replace("'", "").replace(" ", "")] = persona['id']
                    # Add first name only
                    first_name = name.split()[0]
                    name_mapping[first_name] = persona['id']
                    name_mapping[first_name.replace("'", "")] = persona['id']
                
                # Try to find the persona by name
                search_name = persona_id.lower()
                target_persona = None
                
                if search_name in name_mapping:
                    persona_id = name_mapping[search_name]
                    target_persona = next((p for p in orchestrator.scenario.get('personas', []) if p['id'] == persona_id), None)
                else:
                    # Try fuzzy matching
                    for name, pid in name_mapping.items():
                        if (search_name in name or name in search_name or
                            search_name.replace("'", "").replace("_", "") in name.replace("'", "").replace("_", "")):
                            persona_id = pid
                            target_persona = next((p for p in orchestrator.scenario.get('personas', []) if p['id'] == persona_id), None)
                            break
                
                if target_persona:
                    # Use LangChain persona agent for response
                    if orchestrator.langchain_enabled:
                        try:
                            ai_response = await orchestrator.chat_with_persona_langchain(
                                message=request.message,
                                persona_id=persona_id,
                                scene_id=correct_scene_id
                            )
                            persona_name = target_persona['identity']['name']
                            persona_id = target_persona.get('db_id')
                        except Exception as e:
                            print(f"LangChain persona chat error: {e}")
                            # Fallback to orchestrator response
                            ai_response = f"I'm sorry, I'm having trouble processing that right now. Please try again or ask the orchestrator for help."
                            persona_name = "ChatOrchestrator"
                            persona_id = None
                    else:
                        # Fallback if LangChain not available
                        ai_response = f"I'm sorry, the persona interaction system is not available right now. Please try again later."
                        persona_name = "ChatOrchestrator"
                        persona_id = None
                else:
                    # Fallback to orchestrator with redirection
                    ai_response = f"I don't recognize that persona. Available team members: {', '.join([p['id'] for p in orchestrator.scenario.get('personas', [])])}. Please use @mentions to talk to specific team members."
                    persona_name = "ChatOrchestrator"
                    persona_id = None
            else:
                # General orchestrator response - use LangChain if available
                if orchestrator.langchain_enabled:
                    try:
                        # Use orchestrator's system prompt for general responses
                        system_prompt = orchestrator.get_system_prompt()
                        # For now, use direct OpenAI call for orchestrator responses
                        # TODO: Implement orchestrator LangChain integration
                        ai_response = "I'm here to help guide your business simulation. Use @mentions to talk to specific team members or ask me for strategic guidance."
                        persona_name = "ChatOrchestrator"
                        persona_id = None
                    except Exception as e:
                        print(f"LangChain orchestrator error: {e}")
                        ai_response = "I'm here to help guide your business simulation. Use @mentions to talk to specific team members or ask me for strategic guidance."
                        persona_name = "ChatOrchestrator"
                        persona_id = None
                else:
                    ai_response = "I'm here to help guide your business simulation. Use @mentions to talk to specific team members or ask me for strategic guidance."
                    persona_name = "ChatOrchestrator"
                    persona_id = None
            
            # Stream the LangChain response
            if ai_response:
                # Stream the response character by character for consistency with OpenAI streaming
                for char in ai_response:
                    full_response += char
                    yield f"data: {json.dumps({'content': char, 'done': False})}\n\n"
                    await asyncio.sleep(0.03)
            
            # Save AI response to database
            ai_log = ConversationLog(
                user_progress_id=user_progress.id,
                scene_id=correct_scene_id,
                message_type="ai_persona" if persona_id else "orchestrator",
                sender_name=persona_name,
                persona_id=persona_id,
                message_content=full_response,
                message_order=next_order + 1,
                timestamp=datetime.utcnow()
            )
            db_session.add(ai_log)
            db_session.flush()
            print(f"[STREAM] AI response saved: order={next_order + 1}, scene_id={correct_scene_id}")
            
            # Update state
            state_dict = {
                'current_scene_id': orchestrator.state.current_scene_id,
                'current_scene_index': orchestrator.state.current_scene_index,
                'turn_count': orchestrator.state.turn_count,
                'simulation_started': orchestrator.state.simulation_started,
                'user_ready': orchestrator.state.user_ready,
                'state_variables': orchestrator.state.state_variables
            }
            
            if not user_progress.orchestrator_data:
                user_progress.orchestrator_data = {}
            
            user_progress.orchestrator_data['state'] = state_dict
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(user_progress, "orchestrator_data")
            user_progress.last_activity = datetime.utcnow()
            
            # Commit the AI response first so it's saved
            db_session.commit()
            print(f"[STREAM DEBUG] Committed AI response to database. Turn count: {orchestrator.state.turn_count}")
            
            # --- CRITICAL: Check for timeout turns AFTER committing AI response ---
            current_scene = orchestrator.scenario.get('scenes', [{}])[orchestrator.state.current_scene_index]
            timeout_turns = current_scene.get('timeout_turns') or current_scene.get('max_turns', 15)
            print(f"[STREAM DEBUG] Turn count: {orchestrator.state.turn_count}, timeout_turns: {timeout_turns}")
            
            if orchestrator.state.turn_count >= timeout_turns:
                print(f"[STREAM DEBUG] TIMEOUT REACHED: turn_count={orchestrator.state.turn_count}, timeout_turns={timeout_turns} - USING SUBMIT FOR GRADING LOGIC")
                
                # Use the exact same logic as the manual submit for grading
                # Check if there's a next scene available
                print(f"[DEBUG] (Timeout) Current scene index: {orchestrator.state.current_scene_index}")
                print(f"[DEBUG] (Timeout) Total scenes: {len(orchestrator.scenario.get('scenes', []))}")
                
                if orchestrator.state.current_scene_index + 1 < len(orchestrator.scenario.get('scenes', [])):
                    # Move to next scene
                    next_scene_index = orchestrator.state.current_scene_index + 1
                    next_scene = orchestrator.scenario.get('scenes', [])[next_scene_index]
                    next_scene_id = next_scene.get('id')
                    print(f"[DEBUG] (Timeout) Moving to next scene: index={next_scene_index}, id={next_scene_id}, title={next_scene.get('title')}")
                    
                    # No timeout message needed - using loading screen approach
                    
                    # Update orchestrator state
                    orchestrator.state.current_scene_index = next_scene_index
                    orchestrator.state.turn_count = 0
                    print(f"[DEBUG] TURN COUNT RESET TO 0 ON TIMEOUT PROGRESSION")
                    orchestrator.state.scene_completed = False
                    orchestrator.state.current_scene_id = next_scene_id
                    
                    # Clear conversation history and restart all agents for scene transition
                    if orchestrator.langchain_enabled:
                        print(f"[DEBUG] TIMEOUT - Clearing conversation history and restarting agents for scene transition")
                        from agents.persona_agent import PersonaAgent, PersonaAgentManager
                        
                        # Clear all existing agents for this session to force restart
                        if hasattr(orchestrator, 'persona_agent_manager'):
                            orchestrator.persona_agent_manager.clear_session_agents(f"user_{user_progress.id}")
                            print(f"[DEBUG] TIMEOUT - Cleared all existing agents for session")
                        
                        # Clear the ACTUAL persona agents in the orchestrator, not temporary ones
                        if hasattr(orchestrator, 'persona_agents') and orchestrator.persona_agents:
                            print(f"[DEBUG] TIMEOUT - Found {len(orchestrator.persona_agents)} existing persona agents to clear")
                            for agent_id, persona_agent in orchestrator.persona_agents.items():
                                print(f"[DEBUG] TIMEOUT - Clearing conversation history for existing agent: {agent_id}")
                                result = persona_agent.clear_conversation_history(user_progress.id)
                                print(f"[DEBUG] TIMEOUT - clear_conversation_history result: {result}")
                                print(f"[DEBUG] TIMEOUT - Cleared conversation history for existing persona agent: {agent_id}")
                        else:
                            print(f"[DEBUG] TIMEOUT - No existing persona agents found in orchestrator - skipping clearing")
                    
                    print(f"[DEBUG] NEW SCENE START (after timeout progression): index={orchestrator.state.current_scene_index}, turn_count={orchestrator.state.turn_count}, scene_id={next_scene_id}")
                    
                    # CRITICAL: Update UserProgress.current_scene_id to match the orchestrator state
                    user_progress.current_scene_id = next_scene_id
                    print(f"[DEBUG] Updated UserProgress.current_scene_id to {next_scene_id}")
                    
                    # Clear the ACTUAL persona agents in the orchestrator, not temporary ones
                    if orchestrator.langchain_enabled:
                        print("Scene transition detected - clearing conversation history for new scene")
                        if hasattr(orchestrator, 'persona_agents') and orchestrator.persona_agents:
                            print(f"[DEBUG] Found {len(orchestrator.persona_agents)} existing persona agents to clear")
                            for agent_id, persona_agent in orchestrator.persona_agents.items():
                                print(f"[DEBUG] Clearing conversation history for existing agent: {agent_id}")
                                persona_agent.clear_conversation_history(user_progress.id)
                                print(f"Cleared conversation history for existing persona agent: {agent_id}")
                        else:
                            print(f"[DEBUG] No existing persona agents found in orchestrator - skipping clearing")
                    
                    # Mark current scene as completed in UserProgress
                    completed_scenes = user_progress.scenes_completed or []
                    if correct_scene_id and correct_scene_id not in completed_scenes:
                        completed_scenes.append(correct_scene_id)
                        user_progress.scenes_completed = completed_scenes
                        print(f"[DEBUG] Added scene {correct_scene_id} to completed scenes: {completed_scenes}")
                    
                    # Update SceneProgress for the completed scene
                    scene_progress = db_session.query(SceneProgress).filter(
                        and_(
                            SceneProgress.user_progress_id == user_progress.id,
                            SceneProgress.scene_id == correct_scene_id
                        )
                    ).first()
                    
                    if scene_progress:
                        scene_progress.status = "completed"
                        scene_progress.completed_at = datetime.utcnow()
                        print(f"[DEBUG] Marked SceneProgress {correct_scene_id} as completed")
                    
                    # Create SceneProgress for the new scene
                    new_scene_progress = db_session.query(SceneProgress).filter(
                        and_(
                            SceneProgress.user_progress_id == user_progress.id,
                            SceneProgress.scene_id == next_scene_id
                        )
                    ).first()
                    
                    if not new_scene_progress:
                        new_scene_progress = SceneProgress(
                            user_progress_id=user_progress.id,
                            scene_id=next_scene_id,
                            status="in_progress",
                            started_at=datetime.utcnow()
                        )
                        db_session.add(new_scene_progress)
                        print(f"[DEBUG] Created SceneProgress for new scene {next_scene_id}")
                    else:
                        new_scene_progress.status = "in_progress"
                        new_scene_progress.started_at = datetime.utcnow()
                        print(f"[DEBUG] Reactivated SceneProgress for scene {next_scene_id}")
                    
                    # Update timeout_turns for the new scene
                    new_scene = orchestrator.scenario.get('scenes', [{}])[next_scene_index]
                    new_timeout_turns = new_scene.get('timeout_turns') or new_scene.get('max_turns', 15)
                    print(f"[DEBUG] NEW SCENE timeout_turns: {new_timeout_turns}")
                    
                    # --- PATCH: Persist orchestrator state to DB after progression ---
                    state_dict = {
                        'current_scene_id': orchestrator.state.current_scene_id,
                        'current_scene_index': orchestrator.state.current_scene_index,
                        'turn_count': orchestrator.state.turn_count,
                        'simulation_started': orchestrator.state.simulation_started,
                        'user_ready': orchestrator.state.user_ready,
                        'state_variables': orchestrator.state.state_variables
                    }
                    user_progress.orchestrator_data['state'] = state_dict
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(user_progress, "orchestrator_data")
                    db_session.commit()
                    print(f"[DEBUG] TIMEOUT - Saved orchestrator state after progression: {state_dict}")
                    
                    # No timeout message saved - using loading screen approach
                    
                    # Send final metadata with scene completion and next scene info
                    # No timeout message - using loading screen approach
                    response_data = {'done': True, 'persona_name': persona_name, 'persona_id': str(persona_id) if persona_id else None, 'scene_completed': True, 'next_scene_id': next_scene_id, 'turn_count': 0, 'full_content': full_response}
                    print(f"[DEBUG] TIMEOUT STREAMING RESPONSE: {response_data}")
                    yield f"data: {json.dumps(response_data)}\n\n"
                    return
                else:
                    # No more scenes - simulation complete
                    user_progress.simulation_status = "completed"
                    user_progress.completed_at = datetime.utcnow()
                    
                    # No timeout message needed - using loading screen approach
                    
                    # Send final metadata with simulation completion
                    # No timeout message - using loading screen approach
                    yield f"data: {json.dumps({'done': True, 'persona_name': persona_name, 'persona_id': str(persona_id) if persona_id else None, 'scene_completed': True, 'next_scene_id': None, 'turn_count': orchestrator.state.turn_count, 'simulation_complete': True, 'full_content': full_response})}\n\n"
                    return
            else:
                # No timeout - AI response already committed above
                print(f"[STREAM DEBUG] No timeout. Turn count: {orchestrator.state.turn_count}, simulation_started: {orchestrator.state.simulation_started}")
            
            # Send final metadata
            yield f"data: {json.dumps({'done': True, 'persona_name': persona_name, 'persona_id': str(persona_id) if persona_id else None, 'scene_completed': scene_completed, 'next_scene_id': next_scene_id, 'turn_count': orchestrator.state.turn_count, 'full_content': full_response})}\n\n"
            
        except Exception as e:
            db_session.rollback()
            print(f"[ERROR] Streaming chat error: {str(e)}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(generate_stream(db), media_type="text/event-stream")

@router.get("/user-responses")
async def get_user_responses(
    user_progress_id: int = Query(...),
    scene_id: int = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Fetch all user responses (and scene metadata) for a simulation, optionally filtered by scene."""
    # First, verify that the user_progress belongs to the current user
    user_progress = db.query(UserProgress).filter(UserProgress.id == user_progress_id).first()
    if not user_progress:
        raise HTTPException(status_code=404, detail="User progress not found")
    
    if user_progress.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied: You can only access your own simulation data")
    
    # Query user messages
    filters = [ConversationLog.user_progress_id == user_progress_id]
    if scene_id:
        filters.append(ConversationLog.scene_id == scene_id)
    user_messages = db.query(ConversationLog).filter(
        *filters,
        ConversationLog.message_type == "user"
    ).order_by(ConversationLog.message_order).all()
    # Optionally, fetch all messages (for context)
    all_messages = db.query(ConversationLog).filter(*filters).order_by(ConversationLog.message_order).all()
    # Fetch scene metadata if scene_id is provided
    scene_meta = None
    if scene_id:
        scene = db.query(ScenarioScene).filter(ScenarioScene.id == scene_id).first()
        if scene:
            scene_meta = {
                "id": scene.id,
                "title": scene.title,
                "description": scene.description,
                "success_metric": getattr(scene, "success_metric", None),
                "learning_outcomes": getattr(scene, "learning_objectives", None),
                "teaching_notes": getattr(scene, "teaching_notes", None),
            }
    return {
        "user_messages": [
            {
                "id": m.id,
                "content": m.message_content,
                "timestamp": m.timestamp,
                "scene_id": m.scene_id,
                "message_order": m.message_order
            } for m in user_messages
        ],
        "all_messages": [
            {
                "id": m.id,
                "type": m.message_type,
                "sender": m.sender_name,
                "content": m.message_content,
                "timestamp": m.timestamp,
                "scene_id": m.scene_id,
                "message_order": m.message_order
            } for m in all_messages
        ],
        "scene_meta": scene_meta
    } 

@router.get("/grade")
async def get_simulation_grading(
    user_progress_id: int = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    print(f"[DEBUG] /api/simulation/grade called for user_progress_id={user_progress_id}")
    import openai
    from collections import defaultdict
    from database.models import StudentSimulationInstance
    import json
    
    # First, verify that the user_progress belongs to the current user
    user_progress = db.query(UserProgress).filter(UserProgress.id == user_progress_id).first()
    if not user_progress:
        raise HTTPException(status_code=404, detail="User progress not found")
    
    if user_progress.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied: You can only access your own simulation grades")
    
    # Check if AI grading has already been completed
    instance = db.query(StudentSimulationInstance).filter(
        StudentSimulationInstance.user_progress_id == user_progress_id
    ).first()
    
    if instance and instance.ai_grade is not None and instance.ai_graded_at is not None:
        # AI grading already completed, return existing data
        print(f"[DEBUG] AI grading already completed for instance {instance.id}, returning existing data")
        try:
            # Parse existing feedback
            ai_feedback_parsed = json.loads(instance.ai_feedback) if instance.ai_feedback else {}
            return {
                "overall_score": instance.ai_grade,
                "overall_feedback": ai_feedback_parsed.get("overall_feedback", ""),
                "scenes": ai_feedback_parsed.get("scenes", []),
                "rubric_total_points": ai_feedback_parsed.get("rubric_total_points", 100)
            }
        except (json.JSONDecodeError, TypeError):
            # If parsing fails, return basic data
            return {
                "overall_score": instance.ai_grade,
                "overall_feedback": instance.ai_feedback or "",
                "scenes": [],
                "rubric_total_points": 100
            }
    
    scenario_id = user_progress.scenario_id
    
    # Fetch scenario with rubric information
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    
    # Extract rubric information
    rubric_title = scenario.rubric_title
    rubric_criteria = scenario.rubric_criteria
    rubric_performance_levels = scenario.rubric_performance_levels
    
    # Fetch all scenes for the scenario
    scenes = db.query(ScenarioScene).filter(ScenarioScene.scenario_id == scenario_id).order_by(ScenarioScene.scene_order).all()
    # Fetch all scene progresses
    scene_progresses = db.query(SceneProgress).filter(SceneProgress.user_progress_id == user_progress_id).all()
    scene_progress_map = {sp.scene_id: sp for sp in scene_progresses}
    # Fetch all user messages (excluding "Submit for Grading" and "begin" which are UI/system commands)
    user_messages = db.query(ConversationLog).filter(
        ConversationLog.user_progress_id == user_progress_id,
        ConversationLog.message_type == "user",
        ConversationLog.message_content != "Submit for Grading"
    ).order_by(ConversationLog.scene_id, ConversationLog.message_order).all()
    # Group user messages by scene (filtering out "begin" messages)
    user_msgs_by_scene = defaultdict(list)
    for msg in user_messages:
        # Filter out "begin" messages (case-insensitive)
        msg_content_lower = (msg.message_content or "").strip().lower()
        if msg_content_lower != "begin":
            user_msgs_by_scene[msg.scene_id].append({
                "id": msg.id,
                "content": msg.message_content,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None
            })
    # Compose per-scene grading using OpenAI
    scene_feedback = []
    total_score = 0
    max_score = 0
    client = None
    try:
        client = _get_openai_client()
    except HTTPException as e:
        print(f"[ERROR] Failed to initialize OpenAI client: {e}")
        client = None
    for scene in scenes:
        sp = scene_progress_map.get(scene.id)
        user_responses = user_msgs_by_scene.get(scene.id, [])
        print(f"[DEBUG] Grading scene_id={scene.id}, title='{scene.title}'")
        print(f"[DEBUG]   success_metric: {getattr(scene, 'success_metric', None)}")
        print(f"[DEBUG]   user_responses: {user_responses}")
        print(f"[DEBUG]   full scene object: {scene}")
        
        # Use RAG-enabled grading agent instead of direct OpenAI calls
        if user_responses and scene.success_metric:
            try:
                print(f"[DEBUG] Using RAG-enabled grading agent for scene '{scene.title}'")
                
                # Prepare user responses for grading agent
                user_responses_data = [{"content": msg['content']} for msg in user_responses]
                
                # Use the grading agent with RAG capabilities
                grading_result = await grading_agent.grade_scene(
                    scene=scene,
                    user_responses=user_responses_data,
                    user_progress_id=user_progress_id,
                    rubric_criteria=rubric_criteria,
                    rubric_title=rubric_title,
                    rubric_performance_levels=rubric_performance_levels
                )
                
                score = grading_result.get("score", 0)
                feedback = grading_result.get("feedback", "No feedback provided.")
                
                print(f"[DEBUG] RAG grading completed for scene '{scene.title}': score={score}")
                
            except Exception as e:
                print(f"[ERROR] RAG grading failed for scene '{scene.title}': {e}")
                # Fallback to basic scoring
                score = getattr(sp, "goal_achievement_score", 0) or 0
                feedback = f"RAG grading failed: {e}. Goal achieved!" if getattr(sp, "goal_achieved", False) else f"RAG grading failed: {e}. Goal not achieved."
        else:
            score = getattr(sp, "goal_achievement_score", 0) or 0
            feedback = "Goal achieved!" if getattr(sp, "goal_achieved", False) else "Goal not achieved."
        # Get rubric_total_points from scenario, default to 100
        rubric_total_points = scenario.rubric_total_points if scenario else 100
        if rubric_total_points is None:
            rubric_total_points = 100
        
        # Scale scene score to rubric_total_points if it's currently out of 100
        # (assuming scene scores from grading agent are out of 100)
        if rubric_total_points != 100 and score > 0:
            scaled_score = int(round((score / 100) * rubric_total_points))
        else:
            scaled_score = int(score)
        
        max_score += rubric_total_points
        total_score += scaled_score
        teaching_notes = getattr(scene, "teaching_notes", None)
        scene_feedback.append({
            "id": scene.id,
            "title": scene.title,
            "objective": scene.user_goal,
            "user_responses": user_responses,
            "score": scaled_score,  # Use scaled score
            "feedback": feedback,
            "teaching_notes": teaching_notes
        })
    # Compose overall grading using RAG-enabled grading agent
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    learning_outcomes = scenario.learning_objectives if scenario else []
    if isinstance(learning_outcomes, str):
        learning_outcomes = [learning_outcomes]
    
    # Get rubric_total_points for overall score calculation
    rubric_total_points = scenario.rubric_total_points if scenario else 100
    if rubric_total_points is None:
        rubric_total_points = 100
    
    # Calculate overall score based on rubric_total_points
    # Scene scores are already scaled to rubric_total_points above
    scene_scores = [scene["score"] for scene in scene_feedback]
    if scene_scores and len(scene_scores) > 0:
        # Calculate average scene score (scores are already out of rubric_total_points)
        overall_score = int(round(sum(scene_scores) / len(scene_scores)))
    else:
        overall_score = 0
    
    # Use RAG-enabled grading agent for overall assessment
    overall_feedback = ""
    if scene_feedback and learning_outcomes:
        try:
            print(f"[DEBUG] Using RAG-enabled grading agent for overall assessment")
            
            # Use the grading agent for overall simulation grading
            overall_result = await grading_agent.grade_overall_simulation(
                scenario_id=scenario_id,
                scene_grades=scene_feedback,
                learning_objectives=learning_outcomes,
                user_progress_id=user_progress_id,
                rubric_total_points=rubric_total_points
            )
            
            overall_feedback = overall_result.get("feedback", "No feedback provided.")
            
            print(f"[DEBUG] RAG overall grading completed")
            
        except Exception as e:
            print(f"[ERROR] RAG overall grading failed: {e}")
            overall_feedback = f"RAG grading failed: {e}. Great job! You met most of the learning objectives." if overall_score >= 70 else f"RAG grading failed: {e}. You completed the simulation. Review the feedback for improvement."
    else:
        overall_feedback = "Great job! You met most of the learning objectives." if overall_score >= 70 else "You completed the simulation. Review the feedback for improvement."
    
    # Save AI grading results to StudentSimulationInstance if it exists
    from database.models import StudentSimulationInstance, GradeHistory
    from datetime import datetime, timezone
    import json
    
    # Find the StudentSimulationInstance associated with this user_progress
    instance = db.query(StudentSimulationInstance).filter(
        StudentSimulationInstance.user_progress_id == user_progress_id
    ).first()
    
    if instance:
        # Check if AI grading has already been done (prevent duplicate grading)
        if instance.ai_grade is not None and instance.ai_graded_at is not None:
            print(f"[DEBUG] AI grading already completed for instance {instance.id}, skipping re-grading")
        else:
            # Helper function to serialize datetime objects in nested structures
            def serialize_datetime(obj):
                """Recursively convert datetime objects to ISO format strings"""
                if isinstance(obj, datetime):
                    return obj.isoformat()
                elif isinstance(obj, dict):
                    return {k: serialize_datetime(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [serialize_datetime(item) for item in obj]
                return obj
            
            # Prepare feedback as JSON string (combining overall and scene feedback)
            # Serialize any datetime objects in scene_feedback
            serialized_scene_feedback = serialize_datetime(scene_feedback)
            feedback_data = {
                "overall_score": overall_score,
                "overall_feedback": overall_feedback,
                "scenes": serialized_scene_feedback,
                "rubric_total_points": rubric_total_points
            }
            ai_feedback_json = json.dumps(feedback_data)
            
            # Save previous status for history
            previous_status = instance.grade_status or "not_graded"
            
            # Update AI grading fields
            instance.ai_grade = float(overall_score)
            instance.ai_feedback = ai_feedback_json
            instance.ai_graded_at = datetime.now(timezone.utc)
            instance.grade_status = "ai_graded"
            
            # If no professor grade exists, set final grade to AI grade
            if instance.grade is None:
                instance.grade = float(overall_score)
                instance.feedback = ai_feedback_json
                instance.graded_at = datetime.now(timezone.utc)
            
            # Create grade history entry
            grade_history = GradeHistory(
                instance_id=instance.id,
                grade_type="ai",
                grade_value=float(overall_score),
                feedback=ai_feedback_json,
                graded_by=None,  # AI grading, no human grader
                previous_status=previous_status,
                new_status="ai_graded"
            )
            db.add(grade_history)
            
            db.commit()
            print(f"[DEBUG] Saved AI grading results to instance {instance.id}: score={overall_score}, status=ai_graded")
    
    return {
        "overall_score": overall_score,
        "overall_feedback": overall_feedback,
        "scenes": scene_feedback,
        "rubric_total_points": rubric_total_points  # Include in response for frontend
    }

@router.post("/save-message")
async def save_message(
    request: SaveMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Save a system message to conversation history
    Used for completion messages and other system notifications that need to persist
    """
    try:
        user_progress_id = request.user_progress_id
        scene_id = request.scene_id
        sender_name = request.sender_name
        message_content = request.message_content
        message_type = request.message_type
        
        # Verify that the user_progress belongs to the current user
        user_progress = db.query(UserProgress).filter(UserProgress.id == user_progress_id).first()
        if not user_progress:
            raise HTTPException(status_code=404, detail="User progress not found")
        if user_progress.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied: You can only save messages to your own simulation")

        # Get the next message order
        last_message = db.query(ConversationLog).filter(
            ConversationLog.user_progress_id == user_progress_id
        ).order_by(desc(ConversationLog.message_order)).first()
        
        next_message_order = (last_message.message_order + 1) if last_message else 1
        
        # Create the conversation log
        conversation_log = ConversationLog(
            user_progress_id=user_progress_id,
            scene_id=scene_id,
            message_type=message_type,
            sender_name=sender_name,
            message_content=message_content,
            message_order=next_message_order,
            timestamp=datetime.utcnow()
        )
        
        db.add(conversation_log)
        db.commit()
        db.refresh(conversation_log)
        
        return {
            "success": True,
            "message_id": conversation_log.id,
            "message_order": conversation_log.message_order
        }
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        debug_log(f"Error saving message: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save message: {str(e)}")