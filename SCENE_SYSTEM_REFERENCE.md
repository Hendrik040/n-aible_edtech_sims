# Scene System Reference Guide

> End-to-end reference for how scenes are extracted, stored, edited, and used at runtime.
> Last updated: 2026-02-20

---

## 1. End-to-End Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  STAGE 1: EXTRACTION (PDF → Scenes)                         │
│                                                             │
│  PDFProcessingPipeline.process_full_with_progress()         │
│    ├─→ Step 1: extract_personas_and_key_figures()           │
│    │     └─→ personas_result (key_figures[], student_role)  │
│    └─→ Step 2: generate_scenes(content, title, personas)    │
│           └─→ GPT-4o: 4 scenes with persona references      │
│                 └─→ Post-process: filter student role       │
│                       from personas_involved in each scene  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 2: DB SAVE (Repository)                              │
│                                                             │
│  Repository.save_full_pdf_data()                            │
│    ├─→ Create SimulationScene rows (one per scene)          │
│    │     Field mapping: sequence_order → scene_order        │
│    └─→ Create scene_personas rows (join table)              │
│           For each name in personas_involved:               │
│             look up SimulationPersona.id, insert join row   │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 3: SIMULATION BUILDER (Frontend)                     │
│                                                             │
│  PDFProgressTrackerHTTP polls progress endpoint             │
│    └─→ onFieldUpdate("scenes", scenes[])                    │
│          └─→ handleFieldUpdate() in page.tsx                │
│                └─→ setScenes(formattedScenes)               │
│                                                             │
│  Professor edits scenes in SceneCard components             │
│    └─→ handleSave() → normalizeScenes() → API payload       │
│          └─→ POST /api/publishing/simulations/{id}/draft    │
│                └─→ PublishingService.save_simulation_draft()│
│                      Smart update: by ID → by title → new  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 4: SIMULATION START                                  │
│                                                             │
│  LifecycleService.start_simulation()                        │
│    ├─→ Query: all scenes ordered by scene_order             │
│    ├─→ Query: scene_personas join table (bulk load)         │
│    └─→ Build orchestrator_data.scenes[]                     │
│           scenes[i].personas_involved = [name, name, ...]   │
│           Stored in UserProgress.orchestrator_data (JSONB)  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  STAGE 5: RUNTIME (Chat)                                    │
│                                                             │
│  ChatOrchestrator(orchestrator_data)                        │
│    ├─→ current_scene = scenes[state.current_scene_index]    │
│    ├─→ current_scene.personas_involved → route @mentions    │
│    ├─→ scene_context passed to every PersonaAgent prompt    │
│    └─→ SceneProgressionHandler                              │
│           └─→ progress_to_next_scene() when timeout/complete│
│                 └─→ advance index, reset turn_count,        │
│                       create SceneProgress, intro message   │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Stage 1 — Scene Extraction

### Key Files
| File | Purpose |
|---|---|
| `backend/modules/pdf_processing/ai_extraction_service.py` | `generate_scenes()` function |
| `backend/modules/pdf_processing/pipeline.py` | Calls `generate_scenes()` after persona extraction |

### `generate_scenes(content, title, session_id, personas_result)`

- **Model**: `gpt-4o`, `temperature=0.3`, `max_tokens=2048`
- **Called after**: `extract_personas_and_key_figures()` — persona data is a required input
- **Content used**: First 2000 characters of the cleaned case study

### What the Prompt Receives

The scene generation prompt is given three pieces of context derived from the prior persona extraction step:

```python
available_personas = [fig["name"] for fig in personas_result.get("key_figures", [])]
student_role = personas_result.get("student_role", "Business Analyst")

# Included in prompt:
# "STUDENT ROLE: {student_role}"
# "AVAILABLE PERSONAS: {', '.join(available_personas)}"
# "⚠️ DO NOT include the student role in personas_involved arrays"
```

This wires persona names directly into the scene prompt, so GPT-4o references actual extracted characters by name rather than inventing new ones.

### What GPT-4o Returns

3–6 scenes following a flexible narrative arc (the AI extraction service accepts
between 3 and 6 scenes; edge counts outside 2–10 are rejected as degenerate):

```
Scene 1 — Crisis/Opening:      The inciting event; introduces the core problem
Scene 2 — Investigation:       Deeper exploration; student gathers information
Scene 3 — Solution/Decision:   Student must synthesize findings and decide
Scene 4+— Implementation/...   Act on decisions; manage consequences (optional extra scenes)
```

Each scene object:
```json
{
  "title": "string",
  "description": "2-3 sentences with vivid detail (used for image generation)",
  "personas_involved": ["Name A", "Name B"],
  "user_goal": "Specific actionable objective for the student in this scene",
  "goal": "General summary",
  "success_metric": "Measurable criteria for scene completion",
  "sequence_order": 1
}
```

### Post-Processing: Student Role Filter

After GPT-4o returns, the student role character is removed from every scene's `personas_involved` array. The backend does this with normalized name comparison:

```python
def normalize_name(name: str) -> str:
    # Remove title prefixes (Mr., Dr., Prof., etc.)
    normalized = re.sub(r'^(Mr\.|Mrs\.|Ms\.|Miss|Dr\.|Prof\.)\s+', '', name.strip(), flags=re.IGNORECASE)
    # Strip all non-alpha characters, lowercase
    return re.sub(r'[^a-zA-Z]', '', normalized).lower()

# Extract name portion of student_role (ignore parenthetical title)
# e.g. "Luigi Ferrari (President)" → "luigi ferrari" → "luigiferrari"
student_name_normalized = normalize_name(student_role.split('(')[0].strip())

for scene in scenes:
    scene["personas_involved"] = [
        p for p in scene.get("personas_involved", [])
        if normalize_name(p) != student_name_normalized
    ]
```

> This is the **second** filter — the extraction prompt already instructs GPT-4o not to include the student role. The post-process is a safety net.

---

## 3. Stage 2 — Database Model & Saving

### `SimulationScene` Model (`simulation_scenes` table)

```python
# backend/common/db/models/publishing/simulation.py

class SimulationScene(Base):
    __tablename__ = "simulation_scenes"

    id: int                       # Primary key
    simulation_id: int            # FK → simulations.id

    # Core content
    title: str
    description: str              # Scene narrative (also used for image gen prompt context)
    user_goal: str                # Student's objective for this scene

    # Ordering & timing
    scene_order: int              # Determines linear progression order (1, 2, 3, 4)
    timeout_turns: int            # Max student turns before scene auto-advances (default 15)

    # Success tracking
    success_metric: str           # Text description of measurable success
    max_attempts: int             # Optional retry limit (nullable)
    success_threshold: float      # Optional score threshold (nullable)

    # Advanced configuration (all nullable)
    goal_criteria: Dict           # JSON — structured goal evaluation config
    hint_triggers: Dict           # JSON — conditions for surfacing hints
    scene_context: str            # Text — additional context for AI agents
    persona_instructions: Dict    # JSON — per-persona behavioral overrides

    # Media
    image_url: str                # Scene background image
    image_prompt: str             # Prompt used to generate image

    # Soft delete & timestamps
    deleted_at: datetime          # NULL = active; set = soft-deleted
    created_at: datetime
    updated_at: datetime
```

### `scene_personas` Join Table

```python
scene_personas = Table(
    "scene_personas",
    Column("scene_id",          FK → simulation_scenes.id, CASCADE, primary_key=True),
    Column("persona_id",        FK → simulation_personas.id, CASCADE, primary_key=True),
    Column("involvement_level", String, default="participant"),
    Column("created_at",        DateTime),
)
# Composite PK: (scene_id, persona_id) — one row per persona per scene
# involvement_level: always "participant" in the current extraction pipeline
```

### `Repository.save_full_pdf_data()` — Scene Section

```python
# backend/modules/pdf_processing/repository.py

# 1. Deduplicate by title (skip if scene with same title already exists)
existing_scene_titles = {s.title for s in existing_scenes}

for scene_data in scenes:
    if scene_data.get("title") in existing_scene_titles:
        continue  # Idempotent — won't double-create on retry

    scene = SimulationScene(
        simulation_id = simulation.id,
        title         = scene_data.get("title"),
        description   = scene_data.get("description", ""),
        user_goal     = scene_data.get("user_goal", ""),
        scene_order   = scene_data.get("sequence_order", 0),  # ← key: maps sequence_order → scene_order
        image_url     = scene_data.get("image_url", ""),
        image_prompt  = f"Business scene: {scene_title}",
        timeout_turns = int(scene_data.get("timeout_turns") or 15),
        success_metric = scene_data.get("success_metric", ""),
    )
    db.add(scene)
    db.flush()  # get scene.id immediately

    # 2. Create scene_personas rows
    personas_involved_filtered = [
        p for p in scene_data.get("personas_involved", [])
        if not is_main_character(p, student_role)
    ]

    for name in set(personas_involved_filtered):
        # Exact match first, then case-insensitive fallback
        persona_id = persona_mapping.get(name) or next(
            (pid for pname, pid in persona_mapping.items()
             if name.lower().strip() == pname.lower().strip()), None
        )
        if persona_id:
            db.execute(scene_personas.insert().values(
                scene_id=scene.id,
                persona_id=persona_id,
                involvement_level="participant"
            ))
```

> **Field name mismatch to know about**: GPT-4o outputs `sequence_order`; the DB column is `scene_order`. The repository maps this explicitly. The frontend also handles both keys in `normalizeScenes()`.

---

## 4. Stage 3 — Simulation Builder (Frontend)

### Key Files
| File | Purpose |
|---|---|
| `frontend/app/professor/simulation-builder/page.tsx` | Main builder page — all scene state |
| `frontend/components/SceneCard.tsx` | Individual scene display + edit component |

### How Scenes Arrive in the Frontend

**Path A — Full pipeline (primary):**
The backend sends a `field_update` event with `fieldName = "scenes"` via the progress tracker. `handleFieldUpdate` in `page.tsx` receives it:

```typescript
// page.tsx — handleFieldUpdate('scenes', fieldValue)
case 'scenes':
  const formattedScenes = fieldValue.map((scene: any, index: number) => ({
    id:              `scene-${index}`,         // Temporary client-side ID
    title:           scene.title,
    description:     scene.description,
    personasInvolved: scene.personas_involved || [],
    userGoal:        scene.user_goal,
    sequenceOrder:   scene.sequence_order || index + 1,
    imageUrl:        scene.image_url || '',
    successMetric:   scene.success_metric,
    goal:            scene.goal,
    ...scene                                   // Preserve all other AI fields
  }));
  setScenes(formattedScenes);
```

> Note: at this stage `id` is a temporary `scene-${index}` string, not a DB integer. The real DB IDs are only present after a Save round-trip.

**Path B — Loading a saved draft:**
```typescript
// page.tsx — loadDraft() — DB IDs are preserved
const transformedScenes = draftData.scenes.map((scene: any) => ({
  ...scene,
  id:             scene.id,               // ← numeric DB ID, CRITICAL to preserve
  sequence_order: scene.scene_order,      // Map scene_order → sequence_order for frontend
  successMetric:  scene.success_metric,
  personas_involved: scene.personas_involved || []
}));
setScenes(transformedScenes);
```

### SceneCard Component

**Props & Interface:**
```typescript
interface Scene {
  id: string | number;
  title: string;
  description: string;
  personas_involved: string[];   // Array of persona names (not IDs)
  user_goal: string;
  sequence_order: number;
  image_url?: string;
  successMetric?: string;
  timeout_turns?: number;
}

interface SceneCardProps {
  scene: Scene;
  allPersonas?: any[];           // Full persona list for the dropdown
  studentRole?: string;          // Filtered out of personas_involved display
  onSave?: (scene: Scene) => void;
  onDelete?: () => void;
  editMode?: boolean;
}
```

**What professors can edit per scene:**

| Field | UI Control | Notes |
|---|---|---|
| `title` | Text input | Scene name |
| `user_goal` | Text input | Student's objective |
| `description` | Textarea | Scene narrative |
| `personas_involved` | Tag pills + dropdown | Select from available personas; student role auto-excluded |
| `sequence_order` | Number input | Linear order (1–4) |
| `timeout_turns` | Number input | Max turns before auto-advance (default 15) |
| `successMetric` | Textarea | Measurable success criteria |
| `image_url` | Image upload | Scene background |

**Persona filtering in SceneCard:**
```typescript
// Same normalize_name logic as backend — strips titles, non-alpha chars, lowercases
const normStudentRole = normalizeName(studentRole || "");

// Personas shown in the "add persona" dropdown exclude the student role
allPersonas.filter(p => normalizeName(p.name) !== normStudentRole)
```

### Saving Scenes Back to the API

`handleSave()` runs scenes through `normalizeScenes()` before including them in the payload:

```typescript
// normalizeScenes() — frontend/app/professor/simulation-builder/page.tsx
function normalizeScenes(scenes: any[]) {
  return scenes.map(scene => ({
    ...scene,
    id:            scene.id,             // Preserved — backend uses this to match existing rows
    image_url:     scene.image_url,
    timeout_turns: scene.timeout_turns ?? 15,
    // Normalize scene_order from either field name
    scene_order:   scene.sequence_order ?? scene.scene_order,
  }));
}

// In handleSave payload:
const payload = {
  scenes: normalizeScenes(scenes),
  // ...
};
```

---

## 5. Stage 3 — Publishing Service: Smart Scene Update

`PublishingService.save_simulation_draft()` uses a three-way match strategy when scenes arrive in the save payload:

```
For each incoming scene:
  1. Does scene.id match an existing SimulationScene.id?
     → Yes: update that row in-place
  2. Does scene.title match an existing scene's title?
     → Yes: update that row (handles case where ID was not preserved)
  3. Neither?
     → Create a new SimulationScene row

After processing all incoming scenes:
  → Any existing scenes NOT in the incoming list are soft-deleted
    (deleted_at = now())

For scene_personas:
  → DELETE all existing associations for the scene
  → INSERT new ones based on the incoming personas_involved[] names
    (look up SimulationPersona by name + simulation_id)
```

This approach is safe for:
- Reordering scenes (ID preserved)
- Renaming a scene (falls back to create)
- Deleting a scene (not in incoming list → soft-deleted)
- Adding a scene (no ID → created)

---

## 6. Stage 4 — Simulation Start: Serialization into orchestrator_data

`LifecycleService.start_simulation()` builds the `orchestrator_data` dict stored in `UserProgress.orchestrator_data` (JSONB). This snapshot is the source of truth for the runtime — it is not re-queried from DB during a session.

```python
orchestrator_data = {
    "id": simulation.id,
    "title": simulation.title,
    "description": simulation.description,
    "challenge": simulation.challenge,
    "student_role": simulation.student_role,
    "scenes": [
        {
            "id":                scene.id,
            "title":             scene.title,
            "description":       scene.description,
            "user_goal":         scene.user_goal,
            "objectives":        [scene.user_goal] or ["Complete the scene interaction"],
            "image_url":         scene.image_url,
            "personas_involved": scene_personas_map[scene.id],  # List of persona names
            "agent_ids":         [sanitized_name_slug, ...],    # For @mention routing
            "timeout_turns":     scene.timeout_turns or 15,
            "max_turns":         scene.timeout_turns or 15,
            "success_criteria":  f"User achieves: {scene.user_goal}",
            "scene_order":       scene.scene_order,
        }
        for scene in all_scenes   # Ordered by scene_order
    ],
    "personas": [ ... ]           # See PERSONA_PROMPTING_REFERENCE.md
}
```

**Key query: scene-persona map (bulk load, avoids N+1):**
```python
scene_ids = [scene.id for scene in all_scenes]
personas_by_scene = repository.get_personas_for_scenes(scene_ids)
scene_personas_map = {
    scene.id: [p.name for p in personas_by_scene.get(scene.id, [])]
    for scene in all_scenes
}
```

---

## 7. Stage 5 — Runtime Scene Usage

### Current Scene Access

```python
# ChatOrchestrator
current_scene = orchestrator.simulation["scenes"][orchestrator.state.current_scene_index]

# current_scene shape:
{
  "id":                2,
  "title":             "The Board Meeting",
  "description":       "The executive team has gathered...",
  "user_goal":         "Convince the board to approve the restructuring plan",
  "objectives":        ["Convince the board to approve the restructuring plan"],
  "personas_involved": ["Elena Rossi", "Marco Bianchi"],
  "agent_ids":         ["elena_rossi", "marco_bianchi"],
  "timeout_turns":     15,
  "scene_order":       2,
}
```

### How scenes feed the persona system prompt

`scene_context` is built from `current_scene` + `orchestrator.simulation` and passed to every `PersonaAgent.chat_stream()` call:

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

Inside `_get_system_prompt()`, this becomes Block 3 of the system prompt:
```
CURRENT SCENE: The Board Meeting
The executive team has gathered for an emergency meeting...

Scene Objectives: Convince the board to approve the restructuring plan

SCENE AWARENESS — Adapt your emotional register to this environment:
If the scene describes urgency or conflict, let that tension come through in how you
speak. If it's exploratory, be more deliberate. Let the stakes inform your language.
```

### @mention Routing

`personas_involved` in the current scene determines which personas respond:

```python
# chat_handler.py — @all handling
personas_involved = current_scene.get("personas_involved", [])  # List of names

for persona in orchestrator.simulation.get("personas", []):
    if persona["identity"]["name"] in personas_involved:
        scene_personas.append(persona)
```

For `@name` mentions, `agent_ids` (sanitized slugs) are used as lookup keys.

### Scene Progression

`SceneProgressionHandler.progress_to_next_scene()` advances the simulation when:
- `orchestrator.state.turn_count >= current_scene.timeout_turns` (timeout)
- Scene is marked complete by the grading agent or manual trigger

```python
# scene_progression.py
def progress_to_next_scene(orchestrator, user_progress, current_scene_id):
    next_index = orchestrator.state.current_scene_index + 1
    scenes = orchestrator.simulation["scenes"]

    if next_index < len(scenes):
        next_scene = scenes[next_index]

        # Advance orchestrator state
        orchestrator.state.current_scene_index = next_index
        orchestrator.state.turn_count = 0
        orchestrator.state.scene_completed = False
        orchestrator.state.current_scene_id = next_scene["id"]

        # DB: mark current scene complete, create SceneProgress for next
        mark_scene_complete(user_progress, current_scene_id)
        initialize_new_scene(user_progress, next_scene["id"], orchestrator)

        return { "next_scene": next_scene, "scene_intro_message": ... }
    else:
        # All scenes done
        user_progress.simulation_status = "completed"
        return { "simulation_complete": True }
```

---

## 8. Field Name Mapping Reference

One of the friction points in this system is that the same concept uses different field names at different layers. This table tracks them:

| Concept | GPT-4o output | DB column | orchestrator_data | Frontend state | SceneCard prop |
|---|---|---|---|---|---|
| Display order | `sequence_order` | `scene_order` | `scene_order` | `sequence_order` | `sequence_order` |
| Student goal | `user_goal` | `user_goal` | `user_goal` | `userGoal` | `user_goal` |
| Linked personas | `personas_involved` | `scene_personas` (join) | `personas_involved` | `personas_involved` | `personas_involved` |
| Success criteria | `success_metric` | `success_metric` | `success_criteria` | `successMetric` | `successMetric` |
| Turn limit | *(not in output)* | `timeout_turns` | `timeout_turns` + `max_turns` | `timeout_turns` | `timeout_turns` |
| Scene image | `image_url` | `image_url` | `image_url` | `imageUrl` | `image_url` |

> `normalizeScenes()` in page.tsx handles the `sequence_order ↔ scene_order` translation on every save. The repository handles `sequence_order → scene_order` on initial extraction save.

---

## 9. File Path Quick Reference

| What | Where |
|---|---|
| Scene extraction prompt | `backend/modules/pdf_processing/ai_extraction_service.py:324` |
| Student role post-filter (extraction) | `backend/modules/pdf_processing/ai_extraction_service.py:422` |
| Scene save (initial extraction) | `backend/modules/pdf_processing/repository.py:299` |
| scene_personas creation (extraction) | `backend/modules/pdf_processing/repository.py:330` |
| DB model: SimulationScene | `backend/common/db/models/publishing/simulation.py:92` |
| DB model: scene_personas join table | `backend/common/db/models/publishing/simulation.py:120` |
| Publishing scene read (API response) | `backend/modules/publishing/router.py:456` |
| Publishing scene save (draft) | `backend/modules/publishing/service.py:400` |
| scene_personas rebuild on save | `backend/modules/publishing/service.py:477` |
| Scene serialization for runtime | `backend/modules/simulation/services/lifecycle_service.py:129` |
| Scene-persona map (bulk query) | `backend/modules/simulation/services/lifecycle_service.py:108` |
| Current scene access at runtime | `backend/modules/simulation/core/orchestrator.py:381` |
| scene_context passed to agents | `backend/modules/simulation/handlers/chat_handler.py:246` |
| Scene progression handler | `backend/modules/simulation/core/scene_progression.py` |
| Frontend: handleFieldUpdate scenes | `frontend/app/professor/simulation-builder/page.tsx:1975` |
| Frontend: normalizeScenes | `frontend/app/professor/simulation-builder/page.tsx` (search `normalizeScenes`) |
| Frontend: draft load (scenes) | `frontend/app/professor/simulation-builder/page.tsx:444` |
| SceneCard component | `frontend/components/SceneCard.tsx` |
