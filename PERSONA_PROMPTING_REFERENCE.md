# Persona Prompting Reference Guide

> Working reference for understanding and improving the PDF → Persona → Simulation prompting pipeline.

---

## 1. Architecture Overview

```
PDF Upload
  └─→ PDFProcessingPipeline
        ├─→ LlamaParse  (text extraction)
        ├─→ AIExtractionService  (GPT-4o — persona & scene generation)
        ├─→ ImageGenerationService  (avatars, scene images)
        └─→ Repository  (saves to DB)

Simulation Runtime
  └─→ SimulationService
        └─→ ChatOrchestrator  (scene state machine)
              └─→ PersonaAgent (per persona, LangChain)
                    ├─→ _get_system_prompt()  ← CORE PROMPTING
                    ├─→ ConversationBufferWindowMemory (fresh per request)
                    └─→ Tools: get_scene_context, get_persona_knowledge (PGVector)
```

---

## 2. Stage 1 — PDF → Persona Extraction

### Files
| File | Purpose |
|---|---|
| `backend/modules/pdf_processing/pipeline.py` | Orchestrates the full pipeline |
| `backend/modules/pdf_processing/parser_service.py` | LlamaParse PDF → markdown |
| `backend/modules/pdf_processing/ai_extraction_service.py` | GPT-4o extraction prompts |

### Two Extraction Modes

#### A. Fast Autofill (`extract_personas_fast`)
- **Model**: `gpt-4o`, temp=0.1, max_tokens=4000
- **Input**: First 2000 chars of content only
- **System role**: `"You are a JSON generator for business case study analysis. Create detailed descriptions with specific information, numbers, and context. Be thorough and informative."`
- **Returns**: title, description (5-7 paragraphs), student_role, key_figures

Key instruction in the prompt:
```
PRIORITY: Look for the MAIN CHARACTER or PROTAGONIST of the case study first.
If there's a clear main character/protagonist, use their name and title (e.g., "John Smith (CEO of Company Name)").
If no specific character is mentioned, default to "Business Analyst".
```

#### B. Full Extraction (`extract_personas_and_key_figures`)
- **Model**: `gpt-4o`, temp=0.2, max_tokens=12000
- **Input**: Full combined content
- **System role**: `"You are a JSON generator for business case study analysis. Focus on creating comprehensive, detailed descriptions that give students complete context."`
- **Post-processing**: Filters out student role character from key_figures using name/role matching + `is_main_character` flag

Key instruction:
```
⚠️ CRITICAL EXCLUSION RULE ⚠️
DO NOT include the student role character in the key_figures array.
key_figures are NPCs (non-player characters) that the student will interact with.
```

### Extracted Persona Shape (→ Database)
```json
{
  "name": "string",
  "role": "string",
  "correlation": "relationship to narrative",
  "background": "2-3 sentence background",
  "primary_goals": ["goal1", "goal2", "goal3"],
  "personality_traits": {
    "analytical": 0-10,
    "creative": 0-10,
    "assertive": 0-10,
    "collaborative": 0-10,
    "detail_oriented": 0-10
  },
  "is_main_character": false
}
```

### Scene Generation (`generate_scenes`)
- **Model**: `gpt-4o`, temp=0.3, max_tokens=2048
- **Input**: First 2000 chars + available persona names (NPCs only)
- **Output**: 4 scenes with progression: Crisis → Investigation → Solution → Implementation
- Also post-processes scenes to remove student role from `personas_involved`

### Learning Outcomes (`generate_learning_outcomes`)
- **Model**: `gpt-4o`, temp=0.2, max_tokens=1024
- **Input**: First 1500 chars
- **Output**: 5 numbered learning outcomes

---

## 3. Stage 2 — Database Models

### `SimulationPersona` (table: `simulation_personas`)
```python
id, simulation_id
name: str
role: str
background: str       # 2-3 sentence background from extraction
correlation: str      # how they relate to the case
primary_goals: List[str]
personality_traits: Dict   # {"analytical": 7, "creative": 5, ...}
system_prompt: str    # OPTIONAL custom prompt; if set, used verbatim at runtime
image_url: str
deleted_at: DateTime  # soft deletion
```

**`system_prompt` is the key field for prompting work.** If blank → runtime generates default. If set → used mostly verbatim (with scene context appended).

### `SimulationScene` (table: `simulation_scenes`)
```python
id, simulation_id
title: str
description: str
user_goal: str        # student's specific objective
scene_order: int
timeout_turns: int
goal_criteria: Dict
image_url: str
```

### `scene_personas` (join table)
```python
scene_id, persona_id
involvement_level: str   # "key", "participant", "mentioned"
```

---

## 4. Stage 3 — Runtime Persona Prompting

### File: `backend/modules/simulation/agents/persona_agent.py`

### 4.1 Prompt Construction: Two Paths

The method `_create_persona_prompt_with_attempt(attempt_number, scene_context)` is called on every chat turn.

**Path A — Custom `system_prompt` exists:**
```python
# persona.system_prompt is stored verbatim in DB
# The runtime appends case study context + scene context + a conversation note
system_prompt = (
    self.persona.system_prompt          # verbatim
    + case_study_context                # simulation title/description/challenge + student_role + scene title/desc/objectives
    + scene_context_str                 # from scene_context dict (key:value pairs)
    + conversation_instruction          # "Conversation history is already available in your memory..."
)
# All curly braces escaped for LangChain template safety
```

**Path B — No custom prompt (default generated):**
`_get_system_prompt(attempt_number, scene_context)` builds the full prompt inline.

### 4.2 `_get_system_prompt()` — The Default Prompt (lines 338–413)

```
You are {name}, a {role} in this business simulation.

CASE STUDY CONTEXT:
Title: {simulation.title}
Description: {simulation.description}
Challenge: {simulation.challenge}

STUDENT ROLE: You are interacting with a student who is playing the role of: {simulation.student_role}

CURRENT SCENE: {scene.title}
Scene Description: {scene.description}
Scene Objectives: {scene.objectives joined by comma}

PERSONA BACKGROUND:
{persona.background}

CORRELATION TO CASE:
{persona.correlation}

PERSONALITY TRAITS:
{comma-joined k:v pairs from personality_traits dict}

PRIMARY GOALS:
• {goal1}
• {goal2}
...

INSTRUCTIONS:
- CONVERSATION HISTORY: You have access to recent conversation history in your memory. Use it to maintain context and respond appropriately.
- CONVERSATION ANALYSIS: When analyzing conversation history, pay attention to the chronological order of messages to determine what happened first, last, etc.
- PERSONA ISOLATION: NEVER copy or mimic other personas' responses, patterns, or behaviors. Stay true to YOUR unique character and role.
- Stay in character as {name} at all times
- Respond based on your role, background, and personality traits
- Help guide the user toward scene objectives through realistic business interaction
- Don't directly give away answers, but provide realistic business insights
- Keep responses concise and professional (2-4 sentences typically)
- Use your tools to access relevant context and knowledge
- If the user seems stuck, provide subtle hints through natural conversation
- Maintain consistent character behavior based on your personality traits, goals, and role

Remember: You are {name}, not an AI assistant. Respond as this character would in a real business situation.
```

### 4.3 Scene Context Injection

`scene_context` dict passed to `_create_persona_prompt_with_attempt()` has this shape:
```python
{
    "simulation": {
        "title": ...,
        "description": ...,
        "challenge": ...,
        "student_role": ...
    },
    "current_scene": {
        "title": ...,
        "description": ...,
        "objectives": [...]
    }
}
```

**NOTE**: The orchestrator intentionally passes ONLY `current_scene` (not the full simulation dict) to `chat_with_persona_langchain()`:
```python
# orchestrator.py line 447-451
combined_context = {
    "current_scene": current_scene   # <-- no "simulation" key
}
```
This means `case_study_context` is empty string when called through the orchestrator's non-streaming path. The streaming router (`linear-chat-stream`) likely passes the full context — check `simulation/router.py` and `simulation/service.py` to confirm.

### 4.4 LangChain Prompt Template Structure

```
[system]      ← _get_system_prompt() output
[chat_history] ← MessagesPlaceholder (ConversationBufferWindowMemory)
[human]       ← "{input}" (student's current message)
[agent_scratchpad] ← MessagesPlaceholder (tool call results)
```

### 4.5 Agent Setup Per Request (Stateless)

Every call to `chat()` or `chat_stream()` creates fresh:
1. `ConversationBufferWindowMemory` — loaded from DB/Redis cache
2. `ChatPromptTemplate`
3. `create_openai_tools_agent(llm, tools, prompt)`
4. `AgentExecutor` with `max_iterations=PERSONA_AGENT_MAX_ITERATIONS` (default 2)

**LLM**: `langchain_manager.create_fresh_llm()` — isolated per agent instance, same OpenAI API

### 4.6 Tools Available to Each Persona Agent

| Tool | Description | Vector Filter | Cache TTL |
|---|---|---|---|
| `get_scene_context(scene_description)` | Semantic search of scene context | `persona_id + context_type=scene` | 5 min |
| `get_persona_knowledge(query)` | Semantic search of persona background | `persona_id + context_type=knowledge` | 1 hr |

Both use `_cached_vector_search()` → Redis → PGVector fallback.

---

## 5. Conversation History Loading

### Flow
1. Check Redis cache (`conversation_cache.get_cached_history(user_progress_id, scene_id, session_id_filter)`)
2. Cache miss → query `ConversationLog` table filtered by `user_progress_id + scene_id + session_id` variants
3. Max messages: `settings.max_conversation_history_messages` (default 20)
4. Loaded into fresh `ConversationBufferWindowMemory`:
   - `"user"` → `add_user_message()`
   - `"ai_persona"` → `add_ai_message()` (ALL personas, not just current one)
   - `"orchestrator"` → `add_ai_message()`

**Session ID scheme**: `session_{base}_persona_{persona.id}` — ensures isolation between personas in same scene while still loading all scene conversation history.

---

## 6. Orchestrator System Prompt (Fallback Path)

File: `backend/modules/simulation/core/orchestrator.py` — `get_system_prompt()` (line 611)

This prompt is used when LangChain is **not** available or for the non-LangChain orchestration path. It's a different model:
- Lists all personas with `@agent_id: name (role) - bio` format
- Includes scene objectives, success metric, turns remaining
- Instructs the orchestrator to respond as different agents using `**@agent_name:** "dialogue here"` format

This is separate from the per-persona `PersonaAgent` prompts and should not be confused with them.

---

## 7. Key Prompt Gaps / Observations (Starting Points for Improvement)

### 7.1 Case Study Context Missing in Default Path
The orchestrator's `chat_with_persona_langchain()` passes only `{"current_scene": ...}` — the `simulation` key is absent. So the default `_get_system_prompt()` renders the CASE STUDY CONTEXT block as empty strings for title/description/challenge. **The persona doesn't know what case study it's in when called from the orchestrator.**

### 7.2 Personality Traits Are Numbers, Not Descriptions
Traits like `{"analytical": 8, "creative": 5}` are passed as raw integers. The LLM has to infer what "analytical: 8" means behaviorally. There's no translation layer to natural language (e.g., "highly analytical, data-driven, methodical").

### 7.3 No Behavioral Differentiation Per Scene
The same full system prompt is used for every scene. There's no mechanism to give a persona different emphases or constraints per-scene (e.g., "In this scene, be more resistant" or "In this scene, you're under time pressure").

### 7.4 `attempt_number` Parameter Is Unused
`_create_persona_prompt_with_attempt(attempt_number, ...)` accepts `attempt_number` but the parameter is not used in the default prompt generation — there's no actual per-attempt few-shot examples injected. The parameter is wired through but inactive.

### 7.5 Custom `system_prompt` Gets Context Appended Inconsistently
- In `_get_system_prompt()` (line 341–344): returns custom prompt **verbatim** with no appended context.
- In `_create_persona_prompt_with_attempt()` (line 293–327): appends `case_study_context + scene_context_str + conversation_instruction` to custom prompt.
- These two methods are called from different code paths, leading to inconsistent behavior depending on which path the request takes.

### 7.6 No Tone / Register Control
The default instructions say "2-4 sentences typically" but there's no mechanism for a persona to be configured to be more verbose, use formal/informal language, or reflect domain-specific communication styles.

### 7.7 Persona Isolation Instruction Is Reactive
"NEVER copy or mimic other personas" is a negative instruction. It doesn't give positive guidance on how to differentiate. When all personas receive each other's messages in their conversation history (by design), the risk of cross-persona bleed is real.

---

## 8. File Path Quick Reference

| What | Where |
|---|---|
| PDF pipeline orchestration | `backend/modules/pdf_processing/pipeline.py` |
| Fast persona extraction prompt | `backend/modules/pdf_processing/ai_extraction_service.py:151` |
| Full persona extraction prompt | `backend/modules/pdf_processing/ai_extraction_service.py:260` |
| Scene generation prompt | `backend/modules/pdf_processing/ai_extraction_service.py:441` |
| DB model: SimulationPersona | `backend/common/db/models/publishing/simulation.py` |
| Runtime persona agent | `backend/modules/simulation/agents/persona_agent.py` |
| Default system prompt generation | `backend/modules/simulation/agents/persona_agent.py:338` |
| Prompt template construction | `backend/modules/simulation/agents/persona_agent.py:271` |
| Tools (scene/knowledge search) | `backend/modules/simulation/agents/persona_agent.py:155` |
| Conversation history loading | `backend/modules/simulation/agents/persona_agent.py:415` |
| Orchestrator (state machine) | `backend/modules/simulation/core/orchestrator.py` |
| Orchestrator system prompt | `backend/modules/simulation/core/orchestrator.py:611` |
| Chat handler | `backend/modules/simulation/handlers/chat_handler.py` |
| Simulation router (streaming) | `backend/modules/simulation/router.py` |
| Callback (saves response to DB) | `backend/modules/simulation/agents/callbacks.py` |
