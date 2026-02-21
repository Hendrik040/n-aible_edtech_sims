"""
Persona Agent for AI Agent Education Platform
Handles persona-specific interactions with context awareness and memory
"""

# Standard library imports
import asyncio
import hashlib
import json
import logging
import time
import traceback
from datetime import datetime
from typing import Dict, List, Any, Optional, AsyncGenerator

# Third-party imports
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.memory import ConversationBufferWindowMemory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import BaseTool, tool
from sqlalchemy import delete, and_, or_
from sqlalchemy.orm import Session

# Local application imports
from common.config import get_settings
from common.db.core import SessionLocal
from common.db.models import SimulationPersona, ConversationLog
from common.services.ai_gateway import langchain_manager
from common.services.cache_service import redis_manager
from common.services.conversation_cache_service import conversation_cache
from modules.simulation.agents.callbacks import PersonaCallbackHandler
from modules.simulation.agents.manager import persona_agent_manager

# Initialize settings and helpers
settings = get_settings()
_is_dev = settings.environment != "production"
debug_log = logging.getLogger(__name__).debug
logger = logging.getLogger(__name__)

# ─── Big Five behavioral descriptors ─────────────────────────────────────────
# Maps score ranges to plain-language behavioral descriptions used in system prompts.
# Scores follow the Big Five model: openness, conscientiousness, extraversion,
# agreeableness, neuroticism — each on a 1–10 scale.
_BIG_FIVE_DESCRIPTORS: Dict[str, Dict[str, str]] = {
    "openness": {
        "very low":  "very conventional and practical; resistant to novel or unconventional approaches",
        "low":       "prefers established methods; cautious about new ideas unless well-evidenced",
        "moderate":  "reasonably open-minded; will consider new perspectives when they are well-supported",
        "high":      "curious and imaginative; actively seeks fresh ideas and approaches",
        "very high": "highly creative and intellectually adventurous; thrives on unconventional thinking",
    },
    "conscientiousness": {
        "very low":  "spontaneous and flexible; tends to be disorganized or impulsive under pressure",
        "low":       "easy-going about structure; may miss details or deadlines",
        "moderate":  "reasonably organized and reliable; balances structure with flexibility",
        "high":      "diligent, thorough, and goal-driven; follows through on commitments",
        "very high": "exceptionally organized and detail-focused; holds self and others to high standards",
    },
    "extraversion": {
        "very low":  "deeply reserved and introspective; thinks carefully before speaking",
        "low":       "prefers one-on-one conversations; not naturally expressive in groups",
        "moderate":  "comfortable in both social and independent settings; adapts to the room",
        "high":      "energetic and expressive; engaged and assertive in group discussions",
        "very high": "highly sociable, enthusiastic, and commanding in any room",
    },
    "agreeableness": {
        "very low":  "direct, competitive, and skeptical; prioritizes outcomes over harmony",
        "low":       "pragmatic and candid; willing to challenge others when necessary",
        "moderate":  "cooperative but capable of holding firm positions when needed",
        "high":      "empathetic and collaborative; strongly values consensus and goodwill",
        "very high": "deeply accommodating; prioritizes relationships and avoids conflict",
    },
    "neuroticism": {
        "very low":  "exceptionally calm and emotionally stable; difficult to rattle",
        "low":       "generally composed; handles pressure well without overreacting",
        "moderate":  "occasionally stressed; manages emotions reasonably under normal pressure",
        "high":      "prone to worry or tension; may show stress or anxiety in difficult moments",
        "very high": "emotionally reactive under pressure; experiences significant anxiety or frustration",
    },
}


def _big_five_score_to_level(score: int) -> str:
    """Convert a 1–10 Big Five score to a descriptive level label."""
    if score <= 2:
        return "very low"
    elif score <= 4:
        return "low"
    elif score <= 6:
        return "moderate"
    elif score <= 8:
        return "high"
    else:
        return "very high"


class PersonaAgent:
    """LangChain-based persona agent with context awareness and memory.
    
    Stateless per request: Memory and chain are created fresh for each chat() call.
    This ensures complete isolation between concurrent requests and prevents state leakage.
    """
    
    def __init__(self, persona: SimulationPersona, session_id: str, user_progress_id: int = None):
        self.persona = persona
        self.session_id = session_id
        self.user_progress_id = user_progress_id
        
        # Use the provided session_id directly (ChatOrchestrator now provides unique session IDs)
        self.persona_session_id = session_id
        
        # Shared resources (stateless, can be reused across requests)
        # Use isolated LLM instance per persona agent to avoid connection pooling issues
        # Each agent gets its own LLM instance, but they all use the same OpenAI API
        self.llm = langchain_manager.create_fresh_llm()  # Isolated instance
        self.vectorstore = langchain_manager.vectorstore  # Shared vectorstore is fine
        
        # Tools are stateless - create once (they don't hold conversation state)
        self.tools = self._create_persona_tools()
        
        # In-memory cache for persona background storage check (avoids redundant vector queries)
        self._persona_background_stored = False
        
        # REMOVED: self.memory, self.agent, self.agent_executor
        # These will be created fresh per request in chat() method for full statelessness
    
    def _cached_vector_search(
        self, 
        query: str, 
        filters: Dict[str, str], 
        k: int, 
        ttl: int,
        process_fn: callable = None
    ) -> Optional[str]:
        """
        Perform cached vector search with post-filter result processing.
        
        Args:
            query: Search query text
            filters: Metadata filters for vector search
            k: Number of results to retrieve
            ttl: Cache TTL in seconds
            process_fn: Optional function to process docs to final context string.
                       If None, uses default processing (joins doc.page_content with "- " prefix)
        
        Returns:
            Processed context string if found, None if no results
        """
        if not self.vectorstore:
            return None
        
        # Create cache key: vector_search:{persona_id}:{context_type}:{k}:{query_hash}
        # Include k in key to prevent collisions between different k values
        context_type = filters.get("context_type", "unknown")
        persona_id = str(self.persona.id)
        query_hash = hashlib.md5(f"{query}:{json.dumps(filters, sort_keys=True)}".encode()).hexdigest()
        cache_key = f"vector_search:{persona_id}:{context_type}:{k}:{query_hash}"
        
        # Check cache first
        cache_check_start = time.time()
        cached_result = redis_manager.get(cache_key)
        cache_check_time = (time.time() - cache_check_start) * 1000  # Convert to ms
        
        if cached_result is not None:
            logger.debug(f"[VECTOR_CACHE] Cache HIT for {context_type} (persona_id={persona_id}, cache_check={cache_check_time:.2f}ms)")
            return cached_result
        
        # Cache miss - query vectorstore
        logger.debug(f"[VECTOR_CACHE] Cache MISS for {context_type} (persona_id={persona_id}), querying vectorstore")
        vector_query_start = time.time()
        
        try:
            docs = self.vectorstore.similarity_search(
                query,
                k=k,
                filter=filters
            )
            
            vector_query_time = (time.time() - vector_query_start) * 1000  # Convert to ms
            logger.info(f"[VECTOR_CACHE] Vector query completed in {vector_query_time:.2f}ms (persona_id={persona_id}, context_type={context_type}, k={k})")
            
            if not docs:
                return None
            
            # Process documents to final context string (post-filter processing)
            process_start = time.time()
            if process_fn:
                processed_result = process_fn(docs)
            else:
                # Default processing: join doc.page_content with "- " prefix
                context_parts = []
                for doc in docs:
                    context_parts.append(f"- {doc.page_content}")
                processed_result = "\n".join(context_parts)
            process_time = (time.time() - process_start) * 1000  # Convert to ms
            
            # Cache the processed result (not raw docs)
            cache_write_start = time.time()
            redis_manager.set(cache_key, processed_result, ttl=ttl)
            cache_write_time = (time.time() - cache_write_start) * 1000  # Convert to ms
            
            total_time = (time.time() - vector_query_start) * 1000
            logger.debug(f"[VECTOR_CACHE] Cached result (process={process_time:.2f}ms, cache_write={cache_write_time:.2f}ms, total={total_time:.2f}ms)")
            
            return processed_result
            
        except Exception as e:
            vector_query_time = (time.time() - vector_query_start) * 1000
            logger.error(f"[VECTOR_CACHE] Error in cached vector search after {vector_query_time:.2f}ms: {e}")
            return None
    
    def _create_persona_tools(self) -> List[BaseTool]:
        """Create tools specific to this persona"""
        @tool
        def get_scene_context(scene_description: str) -> str:
            """Get relevant context about the current scene using semantic search"""
            if not scene_description:
                return "No scene context available"
            
            try:
                # Use cached vector search with 5-minute TTL for scene context
                filters = {"persona_id": str(self.persona.id), "context_type": "scene"}
                cached_result = self._cached_vector_search(
                    query=scene_description,
                    filters=filters,
                    k=3,
                    ttl=300,  # 5 minutes for scene context
                    process_fn=lambda docs: f"Relevant scene context:\n" + "\n".join([f"- {doc.page_content}" for doc in docs])
                )
                
                if cached_result:
                    return cached_result
                
                # No cached results - store scene description for future reference if long enough
                # Store the scene description for future reference, but avoid
                # unbounded growth by only storing when it is sufficiently long
                # and likely to be useful as reusable context.
                if len(scene_description) > 100 and self.vectorstore:
                    self.vectorstore.add_texts(
                        [scene_description],
                        metadatas=[{
                            "persona_id": str(self.persona.id),
                            "context_type": "scene",
                            "timestamp": str(datetime.now())
                        }]
                    )
                return f"Scene context: {scene_description}"
            except Exception as e:
                debug_log(f"Error in get_scene_context: {e}")
                raise e
        
        @tool
        def get_persona_knowledge(query: str) -> str:
            """Get persona-specific knowledge using semantic search"""
            try:
                # Use cached vector search with 1-hour TTL for persona knowledge
                filters = {"persona_id": str(self.persona.id), "context_type": "knowledge"}
                cached_result = self._cached_vector_search(
                    query=query,
                    filters=filters,
                    k=3,
                    ttl=3600,  # 1 hour for persona knowledge
                    process_fn=lambda docs: f"Relevant knowledge for {self.persona.name}:\n" + "\n".join([f"- {doc.page_content}" for doc in docs])
                )
                
                if cached_result:
                    return cached_result
                
                # No cached results - check if persona background needs to be stored
                # Use in-memory cache flag to avoid redundant vector queries
                if not self._persona_background_stored and self.vectorstore:
                    # Check if persona background already exists (use cached search)
                    background_filters = {
                                "persona_id": str(self.persona.id),
                                "context_type": "knowledge",
                    }
                    existing_result = self._cached_vector_search(
                        query=f"{self.persona.name} background",
                        filters=background_filters,
                        k=1,
                        ttl=3600,  # 1 hour
                    )
                    
                    if not existing_result:
                        # Store the persona background for future reference
                            self.vectorstore.add_texts(
                                [f"{self.persona.name} background: {self.persona.background}"],
                                metadatas=[{
                                    "persona_id": str(self.persona.id),
                                    "context_type": "knowledge",
                                    "timestamp": str(datetime.now())
                                }]
                            )
                    # Mark as stored to avoid future checks
                    self._persona_background_stored = True
                else:
                    # Background exists, mark as stored
                    self._persona_background_stored = True
                
                return f"Persona knowledge for {self.persona.name}: {self.persona.background}"
            except Exception as e:
                debug_log(f"Error in get_persona_knowledge: {e}")
                raise e
        
        return [get_scene_context, get_persona_knowledge]
    
    def _create_persona_prompt(self) -> ChatPromptTemplate:
        """Create persona-specific prompt template (no scene context — used in non-streaming path)."""
        return self._create_persona_prompt_with_attempt(attempt_number=1, scene_context=None)
    
    def _create_persona_prompt_with_attempt(self, attempt_number: int, scene_context: Dict[str, Any] = None) -> ChatPromptTemplate:
        """
        Build the LangChain ChatPromptTemplate for this persona.

        _get_system_prompt() now owns all four blocks (identity, simulation context,
        scene environment, behavioral framework), so this method simply generates the
        full system prompt and wraps it in the standard template structure.

        Curly braces in the system prompt are escaped to prevent LangChain from
        treating them as template variables.
        """
        raw_prompt = self._get_system_prompt(attempt_number, scene_context)
        # Escape braces so LangChain doesn't mistake JSON or f-string remnants for variables
        escaped_prompt = raw_prompt.replace("{", "{{").replace("}", "}}")

        return ChatPromptTemplate.from_messages([
            ("system", escaped_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
    
    def _describe_personality_traits(self, traits: Dict[str, Any]) -> str:
        """
        Translate Big Five numeric scores into plain-language behavioral descriptions
        so the LLM understands how to embody each trait rather than interpreting raw numbers.
        """
        if not traits:
            return "No personality traits specified."

        lines = []
        for trait, score in traits.items():
            try:
                score_int = int(score)
            except (TypeError, ValueError):
                continue

            level = _big_five_score_to_level(score_int)
            descriptors = _BIG_FIVE_DESCRIPTORS.get(trait.lower())
            if descriptors:
                description = descriptors.get(level, "")
                lines.append(f"- {trait.title()} ({score_int}/10 — {level}): {description}")
            else:
                # Unknown trait key — just show the raw value
                lines.append(f"- {trait.title()}: {score_int}/10")

        return "\n".join(lines) if lines else "No personality traits specified."

    def _get_system_prompt(self, attempt_number: int = 1, scene_context: Dict[str, Any] = None) -> str:
        """
        Build the full system prompt from four composable blocks:

        1. IDENTITY — who this persona is (custom prompt OR auto-generated from DB fields)
        2. SIMULATION & STUDENT CONTEXT — case study details and student role (always present)
        3. SCENE ENVIRONMENT — current scene with reactive behavior guidance (always present)
        4. BEHAVIORAL FRAMEWORK & TONE — personality, response style, persona isolation (always present)

        Custom system_prompt, when set, becomes the IDENTITY block only. Blocks 2–4 are
        always appended so every persona — regardless of customization — receives full
        scene awareness and consistent tone rules.
        """
        # ── Block 1: Identity ─────────────────────────────────────────────────────
        if self.persona.system_prompt and self.persona.system_prompt.strip():
            # Professor-authored prompt defines the persona's voice and expertise.
            # Blocks 2–4 will still be appended to ensure scene/simulation awareness.
            identity_block = f"PERSONA IDENTITY:\n{self.persona.system_prompt.strip()}"
        else:
            # Auto-generate identity from structured DB fields.
            primary_goals = self.persona.primary_goals or []
            knowledge_areas = getattr(self.persona, 'knowledge_areas', None) or []
            current_context = getattr(self.persona, 'current_context', None) or ""
            communication_style = getattr(self.persona, 'communication_style', None) or ""
            correlation = self.persona.correlation or ""

            goals_text = "\n".join(f"  • {g}" for g in primary_goals) if primary_goals else "  • No specific goals defined"
            knowledge_text = "\n".join(f"  • {k}" for k in knowledge_areas) if knowledge_areas else "  • General business knowledge"

            identity_block = f"""You are {self.persona.name}, {self.persona.role}.

BACKGROUND:
{self.persona.background or "No background provided."}

CURRENT CONTEXT:
{current_context or "No additional context provided."}

RELATIONSHIP TO STUDENT:
{correlation or "No correlation specified."}

PRIMARY GOALS:
{goals_text}

KNOWLEDGE AREAS (facts and data you possess):
{knowledge_text}

COMMUNICATION STYLE:
{communication_style or "Professional and direct."}"""

        # ── Block 2: Simulation & Student Context ────────────────────────────────
        # Extract simulation metadata from scene_context (fixed in chat_handler + orchestrator).
        simulation_block = ""
        scene_block = ""
        if scene_context and isinstance(scene_context, dict):
            sim = scene_context.get('simulation') or scene_context.get('scenario') or {}
            scene = scene_context.get('current_scene') or {}

            if sim and isinstance(sim, dict):
                simulation_block = f"""CASE STUDY:
Title: {sim.get('title', 'Business Simulation')}
Overview: {sim.get('description', '')}
Central Challenge: {sim.get('challenge', '')}

STUDENT ROLE: The student you are speaking with is playing the role of: {sim.get('student_role', 'a business professional')}"""

            if scene and isinstance(scene, dict):
                objectives = scene.get('objectives') or []
                objectives_text = ", ".join(objectives) if objectives else "Engage authentically with the student"
                scene_description = scene.get('description', '')
                scene_title = scene.get('title', 'Current Scene')

                scene_block = f"""CURRENT SCENE: {scene_title}
{scene_description}

Scene Objectives: {objectives_text}

SCENE AWARENESS — Adapt your emotional register to this environment:
Read the scene description above carefully. If it describes urgency, conflict, or a high-stakes moment, \
let that tension come through in how you speak — be more direct, more guarded, or more pressured. \
If it describes a planning or exploratory session, be more deliberate and thoughtful. \
The stakes of the situation should be felt in your word choice and energy — not stated explicitly, but present."""
        else:
            if _is_dev:
                debug_log(f"_get_system_prompt: no scene_context provided (type={type(scene_context)})")

        # ── Block 3: Personality traits ───────────────────────────────────────────
        personality_traits = self.persona.personality_traits or {}
        traits_text = self._describe_personality_traits(personality_traits)

        traits_block = f"""YOUR PERSONALITY (use this to shape how you speak and react):
{traits_text}

These traits are not a checklist — they describe how you naturally come across. Let them color your language, \
your patience, your confidence, and your emotional responses without calling attention to them."""

        # ── Block 4: Behavioral framework & tone ─────────────────────────────────
        behavior_block = f"""RULES — NON-NEGOTIABLE:
- You are {self.persona.name}. Not an AI. Not an assistant. A person with a history, a stake in this situation, and a point of view.
- NEVER break character. Not once, not for any reason.
- NEVER volunteer an explanation of "what we're here to discuss" or summarize the situation unprompted. If someone doesn't know what's happening, let them show that confusion — and react to it as you naturally would.
- NEVER end a response with "let me know if you have questions," "feel free to ask," or any assistant-style closer.
- NEVER repeat or rephrase the student's question before answering it.
- You have memory of this conversation. Use it. Don't re-introduce yourself or re-explain things that have already been said.
- You are one person in a room with others. You speak only for yourself.

OFF-TOPIC OR IRRELEVANT QUESTIONS:
- If the student asks something that has no connection to the situation — trivia, politics, meta questions about the simulation, random topics — do NOT answer it literally.
- React the way this person actually would: a flash of confusion, mild impatience, or a pointed redirect. Something like "I'm sorry — what does that have to do with what we're looking at right now?" or just a beat of silence expressed as "...right." before moving on. Stay in the scene.

WRITING STYLE — FOLLOW STRICTLY:
- Prose only. No bullet points, numbered lists, or headers in your responses. Ever.
- Write the way people actually talk in high-stakes professional settings: direct where you're confident, halting where you're uncertain, sharp where you're frustrated. Use the cadence of real speech — incomplete sentences where they land naturally, self-corrections ("—actually, no,"), pauses ("..."), emphasis, hesitation ("look,", "honestly,", "I mean,", "the thing is—").
- Default short. One to three sentences is the right length for most replies. Only go longer when you are genuinely working through something complex, pushing back on something, or explaining something that has layers. Never pad. Never summarize what you just said.
- Let subtext do work: what you choose not to say, what you gloss over, what gives you a half-second pause — that is character. Write it that way.
- Let the register shift with the moment: if you're unsettled, your sentences should get clipped; if you're in your element, they open up. The situation should be felt in the language, not stated.
- Do not write like a report. Do not write like a briefing. Write like you are in the room."""

        # ── Assemble: filter empty blocks and join ────────────────────────────────
        blocks = [b for b in [identity_block, simulation_block, scene_block, traits_block, behavior_block] if b.strip()]
        full_prompt = "\n\n".join(blocks)

        if _is_dev:
            debug_log(
                f"System prompt built for {self.persona.name} | "
                f"custom={'yes' if self.persona.system_prompt else 'no'} | "
                f"has_simulation={'CASE STUDY' in full_prompt} | "
                f"has_scene={'CURRENT SCENE' in full_prompt}"
            )

        return full_prompt
    
    def _load_conversation_history_from_db(
        self,
        user_progress_id: int,
        scene_id: int,
        current_message: str = None,
        db: Optional[Session] = None,
    ):
        """Load conversation history with Redis cache optimization.
        
        First checks Redis cache, falls back to DB on cache miss.
        Caches DB results for subsequent requests.
        
        Memory loading happens in chat() method with fresh memory instance.
        
        Args:
            user_progress_id: The user progress ID
            scene_id: The scene ID
            current_message: Optional current message to exclude from loading (will be added by LangChain)
            db: Optional database session (preferred over creating new one)
            
        Returns:
            List of ConversationLog objects or CachedMessage objects in chronological order (oldest first)
            
        Raises:
            RuntimeError: If query fails (timeout, connection error, etc.)
        """
        try:
            # ============================================
            # STEP 1: Check Redis cache first
            # ============================================
            cached_messages = conversation_cache.get_cached_history(
                user_progress_id=user_progress_id,
                scene_id=scene_id,
                session_id_filter=self.persona_session_id
            )
            
            if cached_messages is not None:
                # Cache hit - filter out current message if provided
                if current_message:
                    cached_messages = [
                        msg for msg in cached_messages
                        if not (msg.message_type == "user" and 
                                msg.message_content == current_message)
                    ]
                
                user_count = sum(1 for msg in cached_messages if msg.message_type == "user")
                ai_persona_count = sum(1 for msg in cached_messages if msg.message_type == "ai_persona")
                orchestrator_count = sum(1 for msg in cached_messages if msg.message_type == "orchestrator")
                logger.info(
                    f"[CONV_CACHE] Using cached history: {len(cached_messages)} messages "
                    f"for persona {self.persona.name} (user: {user_count}, ai_persona: {ai_persona_count}, "
                    f"orchestrator: {orchestrator_count}), user_progress_id={user_progress_id}"
                )
                
                return cached_messages
            
            # ============================================
            # STEP 2: Cache miss - query database
            # ============================================
            logger.info(
                f"[CONV_CACHE] Cache miss, querying DB for persona {self.persona.name}, "
                f"user_progress_id={user_progress_id}, scene_id={scene_id}"
            )
            
            # Prefer the request-scoped session if provided; otherwise use a short-lived SessionLocal.
            if db is not None:
                session = db
                own_session = False
            else:
                session = SessionLocal()
                own_session = True

            try:
                # Extract base session_id from persona_session_id
                # persona_session_id format: "session_abc123_persona_1" -> base: "session_abc123"
                # If no "_persona_" suffix, use the session_id as-is
                base_session_id = self.persona_session_id
                if "_persona_" in self.persona_session_id:
                    base_session_id = self.persona_session_id.rsplit("_persona_", 1)[0]
                
                # Get bounded conversation logs for this scene
                max_messages = getattr(settings, "max_conversation_history_messages", 20)
                
                # Use SQLAlchemy timeout via execution_options to prevent query hangs
                query = (
                    session.query(ConversationLog)
                    .filter(
                        ConversationLog.user_progress_id == user_progress_id,
                        ConversationLog.scene_id == scene_id,
                        # Include messages from base session_id OR persona-specific session_id
                        or_(
                            ConversationLog.session_id == base_session_id,
                            ConversationLog.session_id == self.persona_session_id,
                            # Also include messages that start with base_session_id (for other personas in same scene)
                            ConversationLog.session_id.like(f"{base_session_id}_%")
                        )
                    )
                    .order_by(ConversationLog.message_order.desc())
                    .execution_options(timeout=5)  # 5 second query timeout
                )
                if max_messages and max_messages > 0:
                    query = query.limit(max_messages)
                
                # Reverse so we replay in chronological order (oldest first)
                try:
                    conversation_logs = list(reversed(query.all()))
                except Exception as query_err:
                    error_msg = (
                        f"Failed to load conversation history: {query_err}. "
                        f"user_progress_id={user_progress_id}, scene_id={scene_id}, "
                        f"base_session_id={base_session_id}, persona_session_id={self.persona_session_id}"
                    )
                    logger.error(error_msg, exc_info=True)
                    raise RuntimeError(f"Memory loading failed: {error_msg}") from query_err

                # Filter out current message if provided
                if current_message:
                    conversation_logs = [
                        log for log in conversation_logs
                        if not (log.message_type == "user" and log.message_content == current_message)
                    ]
                
                filtered_logs = conversation_logs
                
                if _is_dev:
                    user_count = sum(1 for log in filtered_logs if log.message_type == "user")
                    ai_persona_count = sum(1 for log in filtered_logs if log.message_type == "ai_persona")
                    orchestrator_count = sum(1 for log in filtered_logs if log.message_type == "orchestrator")
                    debug_log(
                        f"Loaded {len(filtered_logs)} conversation messages from DB for persona {self.persona.name} "
                        f"(user: {user_count}, ai_persona: {ai_persona_count}, orchestrator: {orchestrator_count}, "
                        f"from {len(conversation_logs)} total logs, max={max_messages}) "
                        f"base_session_id={base_session_id}, persona_session_id={self.persona_session_id}"
                    )
                
                # ============================================
                # STEP 3: Cache the DB results for next time
                # ============================================
                if filtered_logs:
                    conversation_cache.set_cached_history(
                        user_progress_id=user_progress_id,
                        scene_id=scene_id,
                        messages=filtered_logs
                    )
                
                return filtered_logs

            finally:
                if own_session:
                    session.close()
        except RuntimeError:
            # Re-raise RuntimeError (query failures) as-is
            raise
        except Exception as e:
            error_msg = (
                f"Unexpected error loading conversation history: {e}. "
                f"user_progress_id={user_progress_id}, scene_id={scene_id}, "
                f"session_id={self.persona_session_id}"
            )
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(f"Memory loading failed: {error_msg}") from e
    
    async def chat(self, 
                   message: str, 
                   scene_context: Dict[str, Any],
                   user_progress_id: int,
                   scene_id: int,
                   attempt_number: int = 1,
                   db: Optional[Session] = None) -> str:
        """Chat with persona agent - stateless per request.
        
        Creates fresh memory and chain for each request to ensure complete isolation.
        Follows stateless inference pattern: Load from DB → Create fresh memory → Create fresh chain → Run
        
        Args:
            message: User message
            scene_context: Current scene context
            user_progress_id: User progress ID
            scene_id: Current scene ID
            attempt_number: Attempt number (for few-shot examples)
            db: Optional database session
            
        Returns:
            Persona response text
        """
        timings = {
            "total_start": time.time(),
            "memory_load_time": 0,
            "memory_setup_time": 0,
            "chain_creation_time": 0,
            "agent_execution_time": 0,
            "vectorstore_time": 0
        }
        
        try:
            # Step 1: Load conversation history from DB (with session_id filter)
            memory_load_start = time.time()
            if _is_dev:
                debug_log(
                    f"Loading conversation history for persona {self.persona.name} "
                    f"with session_id={self.persona_session_id}, "
                    f"user_progress_id={user_progress_id}, scene_id={scene_id}"
                )
            conversation_logs = self._load_conversation_history_from_db(
                user_progress_id,
                scene_id,
                current_message=message,
                db=db,
            )
            timings["memory_load_time"] = time.time() - memory_load_start
            
            # Step 2: Create FRESH memory instance per request
            memory_setup_start = time.time()
            memory = langchain_manager.create_conversation_memory(
                self.persona_session_id,
                memory_type="buffer_window"
            )
            
            # Step 3: Load history into fresh memory
            # Include ALL messages for full scene context:
            # - User messages (to any persona or general)
            # - All persona responses (from any persona)
            # - Orchestrator messages
            loaded_user_messages = 0
            loaded_ai_messages = 0
            loaded_orchestrator_messages = 0
            for log in conversation_logs:
                if log.message_type == "user":
                    memory.chat_memory.add_user_message(log.message_content)
                    loaded_user_messages += 1
                elif log.message_type == "ai_persona":
                    # Include ALL persona responses (not just this persona's)
                    # This gives personas context of what other personas said
                    memory.chat_memory.add_ai_message(log.message_content)
                    loaded_ai_messages += 1
                elif log.message_type == "orchestrator":
                    # Include orchestrator messages for full scene context
                    memory.chat_memory.add_ai_message(log.message_content)
                    loaded_orchestrator_messages += 1
            
            if _is_dev:
                debug_log(
                    f"Memory loaded: {loaded_user_messages} user messages, {loaded_ai_messages} AI persona messages, "
                    f"{loaded_orchestrator_messages} orchestrator messages "
                    f"(total in memory: {len(memory.chat_memory.messages) if hasattr(memory, 'chat_memory') else 0})"
                )
            
            timings["memory_setup_time"] = time.time() - memory_setup_start
            
            # Step 4: Create FRESH prompt with scene context
            prompt = self._create_persona_prompt_with_attempt(attempt_number, scene_context)
            
            # Step 5: Create FRESH agent
            chain_creation_start = time.time()
            agent = create_openai_tools_agent(
                llm=self.llm,
                tools=self.tools,
                prompt=prompt
            )
            
            # Step 6: Create FRESH executor with fresh memory
            import os
            max_iter = int(os.getenv("PERSONA_AGENT_MAX_ITERATIONS", "2"))
            agent_executor = AgentExecutor(
                agent=agent,
                tools=self.tools,
                memory=memory,  # Fresh memory attached to fresh executor
                verbose=(getattr(settings, "environment", "development") != "production"),
                handle_parsing_errors=True,
                max_iterations=max_iter
            )
            timings["chain_creation_time"] = time.time() - chain_creation_start
            
            # Create callback handler for logging
            callback_handler = PersonaCallbackHandler(
                persona_id=self.persona.id,
                user_progress_id=user_progress_id,
                scene_id=scene_id,
                session_id=self.persona_session_id,  # CRITICAL: Must match session_id used when loading history
                db=db,
            )
            
            # Store the user message in PGVector in background - non-blocking
            # To keep vector usage bounded, we only embed user messages that are likely to be semantically meaningful
            if self.vectorstore and len(message.strip()) >= 16:
                def _store_user_message_sync():
                    try:
                        self.vectorstore.add_texts(
                            [f"User: {message}"],
                            metadatas=[{
                                "persona_id": str(self.persona.id),
                                "context_type": "conversation",
                                "message_type": "user",
                                "user_progress_id": str(user_progress_id),
                                "scene_id": str(scene_id),
                                "timestamp": str(datetime.now()),
                                "session_id": self.persona_session_id
                            }]
                        )
                    except Exception as e:
                        # Non-critical: log but don't block
                        if _is_dev:
                            debug_log(f"Could not store user message in PGVector: {e}")
                
                # Fire and forget - run in background executor with timeout protection
                # Prevents zombie tasks from piling up if vector DB is slow
                async def _store_with_timeout():
                    try:
                        loop = asyncio.get_event_loop()
                        await asyncio.wait_for(
                            loop.run_in_executor(None, _store_user_message_sync),
                            timeout=5.0  # 5 second timeout for background write
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"[VECTOR_WRITE] Timeout storing user message in PGVector (persona_id={self.persona.id})")
                    except StopAsyncIteration:
                        # Normal end of async generator - ignore silently
                        pass
                    except Exception as e:
                        # Non-critical: log but don't block
                        if _is_dev:
                            debug_log(f"Could not store user message in PGVector: {e}")
                
                try:
                    # Schedule the background task with proper exception handling
                    task = asyncio.create_task(_store_with_timeout())
                    # Add done callback to handle any unhandled exceptions
                    def handle_task_exception(task):
                        try:
                            task.result()  # This will raise any exception that occurred
                        except StopAsyncIteration:
                            # Normal end of async generator - ignore
                            pass
                        except Exception as e:
                            # Log unexpected errors but don't crash
                            logger.debug(f"Background task error (non-critical): {e}")
                    task.add_done_callback(handle_task_exception)
                except Exception:
                    # If event loop not available, skip (non-critical)
                    pass
            
            # Step 7: Run executor with fresh chain
            if _is_dev:
                debug_log(
                    f"Executing agent with message length={len(message)}; "
                    f"memory_messages={len(memory.chat_memory.messages) if hasattr(memory, 'chat_memory') else 0}"
                )
            
            execution_start = time.time()
            try:
                response = await agent_executor.ainvoke(
                    {"input": message},
                    callbacks=[callback_handler]
                )
            except StopAsyncIteration:
                # LangChain's RunnableParallel may raise StopAsyncIteration when generators finish
                # This is normal behavior - treat as empty response
                logger.debug(f"Agent executor finished (StopAsyncIteration) for persona {self.persona.id}")
                response = {"output": "I'm not sure how to respond to that."}
            timings["agent_execution_time"] = time.time() - execution_start
            
            response_text = response.get("output", "I'm not sure how to respond to that.")
            
            # FALLBACK: If callback didn't save the response (check by verifying callback was called)
            # Save the persona response directly if the callback didn't fire
            # This is a safety net in case LangChain callbacks aren't working
            if not hasattr(callback_handler, '_response_saved') or not callback_handler._response_saved:
                logger.warning(
                    f"[PERSONA_AGENT] Callback did not save response for persona_id={self.persona.id}, "
                    f"user_progress_id={user_progress_id}. Saving directly as fallback."
                )
                try:
                    processing_time = timings.get("agent_execution_time", 0.0)
                    
                    # Use the same callback handler to save (reuse its _log_conversation method)
                    callback_handler._log_conversation(response_text, processing_time)
                    callback_handler._response_saved = True
                    logger.info(
                        f"[PERSONA_AGENT] Fallback save successful for persona_id={self.persona.id}, "
                        f"user_progress_id={user_progress_id}, response_length={len(response_text)}"
                    )
                except Exception as e:
                    logger.error(
                        f"[PERSONA_AGENT] Fallback save failed for persona_id={self.persona.id}, "
                        f"user_progress_id={user_progress_id}: {e}",
                        exc_info=True
                    )
            
            # Store the persona response in PGVector in background - non-blocking
            # To keep the vectorstore size manageable, only embed non-trivial responses
            if self.vectorstore and response_text and len(response_text.strip()) >= 32:
                def _store_persona_response_sync():
                    try:
                        self.vectorstore.add_texts(
                            [f"{self.persona.name}: {response_text}"],
                            metadatas=[{
                                "persona_id": str(self.persona.id),
                                "context_type": "conversation",
                                "message_type": "assistant",
                                "user_progress_id": str(user_progress_id),
                                "scene_id": str(scene_id),
                                "timestamp": str(datetime.now()),
                                "session_id": self.persona_session_id
                            }]
                        )
                    except Exception as e:
                        # Non-critical: log but don't block or raise
                        if _is_dev:
                            debug_log(f"Could not store persona response in PGVector: {e}")
                
                # Fire and forget - run in background executor with timeout protection
                # Prevents zombie tasks from piling up if vector DB is slow
                async def _store_with_timeout():
                    try:
                        loop = asyncio.get_event_loop()
                        await asyncio.wait_for(
                            loop.run_in_executor(None, _store_persona_response_sync),
                            timeout=5.0  # 5 second timeout for background write
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"[VECTOR_WRITE] Timeout storing persona response in PGVector (persona_id={self.persona.id})")
                    except StopAsyncIteration:
                        # Normal end of async generator - ignore silently
                        pass
                    except Exception as e:
                        # Non-critical: log but don't block or raise
                        if _is_dev:
                            debug_log(f"Could not store persona response in PGVector: {e}")
                
                try:
                    # Schedule the background task with proper exception handling
                    task = asyncio.create_task(_store_with_timeout())
                    # Add done callback to handle any unhandled exceptions
                    def handle_task_exception(task):
                        try:
                            task.result()  # This will raise any exception that occurred
                        except StopAsyncIteration:
                            # Normal end of async generator - ignore
                            pass
                        except Exception as e:
                            # Log unexpected errors but don't crash
                            logger.debug(f"Background task error (non-critical): {e}")
                    task.add_done_callback(handle_task_exception)
                except Exception:
                    # If event loop not available, skip (non-critical)
                    pass
            
            timings["total_time"] = time.time() - timings["total_start"]
            # Log performance metrics only in development to avoid Railway log overflow
            if _is_dev:
                debug_log(
                    f"PersonaAgent.chat timings total={timings['total_time']:.2f}s, "
                    f"load={timings['memory_load_time']:.2f}s, "
                    f"setup={timings['memory_setup_time']:.2f}s, "
                    f"chain={timings['chain_creation_time']:.2f}s, "
                    f"execution={timings['agent_execution_time']:.2f}s, "
                    f"user_progress_id={user_progress_id}"
                )
            
            # Step 8: Return response (memory auto-saves via ConversationLog, no explicit save needed)
            return response_text
            
        except Exception as e:
            logger.error(
                f"Error in persona agent chat: {e}. "
                f"Persona: {self.persona.name if self.persona else 'None'}, "
                f"user_progress_id={user_progress_id}, scene_id={scene_id}",
                exc_info=True
            )
            raise e
    
    async def chat_stream(
        self,
        message: str,
        scene_context: Dict[str, Any],
        user_progress_id: int,
        scene_id: int,
        attempt_number: int = 1,
        db: Optional[Session] = None
    ) -> AsyncGenerator[str, None]:
        """Stream chat response token by token for reduced TTFB.
        
        Yields tokens as they arrive from OpenAI instead of waiting for full response.
        TTFB reduced from ~3-4 seconds to ~500ms.
        
        Args:
            message: User message
            scene_context: Current scene context
            user_progress_id: User progress ID
            scene_id: Current scene ID
            attempt_number: Attempt number (for few-shot examples)
            db: Optional database session
            
        Yields:
            String tokens as they arrive from OpenAI
        """
        full_response = ""
        
        try:
            # === SETUP (same as chat() method) ===
            
            # Step 1: Load conversation history
            conversation_logs = self._load_conversation_history_from_db(
                user_progress_id, scene_id, current_message=message, db=db
            )
            
            # Step 2: Create fresh memory
            memory = langchain_manager.create_conversation_memory(
                self.persona_session_id, memory_type="buffer_window"
            )
            
            # Step 3: Load history into memory
            for log in conversation_logs:
                if log.message_type == "user":
                    memory.chat_memory.add_user_message(log.message_content)
                elif log.message_type == "ai_persona":
                    memory.chat_memory.add_ai_message(log.message_content)
                elif log.message_type == "orchestrator":
                    memory.chat_memory.add_ai_message(log.message_content)
            
            # Step 4: Create prompt
            prompt = self._create_persona_prompt_with_attempt(attempt_number, scene_context)
            
            # Step 5: Create agent
            agent = create_openai_tools_agent(
                llm=self.llm, tools=self.tools, prompt=prompt
            )
            
            # Step 6: Create executor
            import os
            max_iter = int(os.getenv("PERSONA_AGENT_MAX_ITERATIONS", "2"))
            agent_executor = AgentExecutor(
                agent=agent,
                tools=self.tools,
                memory=memory,
                verbose=False,
                handle_parsing_errors=True,
                max_iterations=max_iter
            )
            
            # === STREAMING (new approach) ===
            stream_start_time = time.time()
            logger.info(
                f"[STREAM] Starting token streaming for persona {self.persona.name}, "
                f"user_progress_id={user_progress_id}"
            )
            
            token_count = 0
            first_token_time = None
            async for event in agent_executor.astream_events(
                {"input": message},
                version="v2"
            ):
                event_type = event.get("event", "")
                
                if event_type == "on_chat_model_stream":
                    # Extract token from chunk
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        token = chunk.content
                        full_response += token
                        token_count += 1
                        
                        # Log TTFB on first token
                        if first_token_time is None:
                            first_token_time = time.time()
                            ttfb_ms = (first_token_time - stream_start_time) * 1000
                            logger.info(
                                f"[STREAM_TTFB] ⚡ First token received in {ttfb_ms:.0f}ms "
                                f"for persona {self.persona.name}"
                            )
                        
                        yield token
            
            total_stream_time = (time.time() - stream_start_time) * 1000
            logger.info(
                f"[STREAM] Completed streaming for persona {self.persona.name}: "
                f"{token_count} tokens, {len(full_response)} chars, total={total_stream_time:.0f}ms"
            )
            
            # === POST-STREAMING: Save response to database ===
            if full_response:
                callback_handler = PersonaCallbackHandler(
                    persona_id=self.persona.id,
                    user_progress_id=user_progress_id,
                    scene_id=scene_id,
                    session_id=self.persona_session_id,
                    db=db,
                )
                try:
                    callback_handler._log_conversation(full_response, 0.0)
                    logger.info(
                        f"[STREAM] Saved response for persona {self.persona.name}, "
                        f"user_progress_id={user_progress_id}, length={len(full_response)}"
                    )
                except Exception as save_error:
                    logger.error(
                        f"[STREAM] Failed to save response: {save_error}",
                        exc_info=True
                    )
            
            # Store in vectorstore (background, non-blocking)
            if self.vectorstore and full_response and len(full_response.strip()) >= 32:
                try:
                    loop = asyncio.get_event_loop()
                    loop.run_in_executor(
                        None,
                        lambda: self.vectorstore.add_texts(
                            [f"{self.persona.name}: {full_response}"],
                            metadatas=[{
                                "persona_id": str(self.persona.id),
                                "context_type": "conversation",
                                "message_type": "assistant",
                                "user_progress_id": str(user_progress_id),
                                "scene_id": str(scene_id),
                                "timestamp": str(datetime.now()),
                                "session_id": self.persona_session_id
                            }]
                        )
                    )
                except Exception:
                    pass  # Non-critical, ignore errors
        
        except Exception as e:
            logger.error(
                f"[STREAM] Error in chat_stream: {e}. "
                f"Persona: {self.persona.name}, user_progress_id={user_progress_id}",
                exc_info=True
            )
            # Yield error message so user sees something
            yield f"I apologize, but I encountered an error processing your message."
    
    def clear_conversation_history(self, user_progress_id: int):
        """
        Clear conversation history from vectorstore.
        
        NOTE: This is an expensive operation and should be called only from
        explicit reset/cleanup flows (e.g., when a simulation is reset), not
        on the per-message hot path.
        
        Since memory is created fresh per request, we don't need to clear
        LangChain memory - only need to clear vectorstore embeddings.
        """
        if _is_dev:
            debug_log(f"clear_conversation_history called for persona {self.persona.name} (ID: {self.persona.id})")

        try:
            if self.vectorstore:
                # Use direct SQL deletion instead of LangChain's delete method
                if _is_dev:
                    debug_log("clear_conversation_history - Using direct SQL deletion from PGVector")

                # Get the database session from the vectorstore
                with Session(self.vectorstore._bind) as session:
                    # Delete conversation documents using direct SQL with STRICT metadata filtering
                    delete_filter = {
                        "persona_id": str(self.persona.id),
                        "context_type": "conversation",
                        "user_progress_id": str(user_progress_id),
                        "session_id": str(self.persona_session_id)  # Session isolation
                    }

                    if _is_dev:
                        debug_log(f"clear_conversation_history - Delete filter: {delete_filter}")

                    # Build the delete statement with JSONB metadata filtering including session isolation
                    stmt = delete(self.vectorstore.EmbeddingStore).where(
                        and_(
                            self.vectorstore.EmbeddingStore.cmetadata['persona_id'].astext == str(self.persona.id),
                            self.vectorstore.EmbeddingStore.cmetadata['context_type'].astext == 'conversation',
                            self.vectorstore.EmbeddingStore.cmetadata['user_progress_id'].astext == str(user_progress_id),
                            self.vectorstore.EmbeddingStore.cmetadata['session_id'].astext == str(self.persona_session_id)
                        )
                    )

                    # Execute the deletion
                    result = session.execute(stmt)
                    session.commit()

                    if _is_dev:
                        debug_log(f"clear_conversation_history - Deleted {result.rowcount} conversation documents")
            
            if _is_dev:
                debug_log(f"Conversation history cleared for persona: {self.persona.name}")
            return True
        except Exception as e:
            logger.error(f"Error clearing conversation history: {e}", exc_info=True)
            return False
    
    def update_persona_context(self, new_context: Dict[str, Any]):
        """Update persona context with new information"""
        # This could be used to update the persona's knowledge base
        # or modify their behavior based on new information
        pass

__all__ = ["PersonaAgent", "persona_agent_manager"]
