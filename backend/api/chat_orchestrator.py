#!/usr/bin/env python3
"""
Manages scene progression, agent interactions, and objective tracking
Enhanced with LangChain integration for improved AI interactions
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import json
from datetime import datetime
import asyncio

# LangChain imports (optional - will gracefully degrade if not available)
LANGCHAIN_AVAILABLE = False
langchain_manager = None
PersonaAgent = None
persona_agent_manager = None
grading_agent = None
summarization_agent = None
session_manager = None
scene_memory_manager = None

try:
    from langchain_config import langchain_manager
    from agents.persona_agent import PersonaAgent, persona_agent_manager
    from agents.grading_agent import grading_agent
    from agents.summarization_agent import summarization_agent
    from services.session_manager import session_manager
    from services.scene_memory import scene_memory_manager
    LANGCHAIN_AVAILABLE = True
except ImportError as e:
    pass

from utilities.debug_logging import debug_log

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
    
    def __init__(self, scenario_data: Dict[str, Any], enable_langchain: bool = True, is_professor_test: bool = False):
        self.scenario = scenario_data
        self.scenes = scenario_data.get('scenes', [])
        self.personas = scenario_data.get('personas', [])
        self.state = SimulationState()
        self.is_professor_test = is_professor_test  # Track if this is a professor test simulation
        
        # Build agent lookup for easy access
        self.agents = {str(agent['id']): agent for agent in self.personas}
        
        # LangChain integration (optional)
        self.langchain_enabled = enable_langchain and LANGCHAIN_AVAILABLE
        self.state.langchain_enabled = self.langchain_enabled
        
        # LangChain components (initialized when needed)
        self.persona_agents: Dict[str, PersonaAgent] = {}
        self.user_progress_id = 0
        self.vectorstore = None
        
        if self.langchain_enabled:
            # Initialize PGVector for scene context storage
            try:
                self.vectorstore = langchain_manager.vectorstore
                if self.vectorstore:
                    pass
                else:
                    pass
            except Exception as e:
                self.vectorstore = None
        else:
            pass
    
    async def initialize_langchain_session(self, user_progress_id: int) -> bool:
        """Initialize LangChain session and agents (optional enhancement)"""
        if not self.langchain_enabled:
            return False
        
        try:
            self.user_progress_id = user_progress_id
            
            # Generate session ID (synchronous method)
            self.state.session_id = session_manager.generate_session_id(
                user_progress_id, 
                self.scenario.get('id', 0), 
                self.state.current_scene_index
            )
            
            # Initialize scene memory
            current_scene = self.get_current_scene()
            if not current_scene:
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
            except Exception as e:
                debug_log(f"Error retrieving scene personas: {e}")
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
                else:
                    debug_log("Failed to initialize scene memory")
                    return False
                    
            except Exception as e:
                debug_log(f"Error initializing scene memory: {e}")
                return False
            
            # Create agent sessions with error handling
            try:
                await self._create_agent_sessions()
            except Exception as e:
                debug_log(f"Error creating agent sessions: {e}")
                # Don't fail completely if agent sessions fail, but log the error
                pass
            
            return True
            
        except Exception as e:
            debug_log(f"Critical error initializing LangChain session: {e}")
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
            debug_log(f"Error getting scene personas: {e}")
            return []
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception as close_error:
                    debug_log(f"Error closing database connection: {close_error}")
    
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
                    debug_log(f"Error expiring session during cleanup: {e}")
            
        except Exception as e:
            debug_log(f"Error during cleanup: {e}")
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
                    
                    # Create persona agent with unique session ID for each persona
                    persona_obj = await self._get_persona_from_db(persona.get('db_id'))
                    if persona_obj:
                        # Create persona-specific session ID to ensure complete isolation
                        persona_session_id = f"{session_id}_persona_{persona_obj.id}"
                        persona_agent = PersonaAgent(persona_obj, persona_session_id, self.user_progress_id)
                        # Don't clear conversation history here - it should only be cleared when a new simulation starts
                        self.persona_agents[str(agent_id)] = persona_agent
                    else:
                        print(f"Could not create persona agent for {agent_id} - persona object not found")
                        
                except Exception as e:
                    debug_log(f"Error creating agent session: {e}")
                    # Continue with other personas even if one fails
                    continue
            
        except Exception as e:
            debug_log(f"Critical error creating agent sessions: {e}")
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
            return None
        
        db = None
        try:
            from database.connection import get_db
            from database.models import ScenarioPersona
            
            db = next(get_db())
            persona = db.query(ScenarioPersona).filter(ScenarioPersona.id == persona_id).first()
            
            return persona
        except Exception as e:
            debug_log(f"Error getting persona from DB: {e}")
            return None
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception as close_error:
                    debug_log(f"Error closing database connection: {close_error}")
    
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
            
            return True
            
        except Exception as e:
            debug_log(f"Error storing scene context in PGVector: {e}")
            raise e
    
    async def chat_with_persona_langchain(self, 
                                        message: str, 
                                        persona_id: str,
                                        scene_id: int) -> str:
        """Enhanced persona chat with LangChain integration (optional)"""
        if not self.langchain_enabled:
            return "LangChain integration not available"
        
        try:
            # Get persona agent
            if str(persona_id) not in self.persona_agents:
                return "I'm sorry, I'm not available right now. Please try again."
            
            persona_agent = self.persona_agents[str(persona_id)]
            
            # Get current scene context
            current_scene = self.get_current_scene()
            
            # Store current scene context in PGVector
            if current_scene:
                await self.store_scene_context(current_scene)
            
            # Create isolated context - only include current scene, NO scenario-wide data
            # This prevents system prompts and context from other personas leaking through
            combined_context = {
                "current_scene": current_scene
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
            debug_log(f"Error in LangChain persona chat: {e}")
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
                        debug_log(f"Unable to parse previous summary JSON: {parse_err}")
            
            return intro
            
        except Exception as e:
            debug_log(f"Error generating enhanced scene introduction: {e}")
            raise e
    
    def generate_timeout_message(self, next_scene: Optional[Dict[str, Any]] = None) -> str:
        """Generate timeout message for scene progression"""
        if next_scene:
            return f"⏰ **Time's up!** You've reached the maximum turns for this scene. Moving to the next scene.\n\n**{next_scene.get('title', 'Next Scene')}**\n\n**Objective:** {next_scene.get('objectives', ['Continue the simulation'])[0]}"
        else:
            return "⏰ **Time's up!** You've reached the maximum turns for this scene. This was the final scene - simulation complete!"
    
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
            debug_log(f"Error cleaning up LangChain session: {e}")
        
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
        if not timeout_turns:
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