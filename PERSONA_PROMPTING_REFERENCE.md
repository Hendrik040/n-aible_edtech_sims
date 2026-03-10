# Persona Prompting Reference Guide

> Working reference for the PDF → Persona → Simulation prompting pipeline.
> Last updated: 2026-02-20 — reflects all changes from the Enhanced Persona Extraction & Meta Prompt overhaul.

---

## 1. End-to-End Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  STAGE 1: PDF UPLOAD & EXTRACTION                           │
│                                                             │
│  Browser                                                    │
│    └─→ POST /api/pdf-processing/parse-pdf-fast-autofill     │
│          └─→ PDFProcessingPipeline.process_fast_autofill()  │
│                ├─→ LlamaParse (PDF → markdown)              │
│                ├─→ AIExtractionService                      │
│                │     └─→ extract_personas_and_key_figures() │
│                ├─→ ImageGenerationService (avatars)         │
│                └─→ Repository.save_autofill_data()          │
│                      └─→ DB: simulation_personas (all fields)│
│                                                             │
│    OR:                                                      │
│    └─→ POST /api/pdf-processing/parse-pdf-with-progress     │
│          └─→ PDFProcessingPipeline.process_full_with_progress()
│                ├─→ LlamaParse                               │
│                ├─→ AIExtractionService                      │
│                │     ├─→ extract_personas_and_key_figures() │
│                │     ├─→ generate_scenes()                  │
│                │     └─→ generate_learning_outcomes()       │
│                ├─→ ImageGenerationService (avatars + scenes)│
│                ├─→ Repository.save_full_pdf_data()          │
│                │     └─→ DB: simulation_personas (all fields)│
│                └─→ ProgressManager.send_field_update()      │
│                      └─→ Redis → HTTP polling → Frontend    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  STAGE 2: SIMULATION BUILDER (Frontend)                     │
│                                                             │
│  PDFProgressTrackerHTTP polls /pdf-progress/{session_id}    │
│    └─→ onFieldUpdate("personas", key_figures[])             │
│          └─→ handleFieldUpdate() in page.tsx                │
│                └─→ mapFigureToPersona() ← single source     │
│                      └─→ setPersonas(newPersonas)           │
│                                                             │
│  OR (fast autofill path):                                   │
│  handleAutofill() → API response.key_figures[]              │
│    └─→ mapFigureToPersona() ← same function                 │
│          └─→ setPersonas(newPersonas)                       │
│                                                             │
│  Professor reviews/edits persona cards, then clicks Save:   │
│  handleSave() → POST /api/publishing/simulations/save       │
│    └─→ PublishingService.save_simulation_draft()            │
│          └─→ DB: simulation_personas updated (all fields)   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  STAGE 3: PUBLISH                                           │
│                                                             │
│  POST /api/publishing/simulations/publish/{id}              │
│    └─→ PublishingService.publish_simulation()               │
│          └─→ simulation.is_draft = False                    │
│          └─→ simulation.status = "active"                   │
│          NOTE: Personas are NOT copied — referenced in-place│
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  STAGE 4: STUDENT STARTS SIMULATION                         │
│                                                             │
│  POST /api/simulation/start                                 │
│    └─→ LifecycleService.start_simulation()                  │
│          ├─→ Queries: SimulationPersona (all DB fields)     │
│          ├─→ Builds orchestrator_data dict (incl. db_id)    │
│          └─→ Creates UserProgress (stores orchestrator_data)│
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  STAGE 5: RUNTIME CHAT                                      │
│                                                             │
│  POST /api/simulation/stream                                │
│    └─→ ChatHandler.handle_stream_message()                  │
│          ├─→ OrchestratorManager.load_orchestrator()        │
│          │     └─→ ChatOrchestrator(orchestrator_data)      │
│          ├─→ orchestrator.initialize_langchain_session()    │
│          │     └─→ _create_agent_sessions()                 │
│          │           └─→ _get_persona_from_db(db_id)        │
│          │                 └─→ SimulationPersona (fresh DB) │
│          │                       └─→ PersonaAgent(persona)  │
│          └─→ persona_agent.chat_stream(                     │
│                  message,                                   │
│                  scene_context={                            │
│                    "current_scene": {title, desc, objs},    │
│                    "simulation": {title, desc, challenge,   │
│                                   student_role}             │
│                  }                                          │
│              )                                              │
│                └─→ _get_system_prompt() → 4-block prompt   │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Stage 1 — PDF → Persona Extraction

### Key Files
| File | Purpose |
|---|---|
| `backend/modules/pdf_processing/router.py` | FastAPI endpoints |
| `backend/modules/pdf_processing/pipeline.py` | Pipeline orchestration |
| `backend/modules/pdf_processing/parser_service.py` | LlamaParse PDF → markdown |
| `backend/modules/pdf_processing/ai_extraction_service.py` | GPT-4o extraction prompts |
| `backend/modules/pdf_processing/image_generation_service.py` | Avatar + scene image generation |
| `backend/modules/pdf_processing/repository.py` | DB writes |

### Single Extraction Function (consolidated)

Both the fast autofill endpoint and the full progress endpoint now call the **same** function:

**`extract_personas_and_key_figures(content, title, session_id=None)`**
- **Model**: `gpt-4o`, `temperature=0.3`, `max_tokens=12000`
- **Input**: Full preprocessed content
- **Prompt instructs**: "aim for at least 4–6 personas, err on the side of including more"
- **Post-processing**: Filters out the student-role character using `is_main_character` flag + 4-char minimum name overlap

> `extract_personas_fast` was deleted. There is one prompt to maintain.

### Extracted Persona Shape (from GPT-4o → to DB)
```json
{
  "name": "Full name and title as stated in the case",
  "role": "Their position/title",
  "background": "Professional history and organizational context. 2-3 sentences.",
  "current_context": "Current responsibilities, challenges, case-specific perspective. 2-3 sentences.",
  "correlation": "How this persona relates to the student role",
  "personality_traits": {
    "openness": 7,
    "conscientiousness": 8,
    "extraversion": 4,
    "agreeableness": 6,
    "neuroticism": 3
  },
  "primary_goals": ["Goal 1", "Goal 2", "Goal 3"],
  "knowledge_areas": [
    "Specific fact or data point from the case",
    "Another specific piece this persona would know"
  ],
  "communication_style": "Direct and data-driven, formal in group settings",
  "is_main_character": false
}
```

> **Personality model**: Big Five (1–10 each). The old 8-trait schema
> (`analytical`, `creative`, `assertive`, `collaborative`, `detail_oriented`,
> `risk_taking`, `empathetic`, `decisive`) was fully replaced. Old rows with
> those keys had `personality_traits` reset to `NULL` in the Alembic migration.

### Student Role Filtering (backend)
```python
# ai_extraction_service.py — after GPT-4o returns
student_role_parts = re.match(r'([^(]+)', student_role)
student_name = student_role_parts.group(1).strip().lower()

for figure in result["key_figures"]:
    # Primary: model flagged this as the protagonist
    if figure.get("is_main_character"):
        is_student_role = True

    # Secondary: name overlap (4-char minimum to avoid false matches)
    if not is_student_role and student_name and len(student_name) >= 4:
        if student_name in figure_name or figure_name in student_name:
            is_student_role = True

    if not is_student_role:
        filtered_figures.append(figure)
```

### Fast Autofill vs Full Pipeline

| | Fast Autofill | Full with Progress |
|---|---|---|
| **Endpoint** | `POST /parse-pdf-fast-autofill` | `POST /parse-pdf-with-progress` |
| **Pipeline method** | `process_fast_autofill()` | `process_full_with_progress()` |
| **Extraction** | `extract_personas_and_key_figures()` | `extract_personas_and_key_figures()` |
| **Also generates** | Avatars only | Scenes + learning outcomes + all images |
| **DB save** | `save_autofill_data()` | `save_full_pdf_data()` |
| **Response** | JSON: `{ key_figures, title, student_role, simulation_id }` | SSE field updates via Redis polling |
| **Frontend handler** | `handleAutofill()` response | `handleFieldUpdate('personas', ...)` |

---

## 3. Stage 2 — Database Models

### `SimulationPersona` (table: `simulation_personas`)
```python
id, simulation_id
name: str
role: str
background: str              # Professional history — 2-3 sentences
current_context: str         # NEW — Current challenges/perspective in the case
correlation: str             # How they relate to the student role
primary_goals: List[str]     # JSON array
personality_traits: Dict     # Big Five: {openness, conscientiousness, extraversion,
                             #            agreeableness, neuroticism} each 1–10
knowledge_areas: List[str]   # NEW — Specific facts/data this persona knows from the case
communication_style: str     # NEW — How this persona communicates
system_prompt: str           # OPTIONAL — custom author-written prompt (Identity block only)
image_url: str
deleted_at: DateTime         # Soft deletion
```

**Migration**: `backend/common/db/migrations/versions/2026_02_20_1200-add_enhanced_persona_fields.py`
- Adds `current_context`, `knowledge_areas`, `communication_style` (all nullable)
- Resets `personality_traits` to `NULL` for rows using old trait keys (no Big Five keys present)
- Uses `personality_traits::jsonb ? 'openness'` for the check (json type requires explicit cast)

### `SimulationScene` (table: `simulation_scenes`)
```python
id, simulation_id
title: str
description: str
user_goal: str          # Student's specific objective for this scene
scene_order: int
timeout_turns: int
success_metric: str
image_url: str
```

### `scene_personas` (join table)
```python
scene_id, persona_id, involvement_level   # "participant", "key", "mentioned"
```

---

## 4. Stage 2 — Frontend: Simulation Builder

### The Core Problem That Was Fixed

The frontend had **four separate places** that mapped raw AI extraction output to `PersonaCard` format. Three of them were duplicates of each other; none of them mapped the new fields. Each had its own inline object literal using the old 8 trait keys, and all were missing `current_context`, `knowledge_areas`, `communication_style`, and `correlation`.

**The fix**: A single `mapFigureToPersona(figure, index)` helper was added at module level in `page.tsx` (line 39). All four handlers now call this function. It is the **single source of truth** for this mapping.

### `mapFigureToPersona(figure, index)` — What it maps

```typescript
// figure = raw object from AI extraction API response
{
  id:                `persona-${Date.now()}-${index}`,
  name:              figure.name,
  position:          figure.role,           // → PersonaCard "position"
  description:       figure.background,     // → PersonaCard "description"
  currentContext:    figure.current_context, // NEW
  correlation:       figure.correlation,    // NEW (was ignored before)
  primaryGoals:      formatted string,      // • Goal 1\n• Goal 2... (from array or string)
  traits: {
    openness:          figure.personality_traits?.openness ?? 5,
    conscientiousness: figure.personality_traits?.conscientiousness ?? 5,
    extraversion:      figure.personality_traits?.extraversion ?? 5,
    agreeableness:     figure.personality_traits?.agreeableness ?? 5,
    neuroticism:       figure.personality_traits?.neuroticism ?? 5,
  },
  defaultTraits:     { all 5 traits: 5 },
  knowledgeAreas:    figure.knowledge_areas ?? [],  // NEW
  communicationStyle: figure.communication_style,  // NEW
  imageUrl:          figure.image_url || figure.imageUrl,
  systemPrompt:      figure.system_prompt,
}
```

### Four Call Sites (all using `mapFigureToPersona`)

| Location (page.tsx) | Trigger | Notes |
|---|---|---|
| `handleAutofill()` response block | Fast autofill API returns JSON directly | Also does student-role filter via `is_main_character` flag |
| `handleFieldUpdate('personas', ...)` | Full pipeline: `PDFProgressTrackerHTTP` fires `onFieldUpdate` | **This was the primary broken path** |
| `handleAutofill()` secondary path | Fast autofill with `key_figures` in `aiData` | Handles response shape variations |
| Background/teaching-notes handler | Late-arriving field update from background pipeline | |

### handleSave → API Payload (field name mapping)

```typescript
// page.tsx handleSave() — maps camelCase → snake_case for backend
personas: personas.map(persona => ({
  ...persona,
  role:               persona.position,
  background:         persona.description,
  current_context:    persona.currentContext,   // ← snake_case for backend
  correlation:        persona.correlation,
  primary_goals:      persona.primaryGoals,
  personality_traits: persona.traits,
  knowledge_areas:    persona.knowledgeAreas,
  communication_style: persona.communicationStyle,
}))
```

### DB Load → Frontend State (field name mapping)

```typescript
// page.tsx loadDraft() — maps snake_case → camelCase for PersonaCard
{
  id:               persona.id,          // numeric DB id — CRITICAL to preserve
  name:             persona.name,
  position:         persona.role,
  description:      persona.background,
  currentContext:   persona.current_context,
  correlation:      persona.correlation,
  primaryGoals:     persona.primary_goals (array → joined string),
  traits:           persona.personality_traits || {},
  knowledgeAreas:   persona.knowledge_areas || [],
  communicationStyle: persona.communication_style,
  imageUrl:         persona.image_url,
  systemPrompt:     persona.system_prompt,
}
```

---

## 5. Stage 3 — Publish

`POST /api/publishing/simulations/publish/{id}` → `PublishingService.publish_simulation()`

**What it does**: Sets `simulation.is_draft = False`, `simulation.is_public = True`, `simulation.status = "active"`.

**What it does NOT do**: Copy, duplicate, or re-serialize any persona data. All `SimulationPersona` rows are referenced in-place by `simulation_id`. No new fields are lost at publish time.

---

## 6. Stage 4 — Student Starts Simulation

`POST /api/simulation/start` → `LifecycleService.start_simulation()`

Builds `orchestrator_data` dict and stores it in `UserProgress.orchestrator_data` (JSONB):

```python
orchestrator_data = {
    "id": simulation.id,
    "title": simulation.title,
    "description": simulation.description,
    "challenge": simulation.challenge,
    "student_role": simulation.student_role,
    "scenes": [ { id, title, description, agent_ids, personas_involved, ... } ],
    "personas": [
        {
            "id": sanitized_name_slug,  # used as agent lookup key
            "db_id": persona.id,        # ← CRITICAL: numeric PK for DB fetch at runtime
            "identity": { name, role, bio },
            "personality": { goals, traits },
            "system_prompt": ...,
            "image_url": ...,
        }
    ]
}
```

> `orchestrator_data["personas"]` contains only a lightweight summary. The **full persona data** (including `current_context`, `knowledge_areas`, `communication_style`) is fetched fresh from DB at runtime using `db_id`.

---

## 7. Stage 5 — Runtime Persona Prompting

### File: `backend/modules/simulation/agents/persona_agent.py`

### 7.1 Persona Loading at Runtime

```
ChatHandler.handle_stream_message()
  └─→ OrchestratorManager.load_orchestrator(user_progress)
        └─→ ChatOrchestrator(orchestrator_data)
              └─→ orchestrator.initialize_langchain_session(user_progress_id)
                    └─→ _create_agent_sessions()
                          for each persona in orchestrator_data["personas"]:
                            db_id = persona["db_id"]
                            persona_obj = await _get_persona_from_db(db_id)
                            # persona_obj = full SimulationPersona SQLAlchemy object
                            # all new fields are present from DB query
                            PersonaAgent(persona_obj, session_id, user_progress_id)
```

### 7.2 scene_context Structure (fixed)

All three chat paths now pass the same nested structure to `persona_agent.chat_stream()`:

```python
scene_context = {
    "current_scene": {
        "title":       current_scene.get("title"),
        "description": current_scene.get("description"),
        "objectives":  current_scene.get("objectives", []),
    },
    "simulation": {
        "title":        orchestrator.simulation.get("title"),
        "description":  orchestrator.simulation.get("description"),
        "challenge":    orchestrator.simulation.get("challenge"),
        "student_role": orchestrator.simulation.get("student_role"),
    },
}
```

**Previously broken**: The `@all` path (line ~243 in chat_handler.py) passed `scene_context=current_scene` (flat dict). `_get_system_prompt()` could not find the `simulation` or `current_scene` keys, so both the CASE STUDY block and SCENE ENVIRONMENT block were always empty for `@all` messages.

### 7.3 `_get_system_prompt()` — 4-Block Architecture

Every call to `persona_agent.chat_stream()` builds a fresh system prompt from four composable blocks:

```
┌─────────────────────────────────────────────────────────────┐
│  BLOCK 1: IDENTITY                                          │
│                                                             │
│  If persona.system_prompt exists (professor-authored):      │
│    PERSONA IDENTITY:                                        │
│    {system_prompt verbatim}                                 │
│                                                             │
│  Otherwise auto-generated from DB fields:                   │
│    You are {name}, {role}.                                  │
│    BACKGROUND: {background}                                 │
│    CURRENT CONTEXT: {current_context}                       │
│    RELATIONSHIP TO STUDENT: {correlation}                   │
│    PRIMARY GOALS: {primary_goals bullet list}               │
│    KNOWLEDGE AREAS: {knowledge_areas bullet list}           │
│    COMMUNICATION STYLE: {communication_style}               │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  BLOCK 2: SIMULATION & STUDENT CONTEXT (always present)     │
│                                                             │
│    CASE STUDY:                                              │
│    Title: {simulation.title}                                │
│    Overview: {simulation.description}                       │
│    Central Challenge: {simulation.challenge}                │
│                                                             │
│    STUDENT ROLE: The student is playing: {student_role}     │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  BLOCK 3: SCENE ENVIRONMENT (always present)                │
│                                                             │
│    CURRENT SCENE: {scene.title}                             │
│    {scene.description}                                      │
│    Scene Objectives: {objectives}                           │
│                                                             │
│    SCENE AWARENESS — Adapt your emotional register:         │
│    "If the scene describes urgency, let that tension come   │
│     through. If it's a planning session, be deliberate."    │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  BLOCK 4: BEHAVIORAL FRAMEWORK & TONE (always present)      │
│                                                             │
│  YOUR PERSONALITY:                                          │
│    {Big Five traits translated to plain-language behavior}  │
│    e.g. "Conscientiousness (8/10 — high): diligent,        │
│           thorough, and goal-driven..."                     │
│                                                             │
│  RULES — NON-NEGOTIABLE:                                    │
│    - You are {name}. Not an AI. A person with stakes.       │
│    - NEVER break character.                                 │
│    - NEVER volunteer unsolicited situation summaries.       │
│    - NEVER use assistant-style closers.                     │
│    - NEVER repeat the student's question before answering.  │
│                                                             │
│  OFF-TOPIC GUARDRAIL:                                       │
│    - React with confusion or redirect, not a literal answer.│
│                                                             │
│  WRITING STYLE:                                             │
│    - Prose only. No bullets, lists, or headers. Ever.       │
│    - Default short (1-3 sentences).                         │
│    - Write like you are in the room.                        │
└─────────────────────────────────────────────────────────────┘
```

**Key behavior for custom `system_prompt`**: It becomes Block 1 (IDENTITY) only. Blocks 2–4 are always appended. This ensures every persona — regardless of professor customization — receives full scene awareness and consistent tone rules.

### 7.4 Big Five Trait → Behavioral Description

```python
# persona_agent.py — _BIG_FIVE_DESCRIPTORS + _describe_personality_traits()
# Input:  {"openness": 7, "conscientiousness": 8, "extraversion": 3, ...}
# Output: "- Openness (7/10 — high): curious and imaginative; actively seeks fresh ideas
#          - Conscientiousness (8/10 — high): diligent, thorough, and goal-driven
#          - Extraversion (3/10 — low): prefers one-on-one conversations..."

Score range → label:
  1-2  → "very low"
  3-4  → "low"
  5-6  → "moderate"
  7-8  → "high"
  9-10 → "very high"
```

### 7.5 LangChain Prompt Template (per request, stateless)

```
[system]           ← _get_system_prompt() — full 4-block output
[chat_history]     ← MessagesPlaceholder (ConversationBufferWindowMemory, fresh from DB/Redis)
[human]            ← "{input}" — student's current message
[agent_scratchpad] ← MessagesPlaceholder — tool call results
```

Tools available to each persona agent:
- `get_scene_context(query)` — semantic search of scene context (PGVector, 5-min Redis cache)
- `get_persona_knowledge(query)` — semantic search of persona background (PGVector, 1-hr Redis cache)

---

## 8. Original Gap Audit (Section 7 of prior version)

| # | Gap | Status |
|---|---|---|
| 7.1 | Case study context missing in default path | **Fixed** — `scene_context` dict structure corrected in all 3 chat paths (single `@mention`, multi-mention `@name1 @name2`, and `@all`) and in orchestrator fallback |
| 7.2 | Personality traits are raw numbers | **Fixed** — `_describe_personality_traits()` translates Big Five scores to plain-language behavioral descriptions in Block 4 |
| 7.3 | No behavioral differentiation per scene | **Fixed** — Block 3 (SCENE ENVIRONMENT) instructs personas to adapt emotional register to scene stakes |
| 7.4 | `attempt_number` parameter unused | **Still unused** — parameter wired through but no per-attempt logic implemented |
| 7.5 | Custom prompt context appended inconsistently | **Fixed** — custom prompt is always Block 1 (IDENTITY) only; Blocks 2–4 always wrap it regardless of code path |
| 7.6 | No tone/register control | **Fixed** — Block 4 WRITING STYLE rules enforce prose-only, short default length, natural speech patterns |
| 7.7 | Persona isolation instruction is reactive | **Improved** — Block 4 RULES now lead with strong positive character definition ("You are a person with stakes") rather than only "don't mimic" |

### Additional Gap Fixed (not in original list)

| | Gap | Fix |
|---|---|---|
| — | `handleFieldUpdate('personas')` in frontend used old 8 trait keys and dropped all new fields — this was the **primary render path** for the full pipeline and caused the persona cards to always show empty Current Context, Communication Style, Knowledge Areas, and Relation to Student | **Fixed** — replaced inline mapping with `mapFigureToPersona()` call |

---

## 9. File Path Quick Reference

| What | Where |
|---|---|
| PDF router (endpoints) | `backend/modules/pdf_processing/router.py` |
| Pipeline orchestration | `backend/modules/pdf_processing/pipeline.py` |
| Persona + scene extraction prompts | `backend/modules/pdf_processing/ai_extraction_service.py` |
| DB writes (autofill + full) | `backend/modules/pdf_processing/repository.py` |
| Progress tracking (Redis + WS) | `backend/modules/pdf_processing/progress_service.py` |
| DB model: SimulationPersona | `backend/common/db/models/publishing/simulation.py` |
| Alembic migration (new columns) | `backend/common/db/migrations/versions/2026_02_20_1200-add_enhanced_persona_fields.py` |
| Publishing service (CRUD) | `backend/modules/publishing/service.py` |
| Publishing router (API responses) | `backend/modules/publishing/router.py` |
| Simulation lifecycle (start) | `backend/modules/simulation/services/lifecycle_service.py` |
| Orchestrator (scene state machine) | `backend/modules/simulation/core/orchestrator.py` |
| Orchestrator manager | `backend/modules/simulation/core/orchestrator_manager.py` |
| Chat handler (all 3 mention paths) | `backend/modules/simulation/handlers/chat_handler.py` |
| PersonaAgent + `_get_system_prompt` | `backend/modules/simulation/agents/persona_agent.py` |
| Persona callback (saves to DB) | `backend/modules/simulation/agents/callbacks.py` |
| Frontend: simulation builder | `frontend/app/professor/simulation-builder/page.tsx` |
| Frontend: `mapFigureToPersona` | `frontend/app/professor/simulation-builder/page.tsx:39` |
| Frontend: `handleFieldUpdate` | `frontend/app/professor/simulation-builder/page.tsx:1921` |
| Frontend: progress tracker component | `frontend/components/PDFProgressTrackerHTTP.tsx` |
| Frontend: PersonaCard component | `frontend/components/PersonaCard.tsx` |
