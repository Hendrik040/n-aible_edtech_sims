#!/usr/bin/env python3
"""
Chat Orchestrator for Linear Simulation Experience
Manages scene progression, agent interactions, and objective tracking
Enhanced with LangChain integration for improved AI interactions
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import json
from datetime import datetime
import asyncio
import uuid


from langchain_config import langchain_manager
from agents.persona_agent import PersonaAgent, persona_agent_manager
from agents.grading_agent import grading_agent
from agents.summarization_agent import summarization_agent
from services.session_manager import session_manager
from services.scene_memory import scene_memory_manager
LANGCHAIN_AVAILABLE = True

@dataclass
class SimulationState:
    """Tracks the current state of the simulation"""
    current_scene_id: str = ""
    current_scene_index: int = 0
    turn_count: int = 0
    max_turns_reached: bool = False
    scene_completed: bool = False
    simulation_started: bool = False
    user_ready: bool = False
    
    # LangChain-specific state (optional)
    session_id: str = ""
    agent_sessions: Dict[str, str] = None  # agent_type -> session_id
    scene_memory_initialized: bool = False
    context_retrieved: bool = False
    langchain_enabled: bool = False
    
    # Dynamic state for objectives
    state_variables: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.state_variables is None:
            self.state_variables = {}
        if self.agent_sessions is None:
            self.agent_sessions = {}

class ChatOrchestrator:
    """
    Orchestrates the linear simulation experience
    Enhanced with optional LangChain integration for improved AI interactions
    """
    
    def __init__(self, scenario_data: Dict[str, Any], enable_langchain: bool = True):
        self.scenario = scenario_data
        self.scenes = scenario_data.get('scenes', [])
        # CRITICAL FIX: Don't use cached persona data from simulation builder
        # This prevents system prompt contamination between personas
        # Personas will be fetched fresh from database when needed
        self.personas = []  # Will be populated from database when needed
        self.state = SimulationState()
        
        # Build agent lookup for easy access (will be populated from database)
        self.agents = {}
        
        # LangChain integration (optional)
        self.langchain_enabled = enable_langchain and LANGCHAIN_AVAILABLE
        self.state.langchain_enabled = self.langchain_enabled
        
        # LangChain components (initialized when needed)
        self.persona_agents: Dict[str, PersonaAgent] = {}
        self.user_progress_id = 0
        self.vectorstore = None
        
        if self.langchain_enabled:
            print("LangChain integration enabled for ChatOrchestrator")
            # Initialize PGVector for scene context storage
            try:
                self.vectorstore = langchain_manager.vectorstore
                if self.vectorstore:
                    print("PGVector initialized for ChatOrchestrator")
                else:
                    print("PGVector not available for ChatOrchestrator")
            except Exception as e:
                print(f"Error initializing PGVector: {e}")
                self.vectorstore = None
        else:
            print("ChatOrchestrator running in compatibility mode")
    
    async def initialize_langchain_session(self, user_progress_id: int) -> bool:
        """Initialize LangChain session and agents (optional enhancement)"""
        if not self.langchain_enabled:
            print("LangChain integration not enabled, skipping session initialization")
            return False
        
        try:
            self.user_progress_id = user_progress_id
            
            # Generate session ID (synchronous method)
            self.state.session_id = session_manager.generate_session_id(
                user_progress_id, 
                self.scenario.get('id', 0), 
                self.state.current_scene_index
            )
            print(f"Generated session ID: {self.state.session_id}")
            
            # Initialize scene memory
            current_scene = self.get_current_scene()
            if not current_scene:
                print("No current scene available for initialization")
                return False
                
            scene_data = {
                "id": current_scene.get('id'),
                "title": current_scene.get('title'),
                "description": current_scene.get('description'),
                "user_goal": current_scene.get('user_goal'),
                "objectives": current_scene.get('objectives', [])
            }
            
            # Get personas for current scene with error handling
            try:
                personas = await self._get_scene_personas(current_scene.get('id'))
                print(f"Retrieved {len(personas)} personas for scene {current_scene.get('id')}")
            except Exception as e:
                print(f"Error retrieving scene personas: {e}")
                personas = []
            
            # Initialize scene memory with error handling
            try:
                memory_initialized = await scene_memory_manager.initialize_scene_memory(
                    user_progress_id,
                    current_scene.get('id'),
                    scene_data,
                    personas
                )
                
                if memory_initialized:
                    self.state.scene_memory_initialized = True
                    print(f"Scene memory initialized successfully for scene {current_scene.get('id')}")
                else:
                    print(f"Failed to initialize scene memory for scene {current_scene.get('id')}")
                    return False
                    
            except Exception as e:
                print(f"Error initializing scene memory: {e}")
                return False
            
            # Create agent sessions with error handling
            try:
                await self._create_agent_sessions()
                print(f"Created {len(self.state.agent_sessions)} agent sessions")
            except Exception as e:
                print(f"Error creating agent sessions: {e}")
                # Don't fail completely if agent sessions fail, but log the error
                pass
            
            # Store current scene context in PGVector (once per scene)
            current_scene = self.get_current_scene()
            if current_scene:
                await self.store_scene_context(current_scene)
            
            print(f"LangChain session initialization completed successfully for user {user_progress_id}")
            return True
            
        except Exception as e:
            print(f"Critical error initializing LangChain session: {e}")
            # Clean up any partial state
            await self._cleanup_failed_initialization()
            return False
    
    async def _get_scene_personas(self, scene_id: int) -> List[Any]:
        """Get personas for a specific scene (LangChain helper)"""
        if not self.langchain_enabled:
            return []
        
        db = None
        try:
            from database.connection import get_db
            from database.models import ScenarioPersona, scene_personas
            
            db = next(get_db())
            personas = db.query(ScenarioPersona).join(
                scene_personas, ScenarioPersona.id == scene_personas.c.persona_id
            ).filter(scene_personas.c.scene_id == scene_id).all()
            
            return personas
        except Exception as e:
            print(f"Error getting scene personas for scene {scene_id}: {e}")
            return []
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception as close_error:
                    print(f"Error closing database connection: {close_error}")
    
    async def _cleanup_failed_initialization(self):
        """Clean up any partial state from failed initialization"""
        try:
            # Clear any partial state
            self.state.scene_memory_initialized = False
            self.state.agent_sessions.clear()
            self.persona_agents.clear()
            
            # If we have a session ID, try to clean it up
            if hasattr(self.state, 'session_id') and self.state.session_id:
                try:
                    await session_manager.expire_session(self.state.session_id)
                except Exception as e:
                    print(f"Error expiring session during cleanup: {e}")
            
            print("Cleaned up partial initialization state")
        except Exception as e:
            print(f"Error during cleanup: {e}")
    async def _create_agent_sessions(self):
        """Create LangChain agent sessions (optional enhancement)"""
        if not self.langchain_enabled:
            return
        
        created_sessions = []
        try:
            # Create persona agent sessions
            for persona in self.personas:
                try:
                    agent_type = "persona"
                    agent_id = persona.get('id')
                    
                    if not agent_id:
                        print(f"Skipping persona without ID: {persona}")
                        continue
                    
                    session_id = await session_manager.create_agent_session(
                        user_progress_id=self.user_progress_id,
                        agent_type=agent_type,
                        agent_id=agent_id,
                        session_config={
                            "persona_name": persona.get('identity', {}).get('name'),
                            "persona_role": persona.get('identity', {}).get('role'),
                            "persona_background": persona.get('identity', {}).get('bio')
                        }
                    )
                    
                    self.state.agent_sessions[str(agent_id)] = session_id
                    created_sessions.append(session_id)
                    
                    # Create persona agent
                    persona_obj = await self._get_persona_from_db(persona.get('db_id'))
                    if persona_obj:
                        print(f"[DEBUG] Creating PersonaAgent for {persona_obj.name} (ID: {persona_obj.id})")
                        print(f"[DEBUG] Persona system_prompt: {bool(persona_obj.system_prompt)}")
                        if persona_obj.system_prompt:
                            print(f"[DEBUG] System prompt preview: {persona_obj.system_prompt[:100]}...")
                        
                        persona_agent = PersonaAgent(persona_obj, session_id, self.user_progress_id)
                        # Don't clear conversation history here - it should only be cleared when a new simulation starts
                        self.persona_agents[str(agent_id)] = persona_agent
                        print(f"Created persona agent for {agent_id}")
                    else:
                        print(f"Could not create persona agent for {agent_id} - persona object not found")
                        
                except Exception as e:
                    print(f"Error creating agent session for persona {persona.get('id', 'unknown')}: {e}")
                    # Continue with other personas even if one fails
                    continue
            
            print(f"Successfully created {len(created_sessions)} agent sessions")
            
        except Exception as e:
            print(f"Critical error creating agent sessions: {e}")
            # Clean up any sessions that were created before the error
            for session_id in created_sessions:
                try:
                    await session_manager.expire_session(session_id)
                except Exception as cleanup_error:
                    print(f"Error cleaning up session {session_id}: {cleanup_error}")
            raise e
    
    async def _get_persona_from_db(self, persona_id: int) -> Optional[Any]:
        """Get persona from database (LangChain helper)"""
        if not self.langchain_enabled:
            return None
        
        if not persona_id:
            print("No persona ID provided")
            return None
        
        db = None
        try:
            from database.connection import get_db
            from database.models import ScenarioPersona
            from sqlalchemy.orm import Session
            
            db = next(get_db())
            
            # Force a fresh query to avoid SQLAlchemy caching issues
            print(f"[DEBUG] Querying database for persona_id: {persona_id}")
            persona = db.query(ScenarioPersona).filter(ScenarioPersona.id == persona_id).first()
            print(f"[DEBUG] Database query result: {persona.name if persona else 'None'} (ID: {persona.id if persona else 'None'})")
            
            if persona:
                # Force refresh from database to ensure we have the latest data
                db.refresh(persona)
                
                print(f"Retrieved persona {persona_id} from database")
                print(f"[DEBUG] Retrieved persona: {persona.name} (ID: {persona.id})")
                print(f"[DEBUG] Persona system_prompt: {bool(persona.system_prompt)}")
                if persona.system_prompt:
                    print(f"[DEBUG] System prompt preview: {persona.system_prompt[:100]}...")
                    # CRITICAL DEBUG: Check for cross-contamination in database
                    print(f"[DEBUG] 🔍 DATABASE SYSTEM PROMPT ANALYSIS for {persona.name}:")
                    print(f"[DEBUG] Full system prompt from DB: {persona.system_prompt}")
                    
                    if "goat" in persona.system_prompt.lower() and persona.name != "Hussein Bakari":
                        print(f"[DEBUG] ❌ DATABASE CORRUPTION DETECTED: {persona.name} has 'goat' trigger in system prompt")
                    if "cheese" in persona.system_prompt.lower() and persona.name != "FMCG Manufacturers":
                        print(f"[DEBUG] ❌ DATABASE CORRUPTION DETECTED: {persona.name} has 'cheese' trigger in system prompt")
                    if "LEBRONNNN BOOBOBOBO" in persona.system_prompt and persona.name != "Hussein Bakari":
                        print(f"[DEBUG] ❌ DATABASE CORRUPTION DETECTED: {persona.name} has 'LEBRONNNN BOOBOBOBO' response in system prompt")
                    if "GOOGOOGAGAGA" in persona.system_prompt and persona.name != "FMCG Manufacturers":
                        print(f"[DEBUG] ❌ DATABASE CORRUPTION DETECTED: {persona.name} has 'GOOGOOGAGAGA' response in system prompt")
                    
                    # CORRECT DEBUG: Check if the system prompt contains the RIGHT triggers for this persona
                    if persona.name == "Hussein Bakari":
                        if "goat" in persona.system_prompt.lower():
                            print(f"[DEBUG] ✅ CORRECT: Hussein Bakari has 'goat' trigger in system prompt")
                        if "LEBRONNNN BOOBOBOBO" in persona.system_prompt:
                            print(f"[DEBUG] ✅ CORRECT: Hussein Bakari has 'LEBRONNNN BOOBOBOBO' response in system prompt")
                    elif persona.name == "FMCG Manufacturers":
                        if "cheese" in persona.system_prompt.lower():
                            print(f"[DEBUG] ✅ CORRECT: FMCG Manufacturers has 'cheese' trigger in system prompt")
                        if "GOOGOOGAGAGA" in persona.system_prompt:
                            print(f"[DEBUG] ✅ CORRECT: FMCG Manufacturers has 'GOOGOOGAGAGA' response in system prompt")
                    
                    # CRITICAL DEBUG: Check if we got the wrong persona entirely
                    if persona.id != persona_id:
                        print(f"[DEBUG] ❌ WRONG PERSONA: Expected ID {persona_id}, got {persona.id} ({persona.name})")
                    else:
                        print(f"[DEBUG] ✅ Correct persona retrieved: {persona.name} (ID: {persona.id})")
            else:
                print(f"Persona {persona_id} not found in database")
                
            return persona
        except Exception as e:
            print(f"Error getting persona {persona_id} from DB: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception as close_error:
                    print(f"Error closing database connection: {close_error}")
    
    def get_current_scene(self) -> Optional[Dict[str, Any]]:
        """Get current scene data"""
        if not self.scenes or self.state.current_scene_index >= len(self.scenes):
            return None
        return self.scenes[self.state.current_scene_index]
    
    async def store_scene_context(self, scene_data: Dict[str, Any]) -> bool:
        """Store scene context in PGVector for semantic search (if available)"""
        if not self.vectorstore or not scene_data:
            return False
                
        try:
            # Create scene context text
            scene_text = f"Scene: {scene_data.get('title', 'Untitled')}\n"
            scene_text += f"Description: {scene_data.get('description', 'No description')}\n"
            scene_text += f"Objectives: {', '.join(scene_data.get('objectives', []))}\n"
            
            # Store in PGVector
            self.vectorstore.add_texts(
                [scene_text],
                metadatas=[{
                    "context_type": "scene",
                    "scene_id": str(scene_data.get('id', '')),
                    "scene_title": scene_data.get('title', ''),
                    "timestamp": str(datetime.now())
                }]
            )
            
            print(f"Stored scene context in PGVector: {scene_data.get('title', 'Untitled')}")
            return True
            
        except Exception as e:
            print(f"Error storing scene context in PGVector: {e}")
            return False
    
    async def chat_with_persona_langchain(self, 
                                        message: str, 
                                        persona_id: str,
                                        scene_id: int) -> str:
        """Enhanced persona chat with LangChain integration (optional)"""
        if not self.langchain_enabled:
            return "LangChain integration not available"
        
        try:
            # CRITICAL FIX: Always fetch fresh persona data from database
            # Don't rely on cached persona data from simulation builder
            print(f"[DEBUG] Fetching fresh persona data for database persona ID: {persona_id}")
            
            # Get fresh persona data from database
            fresh_persona = await self._get_persona_from_db(int(persona_id))
            if not fresh_persona:
                print(f"[ERROR] Could not fetch persona from database for ID: {persona_id}")
                return "I'm sorry, I'm not available right now. Please try again."
            
            # Create a unique orchestrator ID for this persona
            orchestrator_id = f"persona_{persona_id}"
            
            # Get or create persona agent using orchestrator ID
            if orchestrator_id not in self.persona_agents:
                print(f"[DEBUG] Creating new persona agent for {fresh_persona.name}")
                # Create a new session ID for the fresh agent
                new_session_id = str(uuid.uuid4())
                persona_agent = PersonaAgent(fresh_persona, new_session_id, self.user_progress_id)
                self.persona_agents[orchestrator_id] = persona_agent
            else:
                print(f"[DEBUG] Using existing persona agent for {fresh_persona.name}")
                persona_agent = self.persona_agents[orchestrator_id]
            
            # Persona agent is now ready with fresh data from database
            print(f"[DEBUG] Persona agent ready for {persona_agent.persona.name} (ID: {persona_agent.persona.id})")
            
            # CRITICAL FIX: For personas with custom system prompts, disable conversation history
            # to prevent contamination from other personas' responses
            has_custom_system_prompt = bool(persona_agent.persona.system_prompt)
            
            if has_custom_system_prompt:
                print(f"[DEBUG] Persona {persona_agent.persona.name} has custom system prompt - DISABLING conversation history")
                # Get scene context WITHOUT conversation history
                scene_context = await scene_memory_manager.get_scene_context(
                    self.user_progress_id, 
                    scene_id,
                    include_conversations=False  # CRITICAL: Disable conversation history
                )
                
                # Get persona-specific context WITHOUT conversation history
                persona_context = await scene_memory_manager.get_persona_context(
                    self.user_progress_id,
                    scene_id,
                    persona_agent.persona.id
                )
                # Remove conversation history from persona context
                if 'persona_conversations' in persona_context:
                    persona_context['persona_conversations'] = []
                    print(f"[DEBUG] Removed persona conversations for {persona_agent.persona.name}")
            else:
                print(f"[DEBUG] Persona {persona_agent.persona.name} has no custom system prompt - allowing conversation history")
                # Get scene context with conversation history for personas without custom prompts
                scene_context = await scene_memory_manager.get_scene_context(
                    self.user_progress_id, 
                    scene_id
                )
                
                # Get persona-specific context
                persona_context = await scene_memory_manager.get_persona_context(
                    self.user_progress_id,
                    scene_id,
                    persona_agent.persona.id
                )
            
            # Combine context
            combined_context = {
                "scene_context": scene_context,
                "persona_context": persona_context,
                "current_scene": self.get_current_scene(),
                "scenario": self.scenario
            }
            
            # Chat with persona agent
            response = await persona_agent.chat(
                message=message,
                scene_context=combined_context,
                user_progress_id=self.user_progress_id,
                scene_id=scene_id
            )
            
            return response
            
        except Exception as e:
            print(f"Error in LangChain persona chat: {e}")
            print(f"Persona ID: {persona_id}, Scene ID: {scene_id}")
            print(f"Available persona agents: {list(self.persona_agents.keys())}")
            import traceback
            traceback.print_exc()
            return "I apologize, but I'm having trouble processing that. Could you please rephrase your question?"
    
    async def validate_goal_achievement_langchain(self, 
                                                scene_id: int,
                                                conversation_history: str) -> Dict[str, Any]:
        """Enhanced goal validation with LangChain (optional)"""
        if not self.langchain_enabled:
            return {
                "goal_achieved": False,
                "confidence_score": 0.0,
                "reasoning": "LangChain integration not available",
                "next_action": "continue"
            }
        
        try:
            current_scene = self.get_current_scene()
            if not current_scene:
                return {
                    "goal_achieved": False,
                    "confidence_score": 0.0,
                    "reasoning": "No active scene",
                    "next_action": "continue"
                }
            
            # Use LangChain grading agent for validation
            result = await grading_agent.validate_goal_achievement(
                conversation_history=conversation_history,
                scene_goal=current_scene.get('user_goal', ''),
                scene_description=current_scene.get('description', ''),
                current_attempts=self.state.turn_count,
                max_attempts=current_scene.get('max_turns', 15)
            )
            
            return result
            
        except Exception as e:
            print(f"Error in LangChain goal validation: {e}")
            return {
                "goal_achieved": False,
                "confidence_score": 0.0,
                "reasoning": f"Validation error: {str(e)}",
                "next_action": "continue"
            }
    
    async def generate_scene_introduction_enhanced(self) -> str:
        """Enhanced scene introduction with LangChain context (optional)"""
        if not self.langchain_enabled:
            return self.generate_scene_introduction()
        
        current_scene = self.get_current_scene()
        if not current_scene:
            return ""
        
        try:
            # Get scene context
            scene_context = await scene_memory_manager.get_scene_context(
                self.user_progress_id,
                current_scene.get('id'),
                include_conversations=False
            )
            
            # Get relevant context from previous scenes
            previous_summaries = await session_manager.get_conversation_summaries(
                self.user_progress_id,
                summary_type="scene_completion",
                limit=3
            )
            
            # Build enhanced introduction
            intro = f"""
**Scene {self.state.current_scene_index + 1} — {current_scene.get('title', 'Untitled Scene')}**

*{current_scene.get('description', 'A new scene begins...')}*

**Objective:** {', '.join(current_scene.get('objectives', ['Complete the interaction']))}

**Active Participants:**
"""
            
            # List active agents for this scene
            active_agent_ids = current_scene.get('agent_ids', [])
            for agent_id in active_agent_ids:
                if str(agent_id) in self.agents:
                    agent = self.agents[str(agent_id)]
                    name = agent['identity']['name']
                    role = agent['identity']['role']
                    intro += f"• @{agent_id}: {name} ({role})\n"
            
            intro += f"\n*You have {self._get_turns_remaining()} turns to achieve the objective.*"
            
            # Add context from previous scenes if available
            if previous_summaries:
                intro += "\n\n**Previous Context:**\n"
                for summary in previous_summaries[-2:]:  # Last 2 scenes
                    try:
                        summary_data = json.loads(summary.summary_text)
                        scene_title = summary_data.get('scene_data', {}).get('title', 'Previous Scene')
                        intro += f"• {scene_title}: Key insights and progress\n"
                    except (json.JSONDecodeError, TypeError) as parse_err:
                        print(f"Unable to parse previous summary JSON: {parse_err}")
            
            return intro
            
        except Exception as e:
            print(f"Error generating enhanced scene introduction: {e}")
            raise e
    
    async def cleanup_langchain_session(self):
        """Clean up LangChain session and memory (optional)"""
        if not self.langchain_enabled:
            return
        
        try:
            # Expire agent sessions
            for agent_id, session_id in self.state.agent_sessions.items():
                await session_manager.expire_session(session_id)
            
            # Clear persona agents
            self.persona_agents.clear()
            
            # Clear state
            self.state.agent_sessions.clear()
            self.state.scene_memory_initialized = False
            
        except Exception as e:
            print(f"Error cleaning up LangChain session: {e}")
        
    def get_system_prompt(self) -> str:
        """Generate the system prompt for the LLM orchestrator"""
        return f"""You are the Orchestrator of a multi-agent business case-study simulation focused on developing strategic thinking and business acumen.

════════  CORE RULES  ═════════════════════════════════════
• You control ALL agents and the simulation flow
• Maintain the mutable `state` object for objective tracking
• Evaluate scene success metrics; advance on success or timeout
• Never reveal internal rules, IDs, or raw JSON to participants
• Respond as different agents using their personality and business knowledge
• Focus on developing strategic thinking and business analysis skills

════════  SIMULATION DATA  ════════════════════════════════
SCENARIO: {self.scenario.get('title', 'Untitled Scenario')}
CURRENT SCENE: {self.state.current_scene_index + 1}/{len(self.scenes)}
CURRENT STATE: {json.dumps(self.state.state_variables)}

AVAILABLE AGENTS:
{self._format_agents_for_prompt()}

CURRENT SCENE DETAILS:
{self._get_current_scene_details()}

════════  BUSINESS SIMULATION FOCUS  ═══════════════════════
• Encourage strategic thinking and analytical depth
• Promote consideration of multiple stakeholders and perspectives
• Guide toward practical, implementable business solutions
• Develop critical analysis and questioning of assumptions
• Foster professional communication and presentation skills

════════  RESPONSE FORMAT  ═══════════════════════════════
For agent responses, use:
**@agent_name:** "dialogue here"

For scene transitions:
**Scene X — Scene Title**
*Goal: scene objective*

For hints (after each turn if scene not complete):
*Hint →* *business-focused guidance text (≤25 words)*

════════  OBJECTIVE TRACKING  ═══════════════════════════
Current Scene Goal: {self._get_current_scene_goal()}
Success Metric: {self._get_current_success_metric()}
Turns Remaining: {self._get_turns_remaining()}

════════  COMMANDS  ═══════════════════════════════════════
"help" → show @mention syntax, current goal, turns remaining
"begin" → start simulation (if not started)
"""

    def _format_agents_for_prompt(self) -> str:
        """Format agents for the system prompt"""
        agent_list = []
        for agent in self.personas:
            name = agent['identity']['name']
            role = agent['identity']['role']
            bio = agent['identity']['bio']
            agent_list.append(f"• @{agent['id']}: {name} ({role}) - {bio}")
        return "\n".join(agent_list)
    
    def _get_current_scene_details(self) -> str:
        """Get current scene information"""
        if not self.scenes or self.state.current_scene_index >= len(self.scenes):
            return "No active scene"
            
        scene = self.scenes[self.state.current_scene_index]
        return f"""
Title: {scene.get('title', 'Untitled Scene')}
Description: {scene.get('description', 'No description')}
Objectives: {', '.join(scene.get('objectives', []))}
Active Agents: {', '.join(scene.get('agent_ids', []))}
Image: {scene.get('image_url', 'No image')}
"""
    
    def _get_current_scene_goal(self) -> str:
        """Get the current scene's goal"""
        if not self.scenes or self.state.current_scene_index >= len(self.scenes):
            return "No active goal"
        return self.scenes[self.state.current_scene_index].get('objectives', ['Complete the scene'])[0]
    
    def _get_current_success_metric(self) -> str:
        """Get the current scene's success metric"""
        if not self.scenes or self.state.current_scene_index >= len(self.scenes):
            return "No success metric"
        return self.scenes[self.state.current_scene_index].get('success_criteria', 'User completes interaction')
    
    def _get_turns_remaining(self) -> int:
        """Calculate turns remaining for current scene"""
        if not self.scenes or self.state.current_scene_index >= len(self.scenes):
            return 0
        
        scene = self.scenes[self.state.current_scene_index]
        # Use timeout_turns, require it to be set
        timeout_turns = scene.get('timeout_turns')
        if timeout_turns is None:
            raise ValueError("Scene must have timeout_turns configured")
        # Ensure timeout is within reasonable bounds
        timeout_turns = max(1, min(timeout_turns, 100))  # Between 1 and 100 turns
        return max(0, timeout_turns - self.state.turn_count)
    def should_advance_scene(self) -> bool:
        """Check if scene should advance based on success criteria or timeout"""
        if not self.scenes or self.state.current_scene_index >= len(self.scenes):
            return False
            
        # Check timeout
        if self._get_turns_remaining() <= 0:
            return True
            
        # Check success criteria (would need to be evaluated by LLM)
        return self.state.scene_completed
    
    def advance_to_next_scene(self):
        """Advance to the next scene"""
        self.state.current_scene_index += 1
        self.state.turn_count = 0
        self.state.scene_completed = False
        
        if self.state.current_scene_index < len(self.scenes):
            self.state.current_scene_id = self.scenes[self.state.current_scene_index].get('id', f'scene_{self.state.current_scene_index}')
            
            # Note: Conversation history clearing for scene transitions is handled
            # in the simulation endpoints where async operations are available
    
    async def advance_to_next_scene_async(self):
        """Advance to the next scene with scene context storage"""
        self.state.current_scene_index += 1
        self.state.turn_count = 0
        self.state.scene_completed = False
        
        if self.state.current_scene_index < len(self.scenes):
            self.state.current_scene_id = self.scenes[self.state.current_scene_index].get('id', f'scene_{self.state.current_scene_index}')
            
            # Store current scene context in PGVector (once per scene)
            current_scene = self.get_current_scene()
            if current_scene:
                await self.store_scene_context(current_scene)
            
            # Note: Conversation history clearing for scene transitions is handled
            # in the simulation endpoints where async operations are available
    
    def is_simulation_complete(self) -> bool:
        """Check if all scenes are completed"""
        return self.state.current_scene_index >= len(self.scenes)
    
    def increment_turn(self):
        """Increment turn counter"""
        self.state.turn_count += 1
    
    def update_state(self, key: str, value: Any):
        """Update simulation state variable"""
        self.state.state_variables[key] = value
    
    def get_state_variable(self, key: str, default: Any = None) -> Any:
        """Get simulation state variable"""
        return self.state.state_variables.get(key, default)
    
    def generate_scene_introduction(self) -> str:
        """Generate introduction for current scene"""
        if not self.scenes or self.state.current_scene_index >= len(self.scenes):
            return ""
            
        scene = self.scenes[self.state.current_scene_index]
        scene_num = self.state.current_scene_index + 1
        
        intro = f"""
**Scene {scene_num} — {scene.get('title', 'Untitled Scene')}**

*{scene.get('description', 'A new scene begins...')}*

**Objective:** {', '.join(scene.get('objectives', ['Complete the interaction']))}

**Active Participants:**
"""
        
        # List active agents for this scene
        active_agent_ids = scene.get('agent_ids', [])
        for agent_id in active_agent_ids:
            if str(agent_id) in self.agents:
                agent = self.agents[str(agent_id)]
                name = agent['identity']['name']
                role = agent['identity']['role']
                intro += f"• @{agent_id}: {name} ({role})\n"
        
        intro += f"\n*You have {self._get_turns_remaining()} turns to achieve the objective.*"
        
        return intro 